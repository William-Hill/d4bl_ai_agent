# Spec: Data Source Upload Processing Pipeline

**Issue:** [#190](https://github.com/William-Hill/d4bl_ai_agent/issues/190)
**Branch:** `feat/190-datasource-pipeline`
**Parent context:** v2 work deferred from PR #189 (staff contributor guide); sibling of #191 (document indexing, shipped in PR #195)

---

## Goal

When a staff contributor uploads a CSV or XLSX data source and declares column mappings, the file is parsed, validated, and normalized at upload time into `uploaded_datasets` (JSONB rows). An admin approves or rejects based on the declared mapping and a sampled preview. Approved uploads surface on `/explore` inside a single new **Staff Uploads** tab with a dataset picker — a user selects one approved upload at a time and views it through the same map / chart / table components every built-in source uses.

## Non-goals (deferred)

- Multi-metric uploads in a single file (one upload = one metric in v1).
- Aggregation hints (SUM vs AVG rollup) — v1 always averages.
- Race-value normalization across uploads (staff's "Black" vs built-in's "Black or African American").
- Supabase Storage persistence of the raw file.
- Re-upload merging / dataset versioning.
- Tract- and county-level drill-downs on `/explore` (state-only today, matches other sources).
- A "download CSV" button on `/explore` for approved staff datasets.

---

## Current state

### What exists today (from PR #195)

- `uploads` table (`upload_type` ENUM includes `datasource`; `status` ENUM includes `pending_review`, `approved`, `rejected`, `processing`, `live`, `indexed`, `processing_failed`).
- `uploaded_datasets` table with `{id, upload_id FK, row_index, data JSONB, UNIQUE(upload_id, row_index)}` — empty today.
- `POST /api/admin/uploads/datasource` accepts file + metadata but does no parsing; upload is stored with `file_path = NULL`.
- `PATCH /api/admin/uploads/{upload_id}/review` already handles non-document uploads with a pure status flip to `approved` (`src/d4bl/app/upload_routes.py`).
- Admin review UI: `ReviewQueue.tsx`, `ReviewDetail.tsx`, `UploadHistory.tsx` — already surface datasource uploads with status filtering.
- `/explore` page driven by `DataSourceConfig` entries (`ui-nextjs/lib/explore-config.ts`), each pointing at a typed endpoint returning `ExploreResponse` `{rows, national_average, available_metrics, available_years, available_races}` with `ExploreRow = {state_fips, state_name, value, metric, year, race?}`.
- Guide page Section 1 (`ui-nextjs/app/guide/page.tsx`) says post-approval processing is "planned for a follow-up release."

### What is missing

- CSV / XLSX parser + validator.
- Declared column mapping surface on the upload form.
- Normalization into `uploaded_datasets`.
- A Staff Uploads tab + picker on `/explore`.
- An endpoint that serves approved staff uploads in the standard `ExploreResponse` shape.
- Guide copy that accurately describes shipped behavior.

---

## Design decisions (pinned)

### 1. Column mapping is declared, not detected

Contributors explicitly declare `geo_column`, `metric_value_column`, `metric_name`, and optionally `race_column` / `year_column` on the upload form. Admin review is honest about what will land on `/explore`; failures surface immediately instead of as silent auto-detection mistakes.

### 2. Parse at upload, not at approval

The document flow in PR #195 stashes extracted text in `metadata.full_text` at upload time and materializes chunks on approval. Tabular uploads write straight to `uploaded_datasets` at upload time because (a) `uploaded_datasets` exists for exactly this purpose, (b) multi-megabyte row payloads do not fit comfortably in JSONB metadata, and (c) approval becomes a trivial status flip. Rejection keeps dataset rows (filtered out by status) instead of deleting them — matches the document flow's cost profile.

### 3. Single "Staff Uploads" tab on `/explore` with a dataset picker

One new `DataSourceConfig` entry, one new endpoint, one new picker component. Keeps curated vs staff data visibly distinct (matching the trust model) and scales cleanly as approvals accumulate. The alternative — one tab per approved upload generated dynamically — would unbound the tab bar and push `DATA_SOURCES` from a static import to a runtime fetch.

### 4. One metric per upload

Each `Upload` represents one metric. A CSV with five metric columns = five uploads. Keeps the form small, the row shape tight, and admin review legible. Multi-metric uploads are a follow-up if pain materializes.

---

## Data model

### No schema migrations

`uploads`, `uploaded_datasets`, `upload_type` ENUM, and `upload_status` ENUM are all already in the shape this pipeline needs.

### `uploads.metadata_` shape (datasource uploads)

```json
{
  "source_name": "County Eviction Filing Rates 2023",
  "description": "Filing rates per 1000 renter households...",
  "geographic_level": "county",
  "data_year": 2023,
  "source_url": "https://evictionlab.org/...",
  "category_tags": ["housing", "eviction"],
  "mapping": {
    "geo_column": "county_fips",
    "metric_value_column": "filing_rate",
    "metric_name": "eviction_filing_rate",
    "race_column": "race",
    "year_column": null
  },
  "row_count": 3142,
  "preview_rows": [ /* first 20 normalized rows for admin review */ ]
}
```

### `uploaded_datasets.data` JSONB row shape

```json
{
  "geo_fips": "13121",
  "state_fips": "13",
  "race": "Black",
  "year": 2023,
  "value": 14.3
}
```

`metric_name` is stored once on `uploads.metadata_.mapping.metric_name` and joined into the explore response, not duplicated per row.

### Derived fields

- `state_fips = geo_fips[:2]` — works for state (2-digit), county (5-digit), and tract (11-digit) FIPS.
- `year` — from `year_column` if set, else `data_year` for all rows.
- `race` — raw value from `race_column` passed through unchanged (null when no race column).

### Validation rules (any failure → 422, no DB writes)

1. Declared `geo_column`, `metric_value_column`, and (if set) `race_column` / `year_column` must exist as headers.
2. `metric_name` must match `^[a-z0-9_]+$` (snake_case, 1–64 chars).
3. `geo_column` values must parse into a 2-digit state FIPS prefix; rows with unparseable geo are dropped. If >10% of rows fail, raise.
4. `metric_value_column` must yield a float in ≥90% of non-empty rows. Coercion pipeline: `float(x.replace(',', '').rstrip('%').strip())`. Rows that still fail are dropped. If <90% succeed, raise.
5. `year_column` (if set) must parse to a 4-digit integer between 1900 and current year + 1.
6. After dropping invalid rows, at least 10 valid rows must remain; otherwise raise.

Dropped-row counts are returned in 422 detail so the contributor sees exactly what was discarded.

---

## End-to-end flow

```
[Contributor fills upload form]
   file + source_name + geo_column + metric_value_column
   + metric_name + race_column? + year_column? + data_year
        │
        ▼
[POST /api/admin/uploads/datasource]
   1. Validate extension, size, form fields (existing)
   2. Parse CSV/XLSX rows in asyncio.to_thread
   3. Validate declared columns exist in header
   4. Normalize each row → {geo_fips, state_fips, race?, year, value}
   5. On parse/validate error → 422, no DB write
   6. Insert Upload row (status=pending_review)
   7. Bulk-insert parsed rows into uploaded_datasets (same transaction)
        │
        ▼
[Admin opens review queue]
   - Sees declared mapping, metric_name, row count, sample preview
   - Approves → status = 'approved' (pure flip, no processing)
   - Rejects → status = 'rejected' (rows remain, filtered out of /explore)
        │
        ▼
[User visits /explore]
   - New "Staff Uploads" tab
   - Dataset picker loads approved uploads
   - Selecting one hits /api/explore/staff-uploads?upload_id=<uuid>
   - Returns ExploreResponse — reuses StateMap, RacialGapChart, DataTable
```

---

## Backend

### New module: `src/d4bl/services/datasource_processing/`

Mirrors the layout of `document_processing/`. Pure functions — no DB session, no ORM.

- `__init__.py`
- `parser.py` — `parse_datasource_file(content: bytes, ext: str, mapping: MappingConfig) -> ParseResult`. `ParseResult = {normalized_rows, row_count, dropped_counts, preview_rows}`. Raises `DatasourceParseError` on validation failures with structured `detail` payload.
- `validation.py` — pure validation helpers (column-exists, FIPS derivation, numeric coercion). Isolated for unit testing without IO.

`MappingConfig` is a small dataclass shared between the upload endpoint and the parser.

### Modified: `POST /api/admin/uploads/datasource`

Add five new form fields: `geo_column`, `metric_value_column`, `metric_name` (required), `race_column`, `year_column` (optional). Flow:

1. Existing extension / size / auth checks unchanged.
2. `await asyncio.to_thread(parse_datasource_file, content, ext, mapping)` — parse in worker thread to avoid blocking the event loop on large files.
3. On `DatasourceParseError` → `HTTPException(422, detail=<structured>)`. No DB writes.
4. Insert `Upload` with `status='pending_review'` and `metadata_` carrying mapping + `row_count` + `preview_rows[:20]`.
5. Bulk insert normalized rows into `uploaded_datasets` with `INSERT ... VALUES` executemany, chunked at 1000 rows per round-trip. Same transaction as the upload insert — all-or-nothing.
6. Return the standard `UploadResponse`.

### Review flow — no code change needed

`upload_routes.py:453-459` (PR #195) already handles non-document uploads with a pure status flip. For a datasource approval that is exactly the desired behavior. Rejection keeps `uploaded_datasets` rows; they are filtered out by status on the explore endpoint.

### New: `GET /api/explore/staff-uploads/available`

Returns the list of approved datasource uploads for the picker.

```json
[
  {
    "upload_id": "uuid",
    "source_name": "County Eviction Filing Rates 2023",
    "metric_name": "eviction_filing_rate",
    "geographic_level": "county",
    "data_year": 2023,
    "has_race": true,
    "row_count": 3142,
    "uploader_name": "Alice",
    "approved_at": "2026-04-18T15:00:00Z"
  }
]
```

Query: `SELECT uploads ... JOIN profiles ... WHERE upload_type = 'datasource' AND status = 'approved' ORDER BY reviewed_at DESC`. Auth: `get_current_user`.

### New: `GET /api/explore/staff-uploads?upload_id=<uuid>&state_fips=&race=&year=`

Returns `ExploreResponse`. Query pattern:

```sql
SELECT ud.data ->> 'state_fips'      AS state_fips,
       AVG((ud.data ->> 'value')::float) AS value,
       ud.data ->> 'race'             AS race,
       (ud.data ->> 'year')::int      AS year
FROM uploaded_datasets ud
JOIN uploads u ON u.id = ud.upload_id
WHERE u.id = :upload_id
  AND u.upload_type = 'datasource'
  AND u.status = 'approved'
  AND (:state_fips IS NULL OR ud.data ->> 'state_fips' = :state_fips)
  AND (:race IS NULL OR ud.data ->> 'race' = :race)
  AND (:year IS NULL OR (ud.data ->> 'year')::int = :year)
GROUP BY state_fips, race, year
```

The handler attaches `metric` from `uploads.metadata ->> 'mapping' -> 'metric_name'` to every row in the response. `state_name` comes from `FIPS_TO_STATE_NAME`. `available_metrics` is `[metric_name]`; `available_years` and `available_races` are derived from the returned rows.

Cache key includes `upload_id`. Note: `_check_cache_freshness` keys off `ingestion_runs` and does not automatically invalidate when an admin approves or rejects an upload. The in-process cache TTL applies. If review-state lag becomes user-visible, the review endpoint can call `explore_cache.invalidate_if_stale()` explicitly — tracked as a follow-up.

A missing `upload_id` returns 422. An `upload_id` that is not approved (pending, rejected, indexed-as-document, etc.) returns 404 "Not found or not approved."

### Dependencies

Add to `pyproject.toml` `dependencies`:

- `openpyxl>=3.1` — pure-Python XLSX reader, no native deps.

CSV uses stdlib `csv`. No pandas.

---

## Frontend

### Upload form — `ui-nextjs/components/admin/UploadDataSource.tsx`

Add a new "Column mapping" section with:

- **Geo column name** (required text) — helper: "The column containing state (2-digit), county (5-digit), or census tract (11-digit) FIPS codes."
- **Metric value column name** (required text) — helper: "The numeric column whose values will be plotted on the map."
- **Metric name** (required text) — helper: "Lowercase, snake_case, 1–64 characters. Becomes the metric identifier on /explore."
- **Has race column?** (checkbox → reveals race column name input).
- **Has year column?** (checkbox → reveals year column name input).

On 422, render the structured detail inline — listing missing columns and dropped-row counts — so contributors see why it failed without leaving the page. A small helper formats structured detail objects into a readable list.

### Admin review — `ui-nextjs/components/admin/ReviewDetail.tsx`

Add type-aware rendering for `upload_type === 'datasource'`:

- **Column mapping** subsection — `metadata.mapping` rendered as a labeled 2-column grid.
- **Preview** subsection — first 20 normalized rows from `metadata.preview_rows` as a bordered HTML table `state_fips | race | year | value`.
- **Dataset summary** line — `{row_count} rows · geographic level: {geographic_level} · data year: {data_year}`.

Other metadata fields use the existing generic renderer.

### Explore — new "Staff Uploads" tab

**`ui-nextjs/lib/explore-config.ts`** — append one `DataSourceConfig`:

```ts
{
  key: "staff-uploads",
  label: "Staff Uploads",
  accent: "#a29bfe",
  endpoint: "/api/explore/staff-uploads",
  hasRace: true,
  primaryFilterKey: "metric",
  primaryFilterLabel: "Dataset",
  description: "Approved data sources contributed by staff. Each dataset reflects its contributor's methodology and column definitions.",
  sourceUrl: "",
  hasData: true,
}
```

Add `METRIC_DIRECTION["staff-uploads"] = { default: null }`.

**New component `ui-nextjs/components/explore/StaffDatasetPicker.tsx`** — renders above the metric selector when the Staff Uploads tab is active. Fetches `/api/explore/staff-uploads/available` once and exposes a dropdown. Selection updates `filters.uploadId` and triggers a re-fetch. The selected upload's `has_race` flag is passed back to `page.tsx` so the race filter in `MetricFilterPanel` is hidden when the picked upload has no race column. `hasRace: true` on the static `DataSourceConfig` is the conservative default — the actual per-render visibility is gated on the picker's current selection.

**`ui-nextjs/app/explore/page.tsx`**:

1. Extend `ExploreFilters` with `uploadId: string | null`.
2. When `activeSource.key === 'staff-uploads'`, render `<StaffDatasetPicker />` and include `upload_id` in the fetch URL.
3. When Staff Uploads is active with no `uploadId`, render an instructional empty state ("Pick a dataset to view").
4. Extend localStorage persistence (`STORAGE_KEY = 'd4bl-explore-filters'`) to include `uploadId`.

`StateMap`, `RacialGapChart`, `DataTable`, `MetricFilterPanel`, `MapLegend` stay untouched — the response shape is identical.

### Guide — `ui-nextjs/app/guide/page.tsx` Section 1

**Replace** the "What happens after" paragraph:

> **What happens after:** When you upload, the platform parses your file immediately, validates the columns you mapped, and surfaces any errors back to you — so you know it landed cleanly before an admin ever sees it. An admin then reviews your declared mapping and a preview of the parsed rows. Once approved, your dataset appears under the **Staff Uploads** tab on `/explore`, where users can view it on the state map alongside built-in sources. Rejected uploads never reach `/explore`.

**Add** to "How to upload":

> You'll also declare which column is the geographic identifier, which column holds the metric value, and a short snake_case name for the metric. If your file has racial or yearly breakdowns, you can map those columns too.

**Update** "Example" to include a mapping example: `geo_column: county_fips, metric_value_column: premature_death_rate, metric_name: premature_death_rate, race_column: race`.

---

## Error handling and edge cases

| Stage | Failure | HTTP / UI effect |
|---|---|---|
| Upload, pre-parse | Bad extension / empty / oversize | 400 (existing) |
| Upload, parse | Declared column not in header | 422 `{missing_columns: [...]}` |
| Upload, parse | `metric_name` regex fail | 422 `{field: "metric_name", reason: "..."}` |
| Upload, normalize | >10% rows have unparseable FIPS | 422 `{dropped: {reason: "bad_fips", count, sample}}` |
| Upload, normalize | <90% of value rows are numeric | 422 `{dropped: {reason: "non_numeric", count, sample}}` |
| Upload, normalize | <10 valid rows post-drop | 422 `{reason: "too_few_rows", valid: N}` |
| Upload, insert | DB error mid-transaction | 500; rollback leaves no partial state |
| Review | Admin approves / rejects | No change — status flip only |
| Explore query | `upload_id` is not approved | 404 "Not found or not approved" |
| Explore query | `upload_id` param omitted on main endpoint | 422 `"upload_id is required"` |

Edge cases:

- **Rejected upload's orphan rows.** Kept for audit; filtered out by status on explore.
- **Re-upload of the same file.** Creates a new `Upload` and its own dataset rows; explicit by design.
- **Large files (~50MB, ~500k rows).** Parse runs in `asyncio.to_thread`; bulk insert chunked at 1000 rows per round-trip.
- **Numeric columns with `%`, commas, or whitespace.** Coerced by the strict pipeline; unrecoverable rows dropped and counted.
- **Unicode / BOM in CSV headers.** `utf-8-sig` encoding; header names trimmed before matching.
- **Multi-year files with no year column.** All rows get `data_year`; admin preview flags this.
- **State-level view from tract-level CSV.** Explore endpoint averages values when grouping by state_fips. Aggregation hint (SUM vs AVG) is a follow-up.

---

## Testing strategy

### Unit — `tests/test_datasource_processing.py` (new)

- Parse a valid CSV fixture → asserts normalized shape, row count, FIPS derivation.
- Same with XLSX fixture.
- Missing declared columns → `DatasourceParseError` with `missing_columns` populated.
- Invalid `metric_name` → `DatasourceParseError`.
- Bad-FIPS rate > 10% → error; ≤ 10% → rows dropped, count reported.
- Non-numeric rate > 10% → error; ≤ 10% → dropped.
- Year column out of range → rows dropped.
- Percent-sign / comma value coercion → success.
- Fewer than 10 valid rows → error.
- BOM / UTF-8 encoding → success.

### Integration — `tests/test_upload_api.py` (extend)

- `POST /api/admin/uploads/datasource` with valid CSV + mapping → 200, one `Upload` row + N `uploaded_datasets` rows created in one transaction.
- Same call with bad mapping → 422; assert row counts before/after are unchanged.
- `PATCH /.../review` with `action=approve` → status flips to `approved`; no Ollama / vector IO.
- Reject flow: upload row stays, `status=rejected`, dataset rows preserved.

### Integration — `tests/test_explore_api.py` (extend)

- `GET /api/explore/staff-uploads/available` returns only approved datasource uploads.
- `GET /api/explore/staff-uploads?upload_id=<uuid>` returns `ExploreResponse` matching fixture.
- Pending or rejected upload_id → 404.
- Filters (`state_fips`, `race`, `year`) narrow results correctly.
- County-level fixture aggregates to state-level values (averaged).
- Invalid `upload_id` UUID → 422.

### Frontend — manual QA checklist (for PR description)

- Upload a small valid CSV; see success state.
- Upload with a typo in `geo_column` → see inline 422 detail.
- Approve as admin; confirm it appears in `/explore → Staff Uploads` picker.
- Select the upload; confirm map renders and chart + table work.
- Reject another upload; confirm it never appears in the picker.
- Refresh with a staff upload selected; confirm localStorage round-trips `uploadId`.

---

## Critical files

| Path | Role |
| --- | --- |
| `src/d4bl/app/upload_routes.py` | Extend datasource upload endpoint with mapping fields + parse + bulk insert |
| `src/d4bl/app/api.py` | Register two new `/api/explore/staff-uploads` endpoints |
| `src/d4bl/services/datasource_processing/` | **New package** — parser, validation |
| `src/d4bl/app/schemas.py` | Add request schema fields for mapping; no response schema change (reuses `ExploreResponse`) |
| `pyproject.toml` | Add `openpyxl>=3.1` |
| `ui-nextjs/components/admin/UploadDataSource.tsx` | Add mapping fields + 422 detail rendering |
| `ui-nextjs/components/admin/ReviewDetail.tsx` | Type-aware rendering for datasource metadata |
| `ui-nextjs/components/explore/StaffDatasetPicker.tsx` | **New** — dataset dropdown |
| `ui-nextjs/lib/explore-config.ts` | Add staff-uploads `DataSourceConfig` + metric direction entry |
| `ui-nextjs/app/explore/page.tsx` | Wire picker, extend filters + persistence |
| `ui-nextjs/app/guide/page.tsx` | Section 1 copy update |
| `tests/test_datasource_processing.py` | **New** — parser/validation unit tests |
| `tests/test_upload_api.py` | **Extend** — upload + review integration tests |
| `tests/test_explore_api.py` | **Extend** — staff-uploads endpoint tests |

---

## Risks

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Large upload blocks worker | Medium | `asyncio.to_thread` for parse; chunked bulk insert |
| Malformed CSV crashes parser | Medium | All exceptions caught in parser, converted to structured `DatasourceParseError` |
| Admin approves a mapping they didn't fully understand | Low | Preview shows first 20 normalized rows — admin sees exactly what `/explore` will show |
| `AVG` rollup is wrong for count-type metrics | Medium | Documented limitation; aggregation hint is a follow-up |
| Rejected uploads leave dataset rows in storage | Low | Filtered out by status; cleanup is a follow-up |
| `openpyxl` dep bloat | Low | Pure-Python, narrow-scope lib; matches PR #195's approach of adding small purpose-specific deps |

---

## Questions for review

1. Are you comfortable deferring multi-metric uploads and aggregation hints (SUM vs AVG) to follow-ups?
2. Should the empty-state copy on the Staff Uploads tab ("Pick a dataset to view") offer a link to the guide for contributors?
3. Any concerns about leaving `uploaded_datasets` rows around for rejected uploads? Alternative: cascade-delete on rejection.
