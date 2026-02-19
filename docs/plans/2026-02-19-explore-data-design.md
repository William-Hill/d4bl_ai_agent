# Explore Data Feature — Design Document

**Date:** 2026-02-19
**Status:** Approved

---

## Goal

Add a dedicated `/explore` page to the D4BL platform that lets users browse race-disaggregated socioeconomic indicators (Census ACS) and state policy activity (OpenStates) through an interactive choropleth map and policy tracker — styled to D4BL's dark theme with layout patterns inspired by the Black Wealth Data Center (BWDC).

---

## Architecture

### New route
`ui-nextjs/app/explore/page.tsx` — standalone Next.js App Router page alongside the existing research tool.

### New backend endpoints
- `GET /api/explore/indicators` — race-disaggregated Census ACS metrics by state/county
- `GET /api/explore/policies` — OpenStates policy bills filtered by state/status/topic
- `GET /api/explore/states` — lightweight summary roll-up per state for map coloring

### New database tables
- `census_indicators` — ACS 5-year estimates at state and county geography
- `policy_bills` — state legislation from OpenStates

### New ingestion scripts
- `scripts/ingest_census_acs.py` — Census Bureau REST API → `census_indicators`
- `scripts/ingest_openstates.py` — OpenStates GraphQL API → `policy_bills`

### Frontend dependencies
- `react-simple-maps` — choropleth SVG map
- `recharts` — bar charts
- `d3-scale` — color scale for map

---

## Database Schema

### `census_indicators`

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | default gen_random_uuid() |
| fips_code | VARCHAR(5) | state (2-digit) or county (5-digit) FIPS |
| geography_type | VARCHAR(10) | `state` \| `county` \| `tract` |
| geography_name | TEXT | human-readable name |
| state_fips | VARCHAR(2) | parent state FIPS |
| year | INTEGER | ACS survey year (e.g. 2022) |
| race | VARCHAR(50) | `total` \| `black` \| `white` \| `hispanic` \| etc. |
| metric | VARCHAR(100) | `homeownership_rate` \| `median_household_income` \| `poverty_rate` |
| value | FLOAT | metric value |
| margin_of_error | FLOAT | nullable |
| created_at | TIMESTAMP | default now() |

**Index:** `(state_fips, geography_type, metric, race, year)`
**Unique constraint:** `(fips_code, year, race, metric)` — enables idempotent upsert

---

### `policy_bills`

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | default gen_random_uuid() |
| state | VARCHAR(2) | 2-letter state abbreviation |
| state_name | VARCHAR(50) | full state name |
| bill_id | VARCHAR(50) | OpenStates internal ID |
| bill_number | VARCHAR(20) | e.g. `SB 1234` |
| title | TEXT | bill title |
| summary | TEXT | nullable |
| status | VARCHAR(20) | `introduced` \| `passed` \| `failed` \| `signed` \| `other` |
| topic_tags | JSON | array of topic strings |
| session | VARCHAR(20) | e.g. `2025` |
| introduced_date | DATE | nullable |
| last_action_date | DATE | nullable |
| url | TEXT | link to state legislature page |
| created_at | TIMESTAMP | default now() |
| updated_at | TIMESTAMP | default now(), updated on change |

**Index:** `(state, status, session)`
**Index:** GIN on `topic_tags`
**Unique constraint:** `(state, bill_id, session)` — enables idempotent upsert

---

## Backend API Endpoints

All three endpoints live in `src/d4bl/app/api.py` (or a new `src/d4bl/app/explore_router.py`), follow the existing pattern of `async with async_session_maker() as db:`, return JSON, and log errors structurally.

### `GET /api/explore/indicators`

Query params:
- `state_fips` — 2-digit FIPS (optional, returns all states if omitted)
- `geography_type` — `state` | `county` | `tract` (default: `state`)
- `metric` — metric name filter
- `race` — race filter
- `year` — integer year filter

Returns: `[{fips_code, geography_name, state_fips, geography_type, year, race, metric, value, margin_of_error}]`

Use case: feed choropleth map and racial gap bar chart.

---

### `GET /api/explore/policies`

Query params:
- `state` — 2-letter abbreviation (optional)
- `status` — `introduced` | `passed` | `failed` | `signed`
- `topic` — matched against `topic_tags` JSON array
- `session` — session year string

Returns: `[{state, bill_number, title, summary, status, topic_tags, introduced_date, last_action_date, url}]`

Use case: policy tracker table and state drill-down cards.

---

### `GET /api/explore/states`

No required params. Returns one row per state:
`{state_fips, state_name, available_metrics: [...], bill_count, latest_year}`

Computed via two aggregating SQL queries joined in Python. Used to color the choropleth map and populate the state-selector dropdown.

---

## Frontend `/explore` Page

### Layout

```
┌─────────────────────────────────────────────────────────┐
│  NAV: D4BL  |  Research  |  Explore Data  (active)      │
├─────────────────────────────────────────────────────────┤
│  HERO: "Explore Data by State"    [State selector ▼]    │
├──────────────────────────┬──────────────────────────────┤
│                          │  METRIC FILTER               │
│   CHOROPLETH MAP         │  ○ Homeownership Rate        │
│   (react-simple-maps)    │  ○ Median Household Income   │
│   States colored by      │  ○ Poverty Rate              │
│   selected metric,       │  ─────────────────────       │
│   race, year             │  RACE FILTER                 │
│                          │  ○ All  ○ Black  ○ White ... │
│                          │  ─────────────────────       │
│                          │  YEAR  [2022 ▼]              │
├──────────────────────────┴──────────────────────────────┤
│  BAR CHART: Racial gap comparison for selected state    │
│  (recharts BarChart, #00ff32 for Black, #404040 others) │
├─────────────────────────────────────────────────────────┤
│  POLICY TRACKER: Bills in [selected state]             │
│  ┌─────────────────────────────────────────────────┐   │
│  │ [Housing] SB 1234  Title...  Introduced  →      │   │
│  │ [Wealth]  HB 567   Title...  Signed      →      │   │
│  └─────────────────────────────────────────────────┘   │
│  TOPIC FILTER: [All] [Housing] [Education] [Criminal]   │
└─────────────────────────────────────────────────────────┘
```

### Components (`ui-nextjs/components/explore/`)

| Component | Purpose |
|-----------|---------|
| `StateMap.tsx` | Choropleth using `react-simple-maps` + `d3-scale`, hover tooltip |
| `RacialGapChart.tsx` | Grouped `recharts` BarChart, D4BL color palette |
| `PolicyTable.tsx` | Filterable table with topic tag chips, external links |
| `MetricFilterPanel.tsx` | Controlled filter state, drives map + chart |

**State management:** All filters live in `page.tsx` as `useState`, passed down as props. No global state needed.

### Color Conventions

| Use | Color |
|-----|-------|
| Page background | `#292929` |
| Card/panel background | `#1a1a1a` |
| Borders | `#404040` |
| Primary accent / Black population data | `#00ff32` |
| Secondary bars | `#555`, `#777` |
| Map: low value | `#1a3a1a` |
| Map: high value | `#00ff32` |

---

## Data Ingestion Scripts

### `scripts/ingest_census_acs.py`

- Source: Census Bureau public REST API (free key via `CENSUS_API_KEY` env var)
- Metrics: homeownership rate, median household income, poverty rate
- Race groups: total, Black/African American, White alone, Hispanic/Latino
- Geographies: state-level + county-level (tract optional)
- Upsert on `(fips_code, year, race, metric)` — idempotent
- CLI: `python scripts/ingest_census_acs.py [--year 2022] [--state TX] [--dry-run]`
- Env vars: `CENSUS_API_KEY`, `ACS_YEAR` (default `2022`), `ACS_GEOGRAPHY` (default `state,county`)

### `scripts/ingest_openstates.py`

- Source: OpenStates GraphQL API (free tier; `OPENSTATES_API_KEY` required)
- Topics: `housing`, `wealth`, `education`, `criminal-justice`, `voting-rights`
- Upsert on `(state, bill_id, session)` — idempotent
- CLI: `python scripts/ingest_openstates.py [--state MS] [--session 2025] [--dry-run]`
- Env vars: `OPENSTATES_API_KEY`

Both scripts:
- Use `asyncpg` directly (same connection logic as `init_db.py`)
- Print progress to stdout (rows inserted/updated)
- Exit 0 on success, 1 on error
- Designed for manual execution now, schedulable later

---

## Out of Scope (for now)

- Census tract-level geography (high volume, deferred)
- Materialized views / caching layer
- User-saved filters / bookmarks
- Qualitative data ingestion
- Community survey integration
