# Staff Contributor Guide — Design Spec

**Issue:** #188
**Date:** 2026-04-17
**Status:** Draft

## Problem

As D4BL grows beyond the founding developer(s), staff need a self-serve path to contribute data sources, reference documents, example queries, and feature ideas — without requiring Git or CLI knowledge. The current `CONTRIBUTING.md` and `DEVELOPMENT.md` are developer-oriented and assume technical fluency.

## Audience

- **Audience A (non-technical):** Staff who use the app but haven't written code. Need a fully guided UI experience.
- **Audience B (technical-adjacent):** Staff who've edited config files or written some Python/SQL. Can follow detailed instructions and may want to understand the system more deeply.

## Solution Overview

Five deliverables:

1. **Admin Upload UI** — three upload tabs added to `/admin`
2. **Backend Upload API** — endpoints + `Upload` model with review workflow
3. **Staff Tutorial Page** — `/guide` route with walkthroughs for all contribution types
4. **Review Queue** — admin-only tab for approving/rejecting uploads
5. **Approval Processing** — approved uploads flow into existing pipelines

## 1. Admin Upload UI

Three new tabs on the existing `/admin` page, accessible to authenticated staff.

### Tab 1 — Data Sources

- File picker: `.csv`, `.xlsx`
- Required fields:
  - Source name (text)
  - Description (textarea)
  - Geographic level (dropdown: state / county / tract)
  - Data year (number)
- Optional fields:
  - Source URL (where the data was obtained)
  - Category tags (multi-select)
- On submit: upload file to Supabase Storage, create `pending_review` record in Postgres
- Shows user's upload history with status badges (pending / approved / rejected + reviewer notes)

### Tab 2 — Documents

- File picker: `.pdf`, `.docx` — plus a URL text input for web articles
- Required fields:
  - Title (text)
  - Document type (dropdown: report / article / policy brief / other)
  - Topic tags (multi-select)
- On submit:
  - Files: store in Supabase Storage, create metadata record
  - URLs: store URL, optionally trigger Crawl4AI to extract content
- Same upload history view

### Tab 3 — Example Queries

- Text form (no file upload):
  - Query text (textarea, required)
  - Expected summary format (dropdown: brief / detailed)
  - Description of what makes this a good example (textarea, required)
- Optional fields:
  - Curated answer text (textarea)
  - Relevant data sources (multi-select from known sources)
- On submit: create record in Postgres
- Same upload history view

### Shared UI Patterns

- Progress indicator during file upload
- Inline validation (file size limits, required fields)
- Toast notifications for success/failure
- Upload history per user with status badges

## 2. Backend Upload API

### Endpoints

| Method | Endpoint | Auth | Purpose |
|--------|----------|------|---------|
| `POST` | `/api/admin/uploads/datasource` | staff+ | Upload a CSV/XLSX data source |
| `POST` | `/api/admin/uploads/document` | staff+ | Upload a document or submit URL |
| `POST` | `/api/admin/uploads/query` | staff+ | Submit an example query |
| `GET` | `/api/admin/uploads` | staff+ | List uploads (filterable by type, status, user) |
| `PATCH` | `/api/admin/uploads/{id}/review` | admin | Approve or reject an upload |
| `POST` | `/api/admin/uploads/feature-request` | staff+ | Submit a feature request |

### Database Model — `Upload`

New SQLAlchemy model in `src/d4bl/infra/database.py`:

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID | Primary key |
| `user_id` | UUID | FK to Supabase auth user |
| `upload_type` | Enum | `datasource` / `document` / `query` |
| `status` | Enum | `pending_review` / `approved` / `rejected` / `processing` / `live` |
| `file_path` | String (nullable) | Supabase Storage key (null for queries) |
| `original_filename` | String (nullable) | Original uploaded filename |
| `file_size_bytes` | Integer (nullable) | File size |
| `metadata` | JSONB | Type-specific fields (source name, geo level, tags, etc.) |
| `reviewer_id` | UUID (nullable) | Admin who reviewed |
| `reviewer_notes` | Text (nullable) | Review feedback |
| `reviewed_at` | Timestamp (nullable) | When reviewed |
| `created_at` | Timestamp | Auto-set |
| `updated_at` | Timestamp | Auto-updated |

### Validation Rules (Minimal)

- **Data sources:** file parses as valid CSV/XLSX, under 50MB, has at least one row of data
- **Documents:** valid file type (PDF/DOCX), under 25MB. URLs must be reachable (HEAD request).
- **Queries:** non-empty query text, under 2000 characters

### Supabase Storage

- Bucket: `uploads` (private)
- Path structure: `{upload_type}/{user_id}/{uuid}_{original_filename}`

## 3. Staff Tutorial Page

**Route:** `/guide` — accessible to any authenticated user.
**Linked from:** admin sidebar, main navigation.

### Page Structure

React components (not markdown) for consistent styling with the rest of the app. Collapsible sections so it doesn't overwhelm.

#### Section 1 — "Adding a Data Source"

- What counts as a good data source (geographic level, racial breakdowns, recency)
- Supported file formats and size limits
- Step-by-step walkthrough of the upload flow
- Concrete example: uploading a county-level CSV from County Health Rankings
- What happens after upload (review queue → approval → appears in `/explore`)

#### Section 2 — "Sharing a Document"

- What types of documents are useful (policy briefs, reports, news articles)
- File upload vs. URL submission — when to use which
- How documents feed the research agents and vector search
- Concrete example: uploading a Vera Institute incarceration report PDF

#### Section 3 — "Contributing Example Queries"

- What makes a good example query (specific, answerable, equity-focused)
- How examples improve the system (training data, templates for other users)
- Concrete example: crafting a query about housing discrimination with expected results

#### Section 4 — "Requesting a Feature"

- In-app feature request form on the `/guide` page (fields: title, description, who benefits, example of how it would work). Submits to a new `feature_requests` table in Postgres, visible in the admin review queue. Avoids requiring staff to use GitHub.
- What happens next: triage, prioritization, communication back to requester
- Example: a well-written feature request vs. a vague one

#### Section 5 — "Developing a Feature" (Advanced)

- Clearly marked as optional / for technical-adjacent staff
- High-level codebase architecture (simplified)
- Local dev environment setup (condensed, friendly)
- Branch → build → PR workflow for beginners
- Links to full `DEVELOPMENT.md` for details

### UX Details

- Each upload section has a "Try it now →" button linking to the relevant admin upload tab
- Collapsible accordion sections — all collapsed by default except section 1
- No sidebar TOC (page isn't long enough to need one)

## 4. Review Queue

**Added to `/admin` as a "Review Queue" tab — visible only to admin role.**

- Table of pending uploads sorted by submission date
- Filterable by upload type (datasource / document / query)
- Each row: uploader name, type, source name/title, submitted date, file size
- Click to expand:
  - Data sources: preview first 10 rows
  - Documents: metadata display, download link for raw file
  - Queries: full query text and optional curated answer
- Action buttons:
  - **Approve** (with optional note) — triggers processing pipeline
  - **Reject** (with required note explaining why) — sends feedback to uploader
- No assignment workflow, no multi-step review. One admin clicks approve or reject.

## 5. Approval Processing

When an admin approves an upload:

- **Data sources:** status → `processing`. System reads the CSV/XLSX and stores the parsed rows in a new `uploaded_datasets` table (generic key-value rows with the upload ID as FK, preserving the original column names). This avoids needing to map arbitrary CSVs into typed tables like `CensusIndicator`. A developer can later write a migration or script to promote the data into a typed table if warranted. Status → `live`. Creates a `DataLineage` record.
- **Documents:** status → `processing`. File content extracted (PDF text extraction or Crawl4AI for URLs), vectorized, stored in Supabase vector store. Creates a `Document` record. Status → `live`.
- **Queries:** status → `live`. Inserted into a new `example_queries` table. No async processing needed.

When an admin rejects:

- Status → `rejected`, `reviewer_notes` populated.
- Uploader sees the rejection reason in their upload history.
- Raw file remains in Supabase Storage for reference (auto-cleaned after 90 days).

## Out of Scope (v1)

- Column mapping wizard for data sources (future: guided mapping UI)
- Bulk upload / batch processing
- Edit-after-submit (staff must re-upload)
- Notifications (email/Slack) for review status changes
- Public-facing contribution (requires auth)

## Migration

One new Alembic migration adding these tables to Postgres:

- **`uploads`** — as defined in section 2
- **`uploaded_datasets`** — generic storage for approved CSV/XLSX data: `id` (UUID), `upload_id` (FK), `row_index` (int), `data` (JSONB — one key per original column)
- **`example_queries`** — `id` (UUID), `upload_id` (FK), `query_text` (text), `summary_format` (text), `description` (text), `curated_answer` (text, nullable), `relevant_sources` (JSONB array, nullable), `created_at` (timestamp)
- **`feature_requests`** — `id` (UUID), `user_id` (FK), `title` (text), `description` (text), `who_benefits` (text), `example` (text, nullable), `status` (enum: open / acknowledged / planned / closed), `admin_notes` (text, nullable), `created_at` (timestamp)
