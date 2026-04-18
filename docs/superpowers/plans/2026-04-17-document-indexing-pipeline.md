# Plan: Document Indexing Pipeline for Staff Uploads

**Issue:** [#191](https://github.com/William-Hill/d4bl_ai_agent/issues/191)
**Branch:** `feat/191-document-indexing`
**Parent context:** v2 work deferred from PR #189 (staff contributor guide)

---

## Goal

When an admin approves a document upload in the review queue, the document is extracted, chunked, embedded, and stored so that (a) CrewAI research agents cite it in answers and (b) it appears in `/explore` vector search results.

## Non-goals (deferred again)

- Data source processing pipeline (that's #190)
- Example query training integration (that's #192)
- Retroactive processing of uploads approved before this ships
- Periodic re-crawl of URL-based documents
- Multi-format support beyond PDF, DOCX, and URL

---

## Current state

### What exists today

- `uploads` table has a `file_path` column (currently always `NULL` — files aren't persisted)
- `Upload.metadata_` JSONB stores document-specific fields including `source_url` for URL-based uploads
- `VectorStore.store_scraped_content()` in `src/d4bl/infra/vector_store.py:104` writes to `scraped_content_vectors` using a required `job_id` FK
- `scraped_content_vectors` schema (`supabase/migrations/20240101000000_enable_vector_extension.sql:29`) has columns: `id`, `job_id`, `url`, `content`, `content_type`, `metadata`, `embedding`
- Crawl4AI is wired up for URL fetching via research agents (`src/d4bl/agents/tools/crawl_tools/`)
- Admin review UI shows `pending_review` → approves → flips `status = approved`. That's where we need to plug in.

### What's missing

- No PDF or DOCX text extractor in the codebase
- No chunker (existing ingestion scripts embed whole pages, not chunks — the scraped_content_vectors schema assumes ≤ 6000 chars per row, enforced by VectorStore truncation)
- No background task runner for inline Python work (only CrewAI jobs use `research_runner.py`)
- `scraped_content_vectors.job_id` is `NOT NULL` — incompatible with documents that don't belong to a research job

---

## Design decisions (need review before implementation)

### 1. Where do embedded chunks live?

**Option A (recommended):** Extend `scraped_content_vectors` — make `job_id` nullable, add a `source` column (`research_job` | `staff_upload`).

**Option B:** New table `staff_document_vectors` with its own schema.

**Why A:** Research agents already query `scraped_content_vectors` — making staff docs appear in the same table means zero agent-side changes. Adding a `source` column lets `/explore` filter to just staff-contributed content when desired.

**Why not B:** Means duplicating the embedding column, index, and query logic. Every consumer has to be taught about two tables.

**Tradeoff:** Schema change affects the research pipeline. We'd need a small migration and a careful review of existing inserts (all use `job_id`).

### 2. Processing trigger

**Option A (recommended):** Inline on approval — admin clicks approve, processing runs in the request, admin sees success or error immediately.

**Option B:** Background task via FastAPI `BackgroundTasks` — admin click returns fast, processing runs after.

**Option C:** Separate worker process (Celery, RQ) — most robust, most infra.

**Why A:** Simplest. The review queue is an admin-only surface, and admins don't mind a few seconds of wait for explicit feedback. PDF extraction + chunking + embedding for a typical 20-page doc is ~10–30 seconds on local Ollama. Inline also lets us surface errors without a separate status-polling UI.

**Why not B/C:** Worth it for large docs (100+ pages), but we can add an async path later. Start simple.

**Failure mode:** On timeout or extraction error, flip status to `processing_failed` and show the error in the review queue. Admin can fix metadata and click "retry" (new endpoint).

### 3. Raw file storage

**Option A (recommended):** Parse-and-discard. Extract text on approval, store chunks in the vector table, drop the original upload bytes.

**Option B:** Persist raw file to Supabase Storage so citations can deep-link back to the original PDF.

**Why A:** PR #189 explicitly deferred Supabase Storage wiring. Shipping without it keeps the scope tight. Citations can still identify the source (filename, uploader, upload date) via metadata.

**Why not B:** Worth revisiting when we have a concrete user story for "open the original PDF" — today no UI shows raw files.

**Tradeoff:** If extraction fails and we've discarded the file, the admin can't retry without re-uploading. Mitigation: do extraction in the upload endpoint, not on approval — reject bad files at upload time.

### 4. URL-based documents

**Option A (recommended):** Fetch via Crawl4AI on approval (same time as PDF extraction).

**Option B:** Fetch on upload; store extracted text in `metadata_.preview` so admins can review the actual content, not just the URL.

**Why B actually wins:** Admins should be approving the content, not the URL. If the site changed between upload and approval, they'd be approving something they never saw. Fetching on upload + storing preview in metadata lets the review be honest.

**Cost:** Upload endpoint gets slower (Crawl4AI fetch is 2–10s). Acceptable for staff workflow.

**Correction to issue description:** I'm flipping my recommendation on this one compared to the issue — crawl on upload, not approval.

### 5. Chunking strategy

**Option A (recommended):** Simple paragraph-based chunking with 500-char target and 100-char overlap. No fancy sentence boundary detection.

**Option B:** LangChain / LlamaIndex recursive chunker.

**Why A:** mxbai-embed-large handles chunks up to 6000 chars (already truncated in vector_store.py:65). Paragraph splits are good enough for agent retrieval and avoid a heavy dependency.

### 6. Agent citation format

When an agent cites a chunk, it needs to identify the source clearly. Proposed `metadata` JSONB shape for staff-upload rows:

```json
{
  "source_type": "staff_upload",
  "upload_id": "uuid",
  "uploader_email": "alice@d4bl.org",
  "title": "Overlooked: Women and Jails",
  "original_filename": "vera_overlooked.pdf",
  "source_url": null,
  "chunk_index": 3,
  "total_chunks": 47,
  "uploaded_at": "2026-04-17T15:00:00Z"
}
```

Agents can include `"Source: <title> (staff upload by <email>)"` in citations.

---

## Implementation milestones

### Milestone 1: Schema + extractors (foundational)

- [ ] Migration: `supabase/migrations/20260418000000_staff_documents_vectors.sql` — `ALTER TABLE scraped_content_vectors ALTER COLUMN job_id DROP NOT NULL; ADD COLUMN source VARCHAR(30) NOT NULL DEFAULT 'research_job';`
- [ ] `src/d4bl/services/document_processing/extractors.py` — `extract_pdf(bytes) -> str`, `extract_docx(bytes) -> str`, `extract_url(url) -> str` (uses Crawl4AI)
- [ ] `src/d4bl/services/document_processing/chunker.py` — `chunk_text(text, chunk_size=500, overlap=100) -> list[str]`
- [ ] Unit tests for extractors and chunker (fixtures: small PDF, small DOCX)

### Milestone 2: Vector store extension

- [ ] `VectorStore.store_staff_document(upload_id, chunks, metadata) -> list[UUID]` — embed each chunk, insert with `job_id=NULL`, `source='staff_upload'`
- [ ] Update `store_scraped_content` to default `source='research_job'` explicitly
- [ ] Integration test: insert chunks, query by metadata, verify retrieval

### Milestone 3: Upload endpoint — fetch URL previews

- [ ] Modify `POST /api/admin/uploads/document` in `src/d4bl/app/upload_routes.py` — when `url` is provided, fetch via Crawl4AI and store extracted text in `metadata_.preview_text`
- [ ] On fetch failure, reject with 422 + error message
- [ ] Test: mock Crawl4AI, confirm preview is populated

### Milestone 4: Approval processing

- [ ] `src/d4bl/services/document_processing/approve.py` — `process_document_upload(upload_id, db) -> None` that reads metadata, extracts + chunks + embeds + stores
- [ ] Modify `POST /api/admin/uploads/{upload_id}/review` — when `status = approved` and `upload_type = document`, call `process_document_upload` inline
- [ ] On exception, set `upload.status = processing_failed`, store error in `reviewer_notes`, do not raise (admin can retry)
- [ ] New endpoint: `POST /api/admin/uploads/{upload_id}/retry-processing` (admin-only)

### Milestone 5: UI surfacing

- [ ] `ReviewQueue.tsx` — show `processing_failed` state with error message + retry button
- [ ] `UploadHistory.tsx` — show processing status for document uploads (pending / approved / indexed / processing_failed)
- [ ] `/explore` vector search — no code change if we're reusing `scraped_content_vectors`, but add a filter UI for "Staff uploads only" (optional — can defer)

### Milestone 6: Guide copy fix

- [ ] Update `ui-nextjs/app/guide/page.tsx` Section 2 to describe actual shipped behavior
- [ ] Specifically: "When you upload, the platform fetches URL content immediately so the admin can review the actual text. On approval, the document is chunked and indexed into the vector store. Agents cite approved documents in research answers."

### Milestone 7: Verification + tests

- [ ] End-to-end test: upload PDF → admin approves → vector search retrieves a chunk
- [ ] End-to-end test: upload URL → preview populates → admin approves → agent citation includes title
- [ ] Manual QA: run a research job, confirm an approved staff document surfaces in the output

---

## Critical files

| Path | Role |
| --- | --- |
| `src/d4bl/app/upload_routes.py` | Add preview fetch on upload, call processing on review |
| `src/d4bl/infra/vector_store.py` | Add `store_staff_document` method |
| `src/d4bl/services/document_processing/` | **New package** for extractors, chunker, approve flow |
| `src/d4bl/infra/database.py` | No model changes — schema change via migration only |
| `supabase/migrations/20260418000000_*.sql` | **New** — relax job_id, add source column |
| `ui-nextjs/components/admin/ReviewQueue.tsx` | Surface processing state + retry |
| `ui-nextjs/components/admin/UploadHistory.tsx` | Show indexed/failed state |
| `ui-nextjs/app/guide/page.tsx` | Section 2 copy fix |
| `tests/test_document_processing.py` | **New** — extractor + chunker + approve tests |

---

## Dependencies to add

- `pypdf` (PDF text extraction) — lightweight, already in the Python ecosystem, no native deps
- `python-docx` (DOCX text extraction) — similar profile

Both added to `pyproject.toml` under `[project.optional-dependencies.ingestion]` or the default deps (decide during Milestone 1).

---

## Risks

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Schema change breaks existing research_job inserts | High | Default `source = 'research_job'`, update `store_scraped_content` explicitly, add migration test |
| Crawl4AI unavailable during upload | Medium | 422 with actionable error; admin can retry upload |
| Ollama embedding slow on large docs (100+ chunks) | Medium | Accept for inline path; document in PR that >50-page docs may take 1min+ |
| PDF extraction fails on scanned/image-based PDFs | Low | pypdf returns empty string; upload endpoint rejects with clear message |

---

## Out of scope for this PR

- Supabase Storage for raw file persistence
- Re-crawl of URL documents on a schedule
- OCR for image-based PDFs
- Background worker / queue system for long-running processing
- Retroactive processing of pre-existing approved uploads (none exist yet)

---

## Questions for review

1. Do you agree with flipping URL fetch from approval-time to upload-time (design decision #4)?
2. Are you comfortable with inline processing for v1 (design decision #2), or should we plan for a background worker up front?
3. Should the schema change (design decision #1) be a separate PR that lands first, or bundled into this feature PR?
