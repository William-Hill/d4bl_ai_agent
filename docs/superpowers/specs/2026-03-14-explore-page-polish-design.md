# Explore Page Polish & New Data Source Visualizations

**Issue:** #98
**Date:** 2026-03-14

## Problem Statement

The Explore page has two UX problems and missing coverage for 3 ingested data sources:

1. **Slow loading feel** — no skeleton/shimmer states; the page shows a blank "Loading map data..." text while fetching, with no visual feedback on filter changes
2. **No data context** — users don't understand what each data source measures or what individual metrics mean
3. **3 new data sources have data but no visualizations** — Census Demographics (788K rows), CDC Mortality (9.7K rows), BJS Incarceration (1.3K rows)
4. **Empty sources shown** — tabs for DOE, EPA, Traffic Stops, etc. appear despite having zero data

## Design

### 1. Skeleton Loading States

Add shimmer/skeleton placeholders for each visual zone while data loads.

**Components affected:**
- `StateMap` area → gray US map silhouette with shimmer animation
- `MetricFilterPanel` → skeleton bars for filter options
- `RacialGapChart` / `StateVsNationalChart` → skeleton bar shapes
- On filter/tab change, show skeletons immediately (don't wait for response)

**Implementation:**
- Create a single `SkeletonBlock` utility component (rounded div with CSS shimmer animation via `@keyframes`)
- Use it inline in the explore page's conditional rendering — no separate skeleton component per chart
- Show skeletons when `loading && !exploreData?.rows.length` (initial load) AND on subsequent fetches (show skeletons over stale data during filter changes)

**Loading state behavior:**
- **Tab switch:** Clear data immediately, show skeletons
- **Filter change:** Show a subtle loading overlay on existing content (semi-transparent overlay + spinner) rather than replacing with skeletons — avoids layout thrash
- **Initial page load:** Full skeletons

### 2. Data Source Descriptions

Add a brief contextual banner below the data source tabs explaining what the active source measures and why it matters for racial equity analysis.

**Data structure — extend `DataSourceConfig` in `explore-config.ts`:**
```typescript
interface DataSourceConfig {
  // ... existing fields
  description: string;        // 1-2 sentence source description
  sourceUrl: string;          // Link to original data source
  methodology?: string;       // Optional brief methodology note
}
```

**Example descriptions:**
- **Census ACS:** "American Community Survey estimates for homeownership, income, and poverty rates disaggregated by race. Source: U.S. Census Bureau."
- **CDC Health:** "County-level health outcome prevalence from the CDC PLACES dataset, covering chronic disease and health risk behaviors."
- **FBI Crime:** "Arrest statistics and hate crime incidents reported to the FBI's Uniform Crime Reporting program, disaggregated by race and bias motivation."
- **BJS Incarceration** (new): "State and federal incarceration rates from the Bureau of Justice Statistics, disaggregated by race and gender."
- **CDC Mortality** (new): "Age-adjusted mortality rates by cause of death and race from the CDC WONDER database."
- **Census Demographics** (new): "Decennial Census population counts by race and ethnicity at county and tract level."

**UI placement:** A collapsible info bar directly below the tab strip. Shows source description + small "Learn more" link to `sourceUrl`. Collapsed by default after first visit (localStorage preference).

### 3. Metric Tooltips

Add an info icon (ⓘ) next to each metric label in `MetricFilterPanel` that shows a tooltip on hover explaining the metric.

**Data structure — add to `explore-config.ts`:**
```typescript
// Metric descriptions keyed by source + metric value
export const METRIC_DESCRIPTIONS: Record<string, Record<string, string>> = {
  census: {
    homeownership_rate: "Percentage of occupied housing units that are owner-occupied",
    median_household_income: "Median annual household income in inflation-adjusted dollars",
    poverty_rate: "Percentage of population living below the federal poverty line",
  },
  cdc: {
    DIABETES: "Prevalence of diagnosed diabetes among adults aged 18+",
    // ...
  },
  // ...
};
```

**UI:** Small `ⓘ` icon after the metric label. On hover, show a tooltip div positioned above/below. CSS-only tooltip (no library dependency) using `group` + `group-hover:visible` in Tailwind.

### 4. Hide Empty Data Sources

Filter the `DATA_SOURCES` array to only show sources with data.

**Approach:** Add a `hasData: boolean` flag to each `DataSourceConfig` entry, set statically based on known ingestion status. This avoids an extra API call on page load to check row counts.

```typescript
export const DATA_SOURCES: DataSourceConfig[] = [
  { key: "census", label: "Census ACS", hasData: true, ... },
  { key: "epa", label: "EPA Environment", hasData: false, ... },
  // ...
];
```

`DataSourceTabs` filters: `DATA_SOURCES.filter(s => s.hasData)`.

When new data is ingested in the future, the `hasData` flag gets flipped to `true`. This is simple and avoids runtime overhead.

### 5. Wire Up New Data Sources

#### 5a. Census Demographics

- **Table:** `census_demographics` (788K rows — county/tract level)
- **Key columns:** `state_fips`, `county_fips`, `geo_id`, `year`, `race`, `population`, `pct_of_total`
- **API endpoint:** `GET /api/explore/census-demographics`
  - Aggregates to state level: `SUM(population)` grouped by `state_fips, year, race`
  - Computes `pct_of_total` at state level from summed populations
  - Query params: `state_fips`, `race`, `year`
- **Frontend config:** `{ key: "census-demographics", label: "Census Demographics", hasRace: true, primaryFilterKey: "metric", primaryFilterLabel: "Metric" }`
  - Metrics: `population`, `pct_of_total`
  - Accent color: `#45b7d1` (blue, distinct from Census ACS green)
- **Pagination:** Server-side — return state-level aggregates only (max ~50 rows per query). No pagination needed at this aggregation level.

#### 5b. CDC Mortality

- **Table:** `cdc_mortality` (9.7K rows — state level)
- **Key columns:** `state_fips`, `year`, `cause_of_death`, `race`, `deaths`, `age_adjusted_rate`, `crude_rate`
- **API endpoint:** `GET /api/explore/cdc-mortality`
  - Already state-level; return directly with `value = age_adjusted_rate`
  - Query params: `state_fips`, `cause_of_death` (primary filter), `race`, `year`
- **Frontend config:** `{ key: "cdc-mortality", label: "CDC Mortality", hasRace: true, primaryFilterKey: "cause_of_death", primaryFilterLabel: "Cause of Death" }`
  - Accent color: `#c0392b` (dark red, distinct from CDC Health pink-red)

#### 5c. BJS Incarceration

- **Table:** `bjs_incarceration` (1.3K rows — state level)
- **Key columns:** `state_abbrev`, `year`, `facility_type`, `metric`, `race`, `gender`, `value`
- **API endpoint:** `GET /api/explore/bjs`
  - State abbreviation → FIPS conversion needed
  - Query params: `state_fips`, `metric` (primary filter), `race`, `year`
  - Filter by `facility_type` and `gender` as secondary filters (default: all)
- **Frontend config:** `{ key: "bjs", label: "BJS Incarceration", hasRace: true, primaryFilterKey: "metric", primaryFilterLabel: "Metric" }`
  - Accent color: `#8e44ad` (purple, distinct from BLS purple)

### 6. Pagination for Large Datasets

The main concern is Census Demographics (788K rows). Since all explore endpoints aggregate to state level, the actual response sizes are small (~50 rows per query). No client-side pagination is needed.

However, the **initial unfiltered load** can be slow because the DB must scan many rows to aggregate. Optimizations:

- **Require a metric filter** before fetching Census Demographics — show a "Select a metric to explore" prompt instead of auto-loading all data
- **Add DB indexes** if not already present on `(state_fips, year, race)` for the demographics table
- **Server-side:** Use `LIMIT` on raw queries where possible; the aggregation queries already scope to state level

For other sources, response sizes are manageable (<10K rows aggregated to ~50 state rows).

## Files to Create/Modify

### New files:
- None — all changes in existing files

### Modified files:
- `ui-nextjs/lib/explore-config.ts` — add descriptions, metric tooltips, `hasData` flag, new source configs
- `ui-nextjs/app/explore/page.tsx` — skeleton loading, source description banner, loading overlay
- `ui-nextjs/components/explore/DataSourceTabs.tsx` — filter out `hasData: false`
- `ui-nextjs/components/explore/MetricFilterPanel.tsx` — add tooltip icons
- `src/d4bl/app/api.py` — 3 new explore endpoints
- `src/d4bl/app/schemas.py` — any new response models if needed (likely reuse ExploreResponse)

## Out of Scope

- Visualizations for empty data sources (EPA, DOE, Vera, Traffic Stops, Eviction, Congress)
- NL query engine updates (parser.py, structured.py) — separate effort
- New chart component types (the existing StateMap + RacialGapChart + StateVsNationalChart handle all 3 new sources)
- Mobile-specific layout changes
