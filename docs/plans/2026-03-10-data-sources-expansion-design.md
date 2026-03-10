# Data Sources Expansion — 8 New Open Data Sources

**Date:** 2026-03-10
**Status:** Approved

## Goal

Add 8 new open data sources as hardcoded Dagster assets to populate the D4BL
platform with equity-focused data across criminal justice, health, housing,
labor, food access, education, environmental justice, and police violence.

## Architecture

Each source gets:
- A Dagster asset in `dagster/d4bl_pipelines/assets/apis/`
- A SQLAlchemy model (dedicated table) in `src/d4bl/infra/database.py`
- A Supabase migration to create the table
- Lineage recording and bias flags (consistent with Census ACS pattern)
- Graceful skip when API keys aren't configured

## Source → Table Mapping

| # | Source | Asset Name | Table | Auth |
|---|--------|-----------|-------|------|
| 1 | CDC PLACES | `cdc_places_health` | `cdc_health_outcomes` | None |
| 2 | EPA EJScreen | `epa_ejscreen` | `epa_environmental_justice` | None |
| 3 | FBI Crime Data Explorer | `fbi_ucr_crime` | `fbi_crime_stats` | `FBI_API_KEY` (required) |
| 4 | BLS Labor Stats | `bls_labor_stats` | `bls_labor_statistics` | `BLS_API_KEY` (optional) |
| 5 | HUD Fair Housing | `hud_fair_housing` | `hud_fair_housing` | None |
| 6 | USDA Food Access | `usda_food_access` | `usda_food_access` | None |
| 7 | DOE Civil Rights | `doe_civil_rights` | `doe_civil_rights` | None |
| 8 | Mapping Police Violence | `mapping_police_violence` | `police_violence_incidents` | None |

## Table Schemas

### 1. `cdc_health_outcomes`
Health outcomes and risk factors by county/tract from CDC PLACES.

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| fips_code | VARCHAR(11) | State/county/tract FIPS |
| geography_type | VARCHAR(10) | state, county, tract |
| geography_name | TEXT | |
| state_fips | VARCHAR(2) | |
| year | INTEGER | |
| measure | VARCHAR(200) | e.g. "diabetes", "mental_health" |
| category | VARCHAR(100) | e.g. "health_outcomes", "prevention" |
| data_value | FLOAT | Crude or age-adjusted prevalence |
| data_value_type | VARCHAR(50) | "crude_prevalence", "age_adjusted" |
| low_confidence_limit | FLOAT | nullable |
| high_confidence_limit | FLOAT | nullable |
| total_population | INTEGER | nullable |
| created_at | TIMESTAMP | |

**Unique:** `(fips_code, year, measure, data_value_type)`

### 2. `epa_environmental_justice`
Environmental justice screening indicators by census tract from EPA EJScreen.

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| tract_fips | VARCHAR(11) | Census tract FIPS |
| state_fips | VARCHAR(2) | |
| state_name | VARCHAR(50) | |
| year | INTEGER | |
| indicator | VARCHAR(200) | e.g. "pm25", "ozone", "lead_paint" |
| raw_value | FLOAT | |
| percentile_state | FLOAT | State-level percentile |
| percentile_national | FLOAT | National percentile |
| demographic_index | FLOAT | nullable, EJ index |
| population | INTEGER | nullable |
| minority_pct | FLOAT | nullable |
| low_income_pct | FLOAT | nullable |
| created_at | TIMESTAMP | |

**Unique:** `(tract_fips, year, indicator)`

### 3. `fbi_crime_stats`
Use-of-force, hate crimes, and arrest data by race from FBI Crime Data Explorer.

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| state_abbrev | VARCHAR(2) | |
| state_name | VARCHAR(50) | |
| offense | VARCHAR(200) | e.g. "aggravated_assault", "hate_crime" |
| category | VARCHAR(100) | "arrests", "hate_crimes", "use_of_force" |
| race | VARCHAR(50) | |
| ethnicity | VARCHAR(50) | nullable |
| year | INTEGER | |
| value | FLOAT | Count or rate |
| population | INTEGER | nullable |
| created_at | TIMESTAMP | |

**Unique:** `(state_abbrev, offense, race, year, category)`

### 4. `bls_labor_statistics`
Unemployment, wages, and labor force participation by race.

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| series_id | VARCHAR(50) | BLS series identifier |
| state_fips | VARCHAR(2) | nullable (some series are national) |
| state_name | VARCHAR(50) | nullable |
| metric | VARCHAR(200) | "unemployment_rate", "median_weekly_earnings" |
| race | VARCHAR(50) | |
| year | INTEGER | |
| period | VARCHAR(10) | "M01"–"M12" or "Q01"–"Q04" or "A01" |
| value | FLOAT | |
| footnotes | TEXT | nullable |
| created_at | TIMESTAMP | |

**Unique:** `(series_id, year, period)`

### 5. `hud_fair_housing`
Fair housing complaints and AFFH indicators.

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| fips_code | VARCHAR(11) | |
| geography_type | VARCHAR(10) | state, county, place |
| geography_name | TEXT | |
| state_fips | VARCHAR(2) | |
| year | INTEGER | |
| indicator | VARCHAR(200) | e.g. "dissimilarity_index", "segregation_index" |
| category | VARCHAR(100) | "segregation", "discrimination", "access" |
| value | FLOAT | |
| race_group_a | VARCHAR(50) | nullable, first comparison group |
| race_group_b | VARCHAR(50) | nullable, second comparison group |
| created_at | TIMESTAMP | |

**Unique:** `(fips_code, year, indicator, race_group_a, race_group_b)`

### 6. `usda_food_access`
Food desert and SNAP data by census tract.

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| tract_fips | VARCHAR(11) | Census tract FIPS |
| state_fips | VARCHAR(2) | |
| county_fips | VARCHAR(5) | |
| state_name | VARCHAR(50) | |
| county_name | VARCHAR(100) | |
| year | INTEGER | |
| indicator | VARCHAR(200) | e.g. "low_access_1mi", "snap_participation" |
| value | FLOAT | |
| urban_rural | VARCHAR(10) | "urban" or "rural" |
| population | INTEGER | nullable |
| poverty_rate | FLOAT | nullable |
| median_income | FLOAT | nullable |
| created_at | TIMESTAMP | |

**Unique:** `(tract_fips, year, indicator)`

### 7. `doe_civil_rights`
School discipline, AP access, and resource equity by race from DOE CRDC.

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| district_id | VARCHAR(20) | LEA/district identifier |
| district_name | TEXT | |
| state | VARCHAR(2) | |
| state_name | VARCHAR(50) | |
| school_year | VARCHAR(9) | e.g. "2020-2021" |
| metric | VARCHAR(200) | e.g. "suspensions", "ap_enrollment" |
| category | VARCHAR(100) | "discipline", "access", "resources" |
| race | VARCHAR(50) | |
| value | FLOAT | Count or rate |
| total_enrollment | INTEGER | nullable |
| created_at | TIMESTAMP | |

**Unique:** `(district_id, school_year, metric, race)`

### 8. `police_violence_incidents`
Police violence incident data from Mapping Police Violence.

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| incident_id | VARCHAR(100) | Source-assigned ID |
| date | DATE | |
| year | INTEGER | |
| state | VARCHAR(2) | |
| city | VARCHAR(200) | |
| county | VARCHAR(200) | nullable |
| race | VARCHAR(50) | |
| age | INTEGER | nullable |
| gender | VARCHAR(20) | nullable |
| armed_status | VARCHAR(100) | nullable |
| cause_of_death | VARCHAR(200) | nullable |
| circumstances | TEXT | nullable |
| criminal_charges | VARCHAR(200) | nullable, against officer |
| agency | VARCHAR(200) | nullable |
| source_url | TEXT | nullable |
| created_at | TIMESTAMP | |

**Unique:** `(incident_id)`

## API Details

1. **CDC PLACES** — SODA API at `https://data.cdc.gov/resource/swc5-untb.json`
   - Supports `$where`, `$limit`, `$offset` for pagination
   - No auth required

2. **EPA EJScreen** — REST at `https://ejscreen.epa.gov/mapper/ejscreenRESTbroker.aspx`
   - Returns JSON per geography, query by FIPS
   - No auth required

3. **FBI Crime Data Explorer** — `https://api.usa.gov/crime/fbi/cde/`
   - Requires `FBI_API_KEY` env var (free registration)
   - Endpoints: `/arrest/states/`, `/hate-crime/`, `/use-of-force/`

4. **BLS** — `https://api.bls.gov/publicAPI/v2/timeseries/data/`
   - POST with series IDs, optional `BLS_API_KEY` for higher rate limits
   - Series IDs encode state, race, metric

5. **HUD** — `https://www.huduser.gov/hudapi/public/`
   - AFFH data endpoints, no auth for public data

6. **USDA Food Access** — `https://gis.ers.usda.gov/arcgis/rest/services/`
   - ArcGIS REST API, no auth, paginated with `resultOffset`

7. **DOE CRDC** — `https://ocrdata.ed.gov/`
   - Bulk CSV download, parsed locally

8. **Mapping Police Violence** — CSV download
   - Public Google Sheets / direct CSV URL

## Graceful Key Handling

```python
api_key = os.environ.get("FBI_API_KEY")
if not api_key:
    context.log.warning("FBI_API_KEY not set - skipping fbi_ucr_crime asset")
    return MaterializeResult(
        metadata={"status": "skipped", "reason": "missing_api_key"}
    )
```

## Shared Patterns

All assets follow the Census ACS pattern:
- Async `aiohttp` for HTTP calls
- Langfuse tracing (best-effort)
- Lineage recording via `build_lineage_record` / `write_lineage_batch`
- Bias flags for coverage gaps
- `MaterializeResult` with metadata: `records_ingested`, `source_url`,
  `content_hash`, `quality_score`, `bias_flags`

## Follow-up Work (GitHub Issues)

1. **Dagster UI authentication** — add auth proxy in front of Dagster on Fly.io
2. **Explore page visualizations** — wire new tables into frontend charts/maps
3. **Scheduled refreshes** — configure cron schedules for each source
4. **County/tract granularity** — expand sources that support sub-state data
