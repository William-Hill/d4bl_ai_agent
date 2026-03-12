# CDC PLACES Race Disaggregation via ACS Overlay

**Issue**: #75
**Date**: 2026-03-12

## Problem

CDC PLACES provides health outcome estimates (diabetes, obesity, depression, etc.) at county and tract levels but does not disaggregate by race. Cross-referencing with Census ACS demographic data enables race-weighted health outcome estimates for equity analysis.

## Architecture

```
CDC PLACES (county)  +  Census ACS (county)  →  Race-weighted estimates (county)
CDC PLACES (tract)   +  Census ACS (tract)   →  Race-weighted estimates (tract)
```

**Computation** (proportional attribution): For each geography, for each health measure, for each race:

```
estimated_value = health_rate × (race_population / total_population)
```

Example: If Cook County has a 12% diabetes rate and the Black population is 24% of total, the estimated Black diabetes burden = 12% × 0.24 = 2.88% (population-weighted contribution).

## PR Breakdown

### PR 1: CDC PLACES Tract-Level Ingestion

**Files**:
- `dagster/d4bl_pipelines/assets/apis/cdc_places.py` — add `cdc_places_tract_health` asset
- `dagster/d4bl_pipelines/schedules.py` — add schedule entry
- `dagster/tests/test_cdc_places_asset.py` — add tract-level tests

**Details**:
- Fetch from SODA API: `https://data.cdc.gov/resource/cwsq-ngmh.json`
- Same 10 measures as county asset
- Reuse existing `CdcHealthOutcome` model with `geography_type = 'tract'`
- Paginate with limit=5000, iterate per-measure
- ~83,500 tracts × 10 measures = ~835,000 records
- Add lineage recording (county asset is missing it too — add for both)
- Upsert on (fips_code, year, measure, data_value_type)

### PR 2: ACS Race Overlay Computation Asset

**Files**:
- `src/d4bl/infra/database.py` — add `CdcAcsRaceEstimate` model
- `supabase/migrations/YYYYMMDD_add_cdc_acs_race_estimates.sql` — migration
- `dagster/d4bl_pipelines/assets/apis/cdc_acs_overlay.py` — new overlay asset
- `dagster/d4bl_pipelines/assets/apis/__init__.py` — register
- `dagster/d4bl_pipelines/assets/__init__.py` — register
- `dagster/d4bl_pipelines/schedules.py` — add schedule
- `dagster/tests/test_cdc_acs_overlay.py` — tests

**New table `cdc_acs_race_estimates`**:
- `id` UUID PK
- `fips_code` VARCHAR(11) — county (5-digit) or tract (11-digit)
- `geography_type` VARCHAR(10) — 'county' or 'tract'
- `geography_name` VARCHAR(200)
- `state_fips` VARCHAR(2)
- `year` INTEGER
- `measure` VARCHAR(50) — CDC PLACES measure ID
- `race` VARCHAR(20) — black, white, hispanic, total
- `health_rate` FLOAT — raw CDC PLACES rate
- `race_population_share` FLOAT — race pop / total pop from ACS
- `estimated_value` FLOAT — health_rate × race_population_share
- `total_population` INTEGER — from ACS
- `confidence_low` FLOAT — from CDC
- `confidence_high` FLOAT — from CDC
- Unique constraint: (fips_code, year, measure, race)
- Indexes: state_fips, measure, year, race, geography_type

**Asset logic**:
1. Query `cdc_health_outcomes` for all county + tract records for target year
2. Query `census_indicators` for population data (total + by race) at matching geography
3. For each CDC record, for each race: compute `health_rate × (race_pop / total_pop)`
4. Upsert into `cdc_acs_race_estimates`
5. Record lineage with transformation steps: `["join_cdc_acs", "compute_proportional_attribution", "upsert"]`
6. Bias flags: `["computed estimate via proportional attribution, not direct measurement", "assumes uniform health rate across racial groups within geography"]`

**Dependencies**: Runs after both `cdc_places_health` (or `cdc_places_tract_health`) and `census_acs_county_indicators` (or `census_acs_tract_indicators`).

### PR 3: Backend API Endpoint

**Files**:
- `src/d4bl/app/api.py` — add `/api/explore/cdc-race` endpoint
- `src/d4bl/app/schemas.py` — reuse `ExploreResponse`

**Endpoint**: `GET /api/explore/cdc-race`
- Params: `state_fips`, `measure`, `race`, `year`, `geography_type`, `limit`
- Queries `cdc_acs_race_estimates` table
- Returns `ExploreResponse` with `available_races`, `available_metrics`, `available_years`

### PR 4: Frontend Race Selector for CDC

**Files**:
- `ui-nextjs/lib/explore-config.ts` — update CDC config or add new `cdc-race` source
- `ui-nextjs/app/explore/page.tsx` — wire up race filter for CDC race endpoint

**Details**:
- Add `cdc-race` data source entry with `hasRace: true`, endpoint `/api/explore/cdc-race`
- When race data is available, show `RacialGapChart` instead of `StateVsNationalChart`
- Keep original CDC tab for raw PLACES data; add new tab for race-disaggregated view

## Methodology Notes

- **Proportional attribution** is a simplified model. It assumes the health rate is uniform across racial groups within each geography. This is a known limitation.
- All computed records carry bias flags documenting this assumption.
- Future enhancement: use BRFSS microdata or other race-stratified health surveys for validation/calibration.

## Schedule

- Overlay asset depends on CDC PLACES and Census ACS data being present
- Run quarterly after CDC PLACES refresh: `0 6 1 */3 *` (6 AM on 1st of every 3rd month, after PLACES runs at midnight)
