# Unstructured Training Data & Document Layer Design

**Issue:** #151 — feat: add unstructured data to training corpus for v3 iteration
**Date:** 2026-03-31
**Status:** Approved

## Problem

v2.0 eval results show no improvement over v1.0 despite Qwen 3.5-4B upgrade and 8× evaluator data expansion. Root cause: the entire training pipeline feeds exclusively from structured database tables (census, CDC, BJS, etc.). No unstructured content — web scrapes, research reports, news articles, policy documents — is included.

The model learned narrow patterns from templated passages ("In {year}, {state} reported...") rather than generalizable equity analysis. The evaluator learned synthetic perturbation patterns, not real-world hallucination detection.

### v2.0 Baseline Metrics

| Metric | v2.0 Result | Target |
|--------|-------------|--------|
| Parser entity F1 | 58% | 80% |
| Parser schema valid | 70% | 95% |
| Parser community_framing | Always null | Populated |
| Evaluator hallucination accuracy | 0.6% | 85% |
| Explainer JSON valid | 100% | 95% |
| Explainer overfitting ratio | 2.15 (eval/train) | < 1.5 |

## Approach

**Unified Document Layer (Approach 1):** Build a `documents` + `document_chunks` schema that serves three access patterns — training extraction, RAG/research, and the explore UI — then wire it into the existing training pipeline. Implementation is phased by data availability, with a v3 training experiment after Phase 1 to validate the hypothesis before investing in later phases.

## Architecture: Mini Lakehouse

The design follows a medallion architecture (bronze → silver → gold) right-sized for the current stack:

| Layer | What | Where |
|-------|------|-------|
| **Bronze (raw)** | Original PDFs, HTML snapshots | Supabase Storage (buckets) |
| **Silver (extracted)** | Cleaned text, metadata, source URLs | Supabase Postgres (`documents` + `document_chunks`) |
| **Gold (enriched)** | Embeddings, training corpus snapshots | Supabase Postgres (pgvector) + local JSONL cache |

Text-native sources (RSS, news, web scrapes) go directly to silver — the raw and extracted forms are identical. Binary sources (PDFs) must hit bronze first because the raw file carries information that extracted text loses.

### Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Storage for raw files | Supabase Storage | Already in stack, handles binary, signed URLs for explore UI |
| Extracted text + metadata | Supabase Postgres | JOINable with structured data, single-database queries |
| Versioning | Option A — latest-only | `extraction_metadata` JSONB captures provenance; upgrade to versioned rows is one migration if ever needed |
| Document granularity | Chunked rows with parent | Standard RAG pattern; one embedding per chunk for retrieval precision |
| Existing `scraped_content_vectors` | Migrate + compatibility view | Avoids permanent UNION tax; expand-migrate-contract pattern |
| Training corpus cache | Local filesystem (gitignored) | Avoids repeated network pulls from remote Supabase during training |

## Schema

### `documents` table

One row per source file/article/report.

```sql
CREATE TABLE documents (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title               TEXT,
    source_url          TEXT,
    storage_path        TEXT,                   -- Supabase Storage path (PDFs, HTML snapshots); nullable for text-native sources
    content_type        VARCHAR(50) NOT NULL,   -- pdf, html, article, policy_bill, research_report, news, rss
    source_key          VARCHAR(100),           -- links to data_sources.name for lineage
    job_id              UUID REFERENCES research_jobs(job_id),  -- nullable; for research-generated content
    extraction_metadata JSONB DEFAULT '{}',     -- parser used, version, timestamp, params
    metadata            JSONB DEFAULT '{}',     -- title, author, publish date, topic tags, etc.
    created_at          TIMESTAMPTZ DEFAULT now(),
    updated_at          TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_documents_content_type ON documents(content_type);
CREATE INDEX idx_documents_source_key ON documents(source_key);
CREATE INDEX idx_documents_job_id ON documents(job_id) WHERE job_id IS NOT NULL;
CREATE UNIQUE INDEX idx_documents_source_url ON documents(source_url) WHERE source_url IS NOT NULL;
```

### `document_chunks` table

N rows per document. Each chunk gets its own embedding.

```sql
CREATE TABLE document_chunks (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id     UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    content         TEXT NOT NULL,
    chunk_index     INTEGER NOT NULL,
    token_count     INTEGER,
    embedding       vector(1024),               -- mxbai-embed-large
    metadata        JSONB DEFAULT '{}',         -- page_number, section_heading, etc.
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_chunks_document_id ON document_chunks(document_id);
CREATE INDEX idx_chunks_embedding ON document_chunks
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
CREATE UNIQUE INDEX idx_chunks_doc_position ON document_chunks(document_id, chunk_index);
```

### Compatibility view

Replaces the original `scraped_content_vectors` table after data migration.

```sql
CREATE VIEW scraped_content_vectors AS
SELECT
    dc.id,
    d.job_id,
    d.source_url AS url,
    dc.content,
    d.content_type,
    d.metadata,
    dc.embedding,
    d.created_at,
    d.updated_at
FROM document_chunks dc
JOIN documents d ON dc.document_id = d.id;
```

## Data Flow

### Phase 1: Reshape Existing Data (v3 training experiment)

Sources that already exist in the database — no new ingestion or infrastructure needed.

**Policy bill summaries** (`policy_bills` → `documents` + `document_chunks`):
- Note: Currently only Alabama and Alaska data. Migration handles what exists; new bills flow into `documents` as they're ingested after OpenStates re-ingestion.
- Each bill becomes one document with metadata (state, status, topic_tags, session).
- Most summaries are short enough to be a single chunk.

**Research job outputs** (`research_jobs` → `documents` + `document_chunks`):
- Parse `result` and `research_data` JSON fields to extract narrative text.
- Title is the original research query.
- Handle varying result structures gracefully.

**Scraped content migration** (`scraped_content_vectors` → `documents` + `document_chunks`):
- Preserve existing embeddings — no re-computation needed.
- Existing `job_id` links carry forward.

### Phase 2: RSS/News Ingestion (future — after v3 results validate hypothesis)

Modify `ingest_rss_feeds.py` and `ingest_news_search.py` to write directly to `documents` + `document_chunks` instead of `ingested_records`. Requires active feed URLs configured in `data_sources` table.

### Phase 3: PDF Pipeline (future — new capability)

Upload PDFs to Supabase Storage bucket "documents". Extract text via pypdf/pdfplumber. Sentence-aware chunking with page number metadata on each chunk.

### Shared Utilities

Both used by all phases:

1. **Chunker** — Sentence-aware text splitter with configurable target token count and optional overlap. Splits on sentence boundaries, not raw token count. Metadata tracks whether each chunk is a clean boundary (paragraph/section) vs. forced split.

2. **Embedder** — Calls Ollama `mxbai-embed-large` to generate 1024-dim vectors. Batched to avoid overloading the endpoint. Same model already used by `vector_store.py`.

## Training Pipeline Changes

### Corpus Extraction (`extract_corpus.py`)

Add `"documents"` to the `EXTRACTORS` registry alongside existing structured table extractors. The render function wraps chunk text with light metadata context (content type, title) — no heavy templating needed since the text is already natural prose.

Output: `corpus_pretrain.jsonl` shifts from 100% templated structured data to a mix of structured and unstructured passages.

### Evaluator Pair Generation (`generate_training_pairs.py`)

**New document-sourced hallucination pairs:** Use `document_chunks` directly as factual reference text. The chunk itself IS the factual response — no need for Claude to generate one (step 1 of the current pipeline). Only the perturbation step (step 2) uses Claude. This:
- Cuts API cost per pair in half for document-sourced examples
- Produces more realistic training data (natural prose variation, not templated)
- Teaches the evaluator to detect hallucinations in the text distribution it will see at inference time

Both the existing structured perturbation pipeline and the new document-sourced pipeline run together. Target mix: ~50% structured-sourced pairs (existing pipeline, ensures coverage of tabular data patterns) and ~50% document-sourced pairs (new pipeline, covers natural prose). Exact ratio is tunable via config — adjust based on v3 eval results.

### Parser `community_framing` Examples

Add training pairs where questions clearly imply community framing, using policy bills and research outputs as context. Policy bill `topic_tags` map to `issue_domain` slugs naturally:
- housing → housing
- criminal justice → criminal_justice
- voting rights → voting_rights

Example pair:
```
Question: "Our community in Georgia is fighting eviction rates — what does HB 432 actually do for tenants?"
Expected: { "detected": true, "issue_domain": "housing", "structural_frame": "economic_displacement" }
```

### Quick Wins (config only)

| Change | Current | New | Rationale |
|--------|---------|-----|-----------|
| Explainer epochs | 7 | 4 | Overfitting observed after epoch 4.3 (eval/train ratio 2.15) |
| Explainer LoRA rank | r=32 | r=16 (test both) | Reduce overfitting capacity; evaluate impact |

## Explore Page & RAG Integration

### RAG / Research Agents

Update `vector_store.py` to query `document_chunks` instead of `scraped_content_vectors`. Join with `documents` parent for metadata (title, content_type, source_url) in search results. The compatibility view handles the transition — existing code works until updated.

### Explore Page (future — out of scope for this issue)

When implemented: a related documents panel alongside existing structured visualizations. Metadata-filtered queries (by state, content_type) rather than vector search. "View original" links to source URLs or signed Supabase Storage URLs for PDFs.

## Data Flywheel & Metrics

### The D4BL Data Flywheel

The technical flywheel maps directly to the D4BL research methodology (Community Engagement → Problem Identification → Data Collection + Analysis → Policy Innovation → Power Building):

| Technical Stage | D4BL Stage | What Happens | Metric |
|---|---|---|---|
| **1. Documents In** | Data Collection + Analysis | Diverse sources ingested — community-relevant, not just government databases | Document count by type, total token volume, corpus unstructured % |
| **2. Training** | Problem Identification | Model learns to parse community voice into structural queries | Parser entity F1, evaluator hallucination accuracy, community_framing F1 |
| **3. Research Quality** | Policy Innovation | Outputs connect data to specific policy levers and advocacy opportunities | Avg evaluation scores per completed job, policy connection rate |
| **4. Feedback** | Community Power Building | Community use generates new documents and corrections | Research jobs → documents rate, community corrections count |

Core principles at the center: Data as Protest, Data as Accountability, Data as Collective Action.

### Measurement for Leadership

Time-series tracking three curves:
1. **Corpus diversity** — % of training corpus that is unstructured (target: 0% → 40-60%)
2. **Model accuracy** — composite of parser entity F1 + evaluator hallucination accuracy
3. **Research output quality** — average evaluation score across completed jobs

The narrative: "As we added more diverse data to the training corpus, model accuracy improved, which produced better research outputs, which fed back into the corpus."

### Implementation

Flywheel metrics are queryable from three existing tables (`documents`/`document_chunks`, `model_eval_runs`, `evaluation_results`). Initial measurement via script; dashboard UI is out of scope.

Each training iteration tags `model_eval_runs.metrics` with corpus composition:
```json
{
  "corpus_version": "v3.0",
  "corpus_stats": {
    "structured_passages": 12000,
    "unstructured_passages": 4500,
    "content_types": {"research_report": 800, "policy_bill": 2200, "scraped": 1500},
    "total_tokens": 8500000
  }
}
```

### Visual

A flywheel diagram mapping the four technical stages to D4BL methodology stages has been drafted (SVG in `.superpowers/brainstorm/`). Production-quality visual to be generated via Gamma for leadership presentation after v3 results are in.

## Migration Strategy

### Step 1: Create new tables
Supabase migration adds `documents` and `document_chunks`. No existing tables modified. Zero risk.

### Step 2: Populate from existing data
One-time migration script. Each source (policy bills, research jobs, scraped content) runs independently — if one fails, the others are unaffected.

### Step 3: Create compatibility view
1. Rename `scraped_content_vectors` to `scraped_content_vectors_legacy`
2. Create view with the same name
3. Verify `vector_store.py` works against the view
4. Drop legacy table once confirmed

### Step 4: Update `vector_store.py`
Point `similarity_search()` at `document_chunks` directly. View remains for any other callers.

### Rollback
Legacy table exists until explicitly dropped. One-command recovery: drop the view, rename legacy table back.

## Scope

### In Scope (this issue)

- `documents` + `document_chunks` schema + Supabase migration
- Compatibility view for `scraped_content_vectors`
- Chunker and embedder shared utilities
- Phase 1 data population (policy bills, research jobs, scraped content migration)
- `extract_corpus.py` changes to include unstructured documents
- Evaluator pair generation from real document passages
- Parser `community_framing` training examples
- Explainer quick wins (epochs 7→4, optional LoRA rank r=32→r=16)
- Flywheel metrics queries (raw SQL or script)
- Supabase Storage bucket creation (for future PDF use)
- Corpus composition tagging in `model_eval_runs`

### Out of Scope (future tickets)

Each item below should become its own issue for a future sprint:

| Future Ticket | Description | Depends On |
|---|---|---|
| **RSS/news ingestion into document schema** | Modify `ingest_rss_feeds.py` and `ingest_news_search.py` to write to `documents` + `document_chunks`. Configure active feed URLs in `data_sources`. | This issue (schema must exist) |
| **PDF extraction pipeline** | Upload PDFs to Supabase Storage, extract text via pypdf/pdfplumber, sentence-aware chunking with page metadata. | This issue (schema + Storage bucket) |
| **Explore page related documents panel** | Collapsible panel showing policy bills, news, research reports related to selected state/metric. Metadata-filtered queries. "View original" links. | This issue (schema) + frontend work |
| **Flywheel metrics dashboard UI** | Admin page card with time-series charts for corpus diversity, model accuracy, and research quality. | This issue (metrics queries) |
| **Gamma leadership presentation** | Production-quality flywheel visual + narrative slide deck for D4BL leadership. Generate after v3 results demonstrate improvement. | v3 training results |
| **Figma flywheel production visual** | Clean, modern infographic version of the flywheel diagram via Figma (manual or MCP when available). | Flywheel SVG wireframe (done) |
| **OpenStates re-ingestion** | Fix timeout issues, ingest policy bills for all states (currently only AL and AK). Write directly to `documents` schema. | This issue (schema) |
| **Database-level extraction versioning** | Add `extraction_version` + `is_current` columns to `documents` if re-extraction comparison is needed. One-migration upgrade from current Option A. | PDF extraction pipeline |
| **`vector_store.py` full rewrite** | Restructure vector store module around new schema. Current scope is just repointing queries. | This issue |
| **Ingestion scripts → document schema** | Wire remaining ingestion scripts (CDC, Census, EPA, etc.) to also produce `documents` entries for their narrative content. | This issue (schema) |

### Not Changing

- Structured table extractors in `extract_corpus.py` (census, CDC, EPA, etc.)
- `prepare_dataset.py` logic (dedup, split ratios, swap augmentation)
- Training infrastructure (`train.py`, Colab setup) except config tweaks
- Existing ingestion scripts — continue writing to their own tables
- Explore page structured data panels (StateMap, RacialGapChart, etc.)
- Query engine structured search path (`parser.py` → `structured.py`)
