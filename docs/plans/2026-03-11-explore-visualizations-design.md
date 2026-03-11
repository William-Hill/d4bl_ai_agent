# Explore Page Visualizations for New Data Sources

**Issue**: #72
**Date**: 2026-03-11

## Summary

Wire 8 new data tables into the frontend explore page with charts and maps. Add a top-level data source tab bar so users can switch between Census ACS and the 8 new sources, each with source-appropriate filters, diverging choropleth maps, and detail charts.

## Data Sources & Accent Colors

| Source | Table | Accent Color | Has Race? |
|--------|-------|-------------|-----------|
| Census ACS | `census_indicators` | `#00ff32` (green) | Yes |
| CDC Health Outcomes | `cdc_health_outcomes` | `#ff6b6b` (coral) | No |
| EPA Environmental Justice | `epa_environmental_justice` | `#4ecdc4` (teal) | No |
| FBI Crime Stats | `fbi_crime_stats` | `#ffd93d` (amber) | Yes |
| BLS Labor Statistics | `bls_labor_statistics` | `#6c5ce7` (purple) | Yes |
| HUD Fair Housing | `hud_fair_housing` | `#fd79a8` (pink) | No |
| USDA Food Access | `usda_food_access` | `#00b894` (emerald) | No |
| DOE Civil Rights | `doe_civil_rights` | `#fdcb6e` (gold) | Yes |
| Police Violence | `police_violence_incidents` | `#e17055` (burnt orange) | Yes |

## Layout

### Consistent per-source layout

1. **Tab bar** (top) — horizontal scrollable pills, each with accent color indicator. Active tab gets underline glow in its accent color.
2. **Map + Filter sidebar** (main area) — choropleth with diverging color scale centered on national average.
3. **Detail chart** (appears on state click):
   - Sources **with** race data: racial breakdown bar chart (like existing RacialGapChart).
   - Sources **without** race data: state vs national average comparison bar chart.
4. **Policy tracker** — collapsible slide-in overlay panel. A pill badge showing bill count (e.g., "12 bills") appears next to the selected state name on any source. Clicking it opens the policy panel.

### Source-specific filters

| Source | Primary Filter | Secondary Filter |
|--------|---------------|-----------------|
| Census ACS | Metric (homeownership_rate, median_household_income, poverty_rate) | Race (total, black, white, hispanic), Year |
| CDC Health | Measure (Asthma, Obesity, etc.) | Year |
| EPA Environmental Justice | Indicator (EJScreen indicators) | Year |
| FBI Crime | Offense category (Murder, Robbery, etc.) | Race, Year |
| BLS Labor | Metric (Unemployment Rate, Labor Force Participation, etc.) | Race, Year |
| HUD Fair Housing | Indicator (Dissimilarity Index, Segregation, etc.) | Year |
| USDA Food Access | Indicator (Low Access to Supermarket, etc.) | Year |
| DOE Civil Rights | Metric (Suspension Rate, AP Enrollment, etc.) | Race, School Year |
| Police Violence | Aggregate incident counts | Race, Year |

## Map Coloring

**Diverging scale** from national average:
- Above average: source accent color (bright)
- At average: neutral midpoint
- Below average: neutral gray

Midpoint = national mean for the selected metric/indicator. This makes equity gaps immediately visible.

## Empty Data Handling

All 9 tabs are always visible regardless of whether data exists. Sources without ingested data show a styled empty state message: "No [source] data ingested yet. Run the data pipeline to populate."

## Transitions

Crossfade animation when switching between source tabs. Map and charts transition smoothly rather than hard-swapping.

## Backend Requirements

### New API Endpoints

Each new data source needs a GET endpoint under `/api/explore/`:

- `GET /api/explore/cdc` — query `cdc_health_outcomes`
- `GET /api/explore/epa` — query `epa_environmental_justice` (aggregate tracts to state)
- `GET /api/explore/fbi` — query `fbi_crime_stats`
- `GET /api/explore/bls` — query `bls_labor_statistics`
- `GET /api/explore/hud` — query `hud_fair_housing`
- `GET /api/explore/usda` — query `usda_food_access` (aggregate tracts to state)
- `GET /api/explore/doe` — query `doe_civil_rights` (aggregate districts to state)
- `GET /api/explore/police-violence` — query `police_violence_incidents` (aggregate to state counts)

Each endpoint returns:
- State-level aggregated data for the map
- National average for the diverging scale midpoint
- State-specific detail data when `state_fips` or `state` param is provided

### Response Shape (standardized)

```json
{
  "rows": [
    {
      "state_fips": "06",
      "state_name": "California",
      "value": 12.3,
      "metric": "Asthma",
      "race": null,
      "year": 2022
    }
  ],
  "national_average": 10.5,
  "available_metrics": ["Asthma", "Obesity", "Diabetes"],
  "available_years": [2020, 2021, 2022],
  "available_races": []
}
```

## Frontend Components

### New Components

- **DataSourceTabs** — pill tab bar with accent colors and active state animation
- **StateVsNationalChart** — bar chart comparing state value to national average (for non-race sources)
- **PolicyBadge** — pill showing bill count, opens collapsible policy panel
- **EmptyDataState** — styled message for sources without data

### Modified Components

- **StateMap** — accept accent color prop for diverging scale; accept national average for midpoint
- **MetricFilterPanel** — generalize to accept dynamic filter options per source
- **ExplorePage** — orchestrate tab switching, per-source state management, and data fetching
