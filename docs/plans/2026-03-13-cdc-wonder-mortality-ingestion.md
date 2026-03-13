# CDC WONDER Mortality Data Ingestion Design

**Issue:** #91
**Date:** 2026-03-13
**Status:** Approved

## Overview

Ingest CDC mortality data via the SODA API on data.cdc.gov. Two separate Dagster assets write to a single unified `cdc_mortality` table, following the same pattern as Census ACS (multiple geography levels in one table).

## Data Sources

### Asset 1: `cdc_mortality_state`
- **Dataset:** NCHS Leading Causes of Death (`bi63-dtpu`)
- **Endpoint:** `https://data.cdc.gov/resource/bi63-dtpu.json`
- **Auth:** None (public SODA API)
- **Coverage:** State-level, 10 leading causes, 1999–2017
- **Race:** Not available (all rows = `"total"`)
- **Pagination:** `$limit=50000&$offset=N`
- **Schedule:** Annual (`0 0 1 1 *`)

### Asset 2: `cdc_mortality_national_race`
- **Dataset:** AH Excess Deaths by Sex, Age, Race and Hispanic Origin (`m74n-4hbs`)
- **Endpoint:** `https://data.cdc.gov/resource/m74n-4hbs.json`
- **Auth:** None (public SODA API)
- **Coverage:** National-level, all-cause + COVID, 2015–2023, weekly granularity aggregated to annual
- **Race:** 7 categories mapped to standard D4BL values
- **Schedule:** Quarterly (`0 0 1 */3 *`)

## Why SODA API

CDC WONDER's web interface has the richest mortality data (county-level, race-disaggregated, multi-cause), but:
- The WONDER XML API restricts queries to national-level grouping only
- Manual CSV exports break the project's automated, reproducible ingestion pattern
- All other D4BL assets use official public APIs with recordable source URLs

The SODA API provides programmatic, stable, reproducible access that matches our data governance model. Limitations are documented via bias flags.

## Schema

```sql
CREATE TABLE cdc_mortality (
    id UUID PRIMARY KEY,
    geo_id VARCHAR(20) NOT NULL,
    geography_type VARCHAR(10) NOT NULL,  -- 'state' or 'national'
    state_fips VARCHAR(2),
    state_name VARCHAR(100),
    year INTEGER NOT NULL,
    cause_of_death VARCHAR(200) NOT NULL,
    race VARCHAR(100) NOT NULL DEFAULT 'total',
    deaths INTEGER,
    age_adjusted_rate REAL,
    UNIQUE(geo_id, year, cause_of_death, race)
);

CREATE INDEX ix_cdc_mortality_state_year
    ON cdc_mortality(state_fips, year, cause_of_death, race);
CREATE INDEX ix_cdc_mortality_geo_type
    ON cdc_mortality(geography_type, year);
```

- `geo_id`: State FIPS code (e.g., `"01"`) or `"US"` for national
- `geography_type`: `"state"` or `"national"`
- Race defaults to `"total"` for state asset (no race disaggregation available)
- Unique constraint enables idempotent `ON CONFLICT DO UPDATE` upserts
- Matches `CdcHealthOutcome` and `CensusIndicator` patterns

## Race Mapping (National Asset)

| SODA Value | D4BL Standard |
|---|---|
| Non-Hispanic White | white |
| Non-Hispanic Black | black |
| Hispanic | hispanic |
| Non-Hispanic Asian | asian |
| Non-Hispanic American Indian or Alaska Native | native_american |
| Other/More than one race | multiracial |
| All | total |

## Asset Implementation

Both assets follow the standard Dagster asset pattern:
- `@asset(group_name="apis", required_resource_keys={"db_url", "langfuse"})`
- Async with `aiohttp` for HTTP + `AsyncSession` for DB
- Langfuse tracing with download/parse/store spans
- `uuid.uuid5(NAMESPACE_URL, ...)` for deterministic record IDs
- `ON CONFLICT DO UPDATE` for idempotent upserts
- Lineage recording via `build_lineage_record` / `write_lineage_batch`
- Bias flags in `MaterializeResult` metadata

### State Asset Specifics
- Paginates SODA results with `$limit=50000`
- Maps state names to FIPS codes
- Fields: `year`, `state`, `cause_name`, `deaths`, `aadr` (age-adjusted death rate)

### National Race Asset Specifics
- Fetches weekly data, aggregates to annual totals per race
- Maps SODA race values to D4BL standard categories
- `geo_id = "US"`, `geography_type = "national"`
- `cause_of_death = "all_causes"` (may include COVID-specific breakout)

## Bias Flags

- State asset: `"race disaggregation not available from this source"`
- State asset: `"data ends 2017; source has not been updated since"`
- National race asset: `"national-level only; no state/county breakdown by race"`
- National race asset: `"counts under 10 suppressed by NCHS"`

## File Changes

| File | Change |
|---|---|
| `src/d4bl/infra/database.py` | Add `CdcMortality` SQLAlchemy model |
| `dagster/d4bl_pipelines/assets/apis/cdc_mortality.py` | New file with both assets |
| `dagster/d4bl_pipelines/assets/apis/__init__.py` | Register imports |
| `dagster/d4bl_pipelines/assets/__init__.py` | Register imports |
| `dagster/d4bl_pipelines/schedules.py` | Add cron entries |

## Testing

- Unit test: state name → FIPS mapping
- Unit test: race value normalization
- Unit test: weekly-to-annual aggregation logic
- Integration test: hit real SODA API with small `$limit`
