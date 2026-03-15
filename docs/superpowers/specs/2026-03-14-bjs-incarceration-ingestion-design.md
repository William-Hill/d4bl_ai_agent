# BJS Incarceration Data Ingestion Design

**Issue**: #92 — Add DOJ Bureau of Justice Statistics incarceration ingestion
**Date**: 2026-03-14
**Status**: Approved

## Overview

Ingest incarceration data from the Bureau of Justice Statistics (BJS) "Prisoners in 20XX" annual publication into the existing `bjs_incarceration` table. The data covers sentenced prisoner populations, imprisonment rates, admissions, and releases — broken down by state, race, sex, and year. This is critical for criminal justice equity analysis in D4BL.

## Data Source

- **Publisher**: Bureau of Justice Statistics, U.S. Department of Justice
- **Publication**: "Prisoners in 2023 – Statistical Tables" (NCJ 310197)
- **Download URL pattern**: `https://bjs.ojp.gov/document/p{YY}st.zip`
  - Example: `https://bjs.ojp.gov/document/p23st.zip` for 2023
- **Format**: Zip archive containing 25+ CSV files
- **Auth**: None (public download)
- **Update frequency**: Annual (published ~September following the data year)

## Tables to Ingest

Six CSV files from the zip, covering all available data with race and/or state breakdowns:

| CSV File | Table | Granularity | Race | Sex | Years | Metrics |
|----------|-------|-------------|------|-----|-------|---------|
| `p{YY}stat01.csv` | Appendix T1 | Per-state | Yes | No | Current year | Total prisoner counts by race |
| `p{YY}stt03.csv` | Table 3 | National | Yes | Yes | 2013–current | Sentenced prisoner counts |
| `p{YY}stt05.csv` | Table 5 | National | Yes | Yes | 2013–current | Imprisonment rates (all ages, per 100k) |
| `p{YY}stt06.csv` | Table 6 | National | Yes | Yes | 2013–current | Imprisonment rates (adults, per 100k) |
| `p{YY}stt08.csv` | Table 8 | Per-state | No | No | 2 years | Admissions (total, new court, violations) |
| `p{YY}stt09.csv` | Table 9 | Per-state | No | No | 2 years | Releases (total, unconditional, conditional, deaths) |

## Existing Infrastructure

### Database Table (already exists)

Migration `20260313000001_add_expanded_data_tables.sql` already defines:

```sql
CREATE TABLE IF NOT EXISTS bjs_incarceration (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    state_abbrev VARCHAR(2) NOT NULL,
    state_name VARCHAR(50),
    year INTEGER NOT NULL,
    facility_type VARCHAR(20) NOT NULL,
    metric VARCHAR(100) NOT NULL,
    race VARCHAR(50) NOT NULL,
    gender VARCHAR(20) NOT NULL,
    value FLOAT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_bjs_incarceration_key
    ON bjs_incarceration(state_abbrev, year, facility_type, metric, race, gender);
```

### SQLAlchemy Model (already exists)

`BjsIncarceration` in `src/d4bl/infra/database.py` mirrors the table schema.

## Schema Mapping

All CSV data normalizes into the existing `metric` + `value` pattern:

| Field | Values |
|-------|--------|
| `state_abbrev` | `"US"` for national-level data, 2-letter state abbreviation for state-level |
| `state_name` | `"United States"` or full state name |
| `year` | 2013–2023 (varies by table) |
| `facility_type` | `"prison"` for all NPS data |
| `metric` | See Metric Catalog below |
| `race` | `"total"`, `"white"`, `"black"`, `"hispanic"`, `"aian"`, `"asian"` |
| `gender` | `"total"`, `"male"`, `"female"` |
| `value` | Numeric value (population count or rate per 100k) |

### Metric Catalog

From the ingested tables:

```
# Table 3 — Sentenced prisoner counts (national, by race × sex, 2013–2023)
sentenced_population
sentenced_population_federal
sentenced_population_state

# Table 5 — Imprisonment rates, all ages (national, by race × sex, 2013–2023)
imprisonment_rate_all_ages
imprisonment_rate_all_ages_federal
imprisonment_rate_all_ages_state

# Table 6 — Imprisonment rates, adults (national, by race × sex, 2013–2023)
imprisonment_rate_adult
imprisonment_rate_adult_federal
imprisonment_rate_adult_state

# Table 8 — Admissions (per-state, no race, 2022–2023)
admissions_total
admissions_new_court_commitment
admissions_supervision_violations

# Table 9 — Releases (per-state, no race, 2022–2023)
releases_total
releases_unconditional
releases_conditional
releases_deaths

# Appendix Table 1 — Total prisoners by race (per-state, 2023)
total_population
```

## CSV Parsing

### Header Structure

All BJS CSVs share this format:
- **Rows 1–8**: Metadata (bureau name, filename, table title, report title, data source, authors, contact, version date)
- **Row 9**: Blank
- **Row 10**: Table title (repeat)
- **Row 11**: Column headers (with sub-headers on some tables)
- **Rows 12+**: Data rows
- **Bottom rows**: "Percent change" summary, notes, footnotes, source citation

### Parsing Challenges and Mitigations

| Challenge | Example | Mitigation |
|-----------|---------|------------|
| Comma-formatted numbers in quotes | `"1,520,403"` | Strip commas before float conversion |
| Empty interleaving columns | `2013,,"1,520,403",,` | Skip empty columns |
| Footnote markers on jurisdictions | `Alabama/d`, `"Illinois/d,g"` | Regex strip `/[a-z,]+` suffix |
| Not-reported values | `/` | Skip record |
| Not-applicable values | `~` | Skip record |
| Percent change rows | `Percent change,,,` | Stop parsing at "Percent change" |
| Note/source footer rows | `Note:...`, `Source:...` | Stop at rows starting with note markers |
| Regional grouping rows | `Northeast`, `Midwest` | Skip rows that are region names |
| Federal row prefix | `Federal/c` | Map to state_abbrev `"US"` with `_federal` metric suffix |

### Default Dimension Values

When a CSV table does not include a dimension, use these defaults:
- **Tables without sex breakdown** (Appendix T1, Tables 8, 9): `gender = "total"`
- **Tables without race breakdown** (Tables 8, 9): `race = "total"`

### State Name to Abbreviation Mapping

Define a `STATE_NAME_TO_ABBREV` dict in the ingestion script mapping full state names (as they appear in the CSVs) to 2-letter abbreviations. The existing `STATE_FIPS` dict in `helpers.py` maps FIPS codes to state names but does not contain abbreviations, so a dedicated mapping is needed.

## Ingestion Script

### File: `scripts/ingestion/ingest_bjs_incarceration.py`

**Entry point**: `main() -> int` (returns total records upserted)

**Environment variables**:
- `DAGSTER_POSTGRES_URL` (required) — database connection
- `BJS_YEAR` (optional, default `2023`) — publication year to ingest

**Flow**:

```
1. Build download URL from BJS_YEAR
2. Download zip to tempfile
3. Extract to temp directory
4. For each target CSV:
   a. Read and skip header rows
   b. Parse data rows into normalized records
   c. Generate deterministic IDs via make_record_id("bjs", state, year, facility_type, metric, race, gender)
5. Upsert all records via upsert_batch()
6. Cleanup temp files
7. Return total record count
```

**Dependencies**: `httpx`, `psycopg2`, standard library (`csv`, `zipfile`, `tempfile`, `re`)

**Error handling**:
- If the zip download returns a non-200 status or 404, exit with a clear error message suggesting the URL pattern may have changed for that publication year.
- Set a 60-second timeout on the HTTP download.
- Skip individual records with unparseable values (`/`, `~`, `--`) with a warning, do not abort the entire table.

**Upsert SQL**:
```sql
INSERT INTO bjs_incarceration (id, state_abbrev, state_name, year, facility_type, metric, race, gender, value)
VALUES (%(id)s::UUID, %(state_abbrev)s, %(state_name)s, %(year)s, %(facility_type)s, %(metric)s, %(race)s, %(gender)s, %(value)s)
ON CONFLICT (state_abbrev, year, facility_type, metric, race, gender)
DO UPDATE SET value = EXCLUDED.value, state_name = EXCLUDED.state_name
```

## Dispatcher Registration

Add to `scripts/run_ingestion.py` SOURCES dict:

```python
"bjs": "ingest_bjs_incarceration",
```

Add `BJS_YEAR` to the year-forwarding logic alongside existing year env vars.

## Explore UI Integration

### Backend: New endpoint

Add `GET /api/explore/bjs` in `src/d4bl/app/api.py` following the existing pattern:
- Query `BjsIncarceration` model
- Filter by `state_fips` (convert state_abbrev to FIPS via existing `ABBREV_TO_FIPS` dict), `metric`, `race`, `year`
- **Gender handling**: Filter to `gender = "total"` by default for the explore endpoint. The gender dimension is unique to BJS among explore sources; exposing a gender filter in the UI can be a follow-up enhancement.
- **National rows**: Exclude rows with `state_abbrev = "US"` from the state map response. Use the national-level data for the `national_average` field in `ExploreResponse` when available (e.g., for `total_population`, use the U.S. total from the same metric).
- **Aggregation**: Since BJS data is already at the state level, no aggregation (AVG/SUM) is needed — return values directly.
- Return `ExploreResponse`
- Default metric: `total_population` (from Appendix Table 1)

### Frontend: New data source config

Add entry in `ui-nextjs/lib/explore-config.ts` matching the `DataSourceConfig` interface:

```typescript
{
  key: "bjs",
  label: "BJS Incarceration",
  accent: "#a29bfe",
  endpoint: "/api/explore/bjs",
  hasRace: true,
  primaryFilterKey: "metric",
  primaryFilterLabel: "Metric",
}
```

## Estimated Record Count

| Source | Calculation | Records |
|--------|------------|---------|
| Appendix T1 | ~52 jurisdictions x 6 races | ~312 |
| Table 3 | 11 years x (3 jurisdiction levels) x 6 races x 3 genders | ~594 |
| Table 5 | 11 years x (3 jurisdiction levels) x 6 races x 3 genders | ~594 |
| Table 6 | 11 years x (3 jurisdiction levels) x 6 races x 3 genders | ~594 |
| Table 8 | ~52 jurisdictions x 2 years x 3 metrics | ~312 |
| Table 9 | ~52 jurisdictions x 2 years x 4 metrics | ~416 |
| **Total** | | **~2,822** (upper bound) |

Note: Actual count may be lower as not all race/gender combinations exist for every year (e.g., AIAN disaggregation varies).

## Testing

- Run `python scripts/ingestion/ingest_bjs_incarceration.py` and verify record count
- Run `python scripts/run_ingestion.py --sources bjs` and verify dispatcher integration
- Verify idempotency by running twice and confirming no duplicate records
- Spot-check values against the PDF publication for accuracy

## Out of Scope

- **Supabase storage buckets** for raw CSV archival (follow-up ticket)
- **CSAT web tool** scraping (no API, fragile)
- **NACJD/ICPSR** archived datasets (requires auth, complex formats)
- **Tables without state or race breakdowns** (Tables 1, 2, 4, 7, 10-25) — can be added later if needed
- **Data lineage recording** — not implemented in any standalone ingestion script currently; can be added project-wide later
- **Gender filter in explore UI** — BJS is the only source with gender disaggregation; adding a gender filter control is a follow-up enhancement
