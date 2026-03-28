# Explore Page Polish & New Visualizations Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Polish the Explore page with skeleton loading states, data source descriptions, metric tooltips, hidden empty sources, and wire up 3 new data sources (Census Demographics, CDC Mortality, BJS Incarceration).

**Architecture:** Extend the existing Explore page infrastructure — add fields to `DataSourceConfig` in the frontend config, add 3 new API endpoints following the FBI/BLS pattern (query model → build ExploreResponse inline), and improve loading UX with CSS-only skeleton animations.

**Tech Stack:** Next.js (React 19), Tailwind CSS 4, FastAPI, SQLAlchemy async, pytest

**Spec:** `docs/superpowers/specs/2026-03-14-explore-page-polish-design.md`

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `ui-nextjs/lib/explore-config.ts` | Modify | Add `description`, `sourceUrl`, `hasData` to config; add `METRIC_DESCRIPTIONS`; add 3 new source entries |
| `ui-nextjs/components/explore/DataSourceTabs.tsx` | Modify | Filter out `hasData: false` sources |
| `ui-nextjs/components/explore/MetricFilterPanel.tsx` | Modify | Add tooltip icons next to metric labels |
| `ui-nextjs/app/explore/page.tsx` | Modify | Skeleton loading, loading overlay, source description banner |
| `src/d4bl/app/api.py` | Modify | Add 3 new explore endpoints |
| `tests/test_explore_api.py` | Modify | Add tests for 3 new endpoints + parametrized shape test |

---

## Chunk 1: Frontend Config & Data Source Descriptions

### Task 1: Extend DataSourceConfig and add source metadata

**Files:**
- Modify: `ui-nextjs/lib/explore-config.ts`

- [ ] **Step 1: Add new fields to `DataSourceConfig` interface**

Add `description`, `sourceUrl`, and `hasData` fields:

```typescript
export interface DataSourceConfig {
  key: string;
  label: string;
  accent: string;
  endpoint: string;
  hasRace: boolean;
  primaryFilterKey: string;
  primaryFilterLabel: string;
  description: string;
  sourceUrl: string;
  hasData: boolean;
}
```

- [ ] **Step 2: Update existing DATA_SOURCES entries with new fields**

Add `description`, `sourceUrl`, and `hasData` to each existing entry. Set `hasData: false` for `epa` and `doe` (0 rows in DB). All others have data.

Census ACS example:
```typescript
{
  key: "census",
  label: "Census ACS",
  accent: "#00ff32",
  endpoint: "/api/explore/indicators",
  hasRace: true,
  primaryFilterKey: "metric",
  primaryFilterLabel: "Metric",
  description: "American Community Survey estimates for homeownership, income, and poverty rates disaggregated by race. Source: U.S. Census Bureau.",
  sourceUrl: "https://data.census.gov/",
  hasData: true,
},
```

Descriptions for all sources:
- **census**: "American Community Survey estimates for homeownership, income, and poverty rates disaggregated by race. Source: U.S. Census Bureau."
- **cdc**: "County-level health outcome prevalence from the CDC PLACES dataset, covering chronic disease and health risk behaviors."
- **epa** (hasData: false): "Tract-level environmental justice screening indicators from the EPA EJScreen tool."
- **fbi**: "Arrest statistics and hate crime incidents reported to the FBI's Uniform Crime Reporting program, disaggregated by race and bias motivation."
- **bls**: "Monthly labor force statistics including unemployment rates disaggregated by race. Source: Bureau of Labor Statistics."
- **hud**: "Fair housing indicators measuring residential segregation and housing discrimination patterns. Source: HUD."
- **usda**: "Food access indicators measuring proximity to grocery stores and food deserts at the census tract level. Source: USDA ERS."
- **doe** (hasData: false): "Civil rights data on school discipline, enrollment, and staffing disaggregated by race. Source: DOE Office for Civil Rights."
- **police**: "Documented incidents of police violence including use of force and fatal encounters, tracked by race and geography."

- [ ] **Step 3: Add 3 new data source entries**

Append these after `police`:

```typescript
{
  key: "census-demographics",
  label: "Census Demographics",
  accent: "#45b7d1",
  endpoint: "/api/explore/census-demographics",
  hasRace: true,
  primaryFilterKey: "metric",
  primaryFilterLabel: "Metric",
  description: "Decennial Census population counts by race and ethnicity at county and tract level, aggregated to state. Source: U.S. Census Bureau.",
  sourceUrl: "https://data.census.gov/",
  hasData: true,
},
{
  key: "cdc-mortality",
  label: "CDC Mortality",
  accent: "#c0392b",
  endpoint: "/api/explore/cdc-mortality",
  hasRace: true,
  primaryFilterKey: "cause_of_death",
  primaryFilterLabel: "Cause of Death",
  description: "Age-adjusted mortality rates by cause of death and race from the CDC WONDER database.",
  sourceUrl: "https://wonder.cdc.gov/",
  hasData: true,
},
{
  key: "bjs",
  label: "BJS Incarceration",
  accent: "#8e44ad",
  endpoint: "/api/explore/bjs",
  hasRace: true,
  primaryFilterKey: "metric",
  primaryFilterLabel: "Metric",
  description: "State and federal incarceration statistics from the Bureau of Justice Statistics, disaggregated by race and gender.",
  sourceUrl: "https://bjs.ojp.gov/",
  hasData: true,
},
```

- [ ] **Step 4: Add METRIC_DESCRIPTIONS constant**

Add after the `DATA_SOURCES` array:

```typescript
/** Metric descriptions keyed by source key + metric value. Used for tooltips. */
export const METRIC_DESCRIPTIONS: Record<string, Record<string, string>> = {
  census: {
    homeownership_rate: "Percentage of occupied housing units that are owner-occupied",
    median_household_income: "Median annual household income in inflation-adjusted dollars",
    poverty_rate: "Percentage of population living below the federal poverty line",
  },
  cdc: {
    DIABETES: "Prevalence of diagnosed diabetes among adults aged 18+",
    BPHIGH: "Prevalence of high blood pressure among adults aged 18+",
    CASTHMA: "Prevalence of current asthma among adults aged 18+",
    OBESITY: "Prevalence of obesity (BMI >= 30) among adults aged 18+",
    MHLTH: "Poor mental health for 14+ days in the past 30 days among adults",
    CSMOKING: "Prevalence of current smoking among adults aged 18+",
    CHD: "Prevalence of coronary heart disease among adults aged 18+",
    STROKE: "Prevalence of stroke among adults aged 18+",
    CANCER: "Prevalence of cancer (excluding skin cancer) among adults aged 18+",
    KIDNEY: "Prevalence of chronic kidney disease among adults aged 18+",
  },
  fbi: {
    "Aggravated Assault": "Attack with a weapon or causing serious bodily injury",
    "Robbery": "Taking property by force or threat of force",
    "Burglary": "Unlawful entry into a structure to commit a crime",
  },
  bls: {
    unemployment_rate: "Percentage of the labor force that is unemployed and actively seeking work",
    labor_force_participation_rate: "Percentage of working-age population in the labor force",
  },
  "census-demographics": {
    population: "Total population count from the Decennial Census",
    pct_of_total: "Percentage of total population for a given race/ethnicity group",
  },
  "cdc-mortality": {},
  bjs: {
    incarceration_rate: "Number of inmates per 100,000 residents",
    total_population: "Total incarcerated population count",
  },
};
```

- [ ] **Step 5: Commit**

```bash
git add ui-nextjs/lib/explore-config.ts
git commit -m "feat: extend DataSourceConfig with descriptions, hasData, and 3 new sources (#98)"
```

### Task 2: Filter empty sources from DataSourceTabs

**Files:**
- Modify: `ui-nextjs/components/explore/DataSourceTabs.tsx`

- [ ] **Step 1: Filter DATA_SOURCES by hasData**

In `DataSourceTabs.tsx`, change:
```typescript
{DATA_SOURCES.map((src) => {
```
to:
```typescript
{DATA_SOURCES.filter((src) => src.hasData).map((src) => {
```

- [ ] **Step 2: Verify build passes**

Run: `cd ui-nextjs && npx next build 2>&1 | tail -20`
Expected: Build succeeds (or only pre-existing warnings)

- [ ] **Step 3: Commit**

```bash
git add ui-nextjs/components/explore/DataSourceTabs.tsx
git commit -m "feat: hide empty data sources from explore tabs (#98)"
```

### Task 3: Add source description banner to Explore page

**Files:**
- Modify: `ui-nextjs/app/explore/page.tsx`

**Note:** The spec mentions a collapsible banner with localStorage preference. We simplify to an always-visible banner — collapsibility can be added later if users find it too noisy.

- [ ] **Step 1: Add source description banner below DataSourceTabs**

After the `<DataSourceTabs ... />` line and before the `{error && ...}` block, add:

```tsx
{/* Source description banner */}
<div className="mb-4 px-4 py-3 bg-[#1a1a1a] border border-[#404040] rounded-lg flex items-start gap-3">
  <div
    className="mt-0.5 w-2 h-2 rounded-full flex-shrink-0"
    style={{ backgroundColor: activeSource.accent }}
  />
  <div className="flex-1 min-w-0">
    <p className="text-sm text-gray-300">{activeSource.description}</p>
    <a
      href={activeSource.sourceUrl}
      target="_blank"
      rel="noopener noreferrer"
      className="text-xs mt-1 inline-block hover:underline"
      style={{ color: activeSource.accent }}
    >
      Learn more
    </a>
  </div>
</div>
```

- [ ] **Step 2: Verify build passes**

Run: `cd ui-nextjs && npx next build 2>&1 | tail -20`

- [ ] **Step 3: Commit**

```bash
git add ui-nextjs/app/explore/page.tsx
git commit -m "feat: add source description banner to explore page (#98)"
```

### Task 4: Add metric tooltips to MetricFilterPanel

**Files:**
- Modify: `ui-nextjs/components/explore/MetricFilterPanel.tsx`

- [ ] **Step 1: Add `sourceKey` prop and import METRIC_DESCRIPTIONS**

Add to the Props interface:
```typescript
/** Key of the active data source, used to look up metric tooltips. */
sourceKey?: string;
```

Add import at top:
```typescript
import { METRIC_DESCRIPTIONS } from '@/lib/explore-config';
```

Add to the destructured props:
```typescript
sourceKey,
```

- [ ] **Step 2: Add tooltip to each metric label**

In the metric radio button map, after the `<span className="text-sm text-gray-300">{m.label}</span>`, add:

```tsx
{sourceKey && METRIC_DESCRIPTIONS[sourceKey]?.[m.value] && (
  <span className="relative group ml-1">
    <span className="text-gray-500 cursor-help text-xs">i</span>
    <span className="invisible group-hover:visible absolute left-4 bottom-full mb-1 w-52 px-2 py-1 text-xs text-gray-200 bg-[#404040] rounded shadow-lg z-10">
      {METRIC_DESCRIPTIONS[sourceKey][m.value]}
    </span>
  </span>
)}
```

- [ ] **Step 3: Pass `sourceKey` from Explore page**

In `ui-nextjs/app/explore/page.tsx`, update the `<MetricFilterPanel>` usage:

```tsx
<MetricFilterPanel
  filters={filters}
  onChange={setFilters}
  availableMetrics={exploreData?.available_metrics}
  availableYears={exploreData?.available_years}
  availableRaces={exploreData?.available_races}
  primaryFilterLabel={activeSource.primaryFilterLabel}
  accent={activeSource.accent}
  sourceKey={activeSource.key}
/>
```

- [ ] **Step 4: Verify build passes**

Run: `cd ui-nextjs && npx next build 2>&1 | tail -20`

- [ ] **Step 5: Commit**

```bash
git add ui-nextjs/components/explore/MetricFilterPanel.tsx ui-nextjs/app/explore/page.tsx
git commit -m "feat: add metric tooltips to explore filter panel (#98)"
```

---

## Chunk 2: Skeleton Loading States

### Task 5: Add skeleton loading to Explore page

**Files:**
- Modify: `ui-nextjs/app/explore/page.tsx`

- [ ] **Step 1: Add SkeletonBlock component at top of file**

Add before the `ExplorePage` component:

```tsx
/** Reusable shimmer skeleton block. */
function SkeletonBlock({ className = '' }: { className?: string }) {
  return (
    <div
      className={`bg-[#333] rounded animate-pulse ${className}`}
    />
  );
}
```

- [ ] **Step 2: Replace map loading placeholder with skeleton**

Replace the existing loading state for the map area:
```tsx
{loading && (!exploreData || !exploreData.rows.length) ? (
  <div className="bg-[#1a1a1a] border border-[#404040] rounded-lg h-64 flex items-center justify-center text-gray-500 text-sm">
    Loading map data...
  </div>
```

with:
```tsx
{loading && (!exploreData || !exploreData.rows.length) ? (
  <div className="bg-[#1a1a1a] border border-[#404040] rounded-lg p-6 space-y-4">
    <SkeletonBlock className="h-6 w-48" />
    <SkeletonBlock className="h-48 w-full" />
    <div className="flex gap-2">
      <SkeletonBlock className="h-4 w-20" />
      <SkeletonBlock className="h-4 w-24" />
      <SkeletonBlock className="h-4 w-16" />
    </div>
  </div>
```

- [ ] **Step 3: Add loading overlay for filter changes**

After the closing `>` of the `<div>` wrapping the map (the `<div>` at the start of the map/filter grid), wrap the map section in a relative container and add an overlay:

Change the map rendering block. After the `<StateMap ... />` component (inside the `exploreData && exploreData.rows.length > 0` branch), add an overlay that shows when loading with existing data:

```tsx
) : exploreData && exploreData.rows.length > 0 ? (
  <div className="relative">
    <StateMap
      indicators={mapIndicators}
      selectedStateFips={filters.selectedState}
      onSelectState={handleSelectState}
      accent={activeSource.accent}
      nationalAverage={exploreData.national_average}
    />
    {loading && (
      <div className="absolute inset-0 bg-[#292929]/60 rounded-lg flex items-center justify-center">
        <div className="w-6 h-6 border-2 border-gray-500 border-t-white rounded-full animate-spin" />
      </div>
    )}
  </div>
```

- [ ] **Step 4: Add skeleton state for MetricFilterPanel area**

When loading with no data, show skeleton bars instead of the filter panel. In the map+filter grid, wrap the `<MetricFilterPanel>` in a conditional:

```tsx
{loading && (!exploreData || !exploreData.rows.length) ? (
  <div className="bg-[#1a1a1a] border border-[#404040] rounded-lg p-4 space-y-4">
    <SkeletonBlock className="h-4 w-20" />
    <SkeletonBlock className="h-3 w-full" />
    <SkeletonBlock className="h-3 w-full" />
    <SkeletonBlock className="h-3 w-3/4" />
    <SkeletonBlock className="h-px w-full bg-[#404040]" />
    <SkeletonBlock className="h-4 w-16" />
    <SkeletonBlock className="h-3 w-full" />
    <SkeletonBlock className="h-3 w-full" />
  </div>
) : (
  <MetricFilterPanel ... />
)}
```

- [ ] **Step 5: Verify build passes**

Run: `cd ui-nextjs && npx next build 2>&1 | tail -20`

- [ ] **Step 6: Commit**

```bash
git add ui-nextjs/app/explore/page.tsx
git commit -m "feat: add skeleton loading and filter overlay to explore page (#98)"
```

---

## Chunk 3: Backend API Endpoints

### Task 6: Add Census Demographics explore endpoint

**Files:**
- Modify: `src/d4bl/app/api.py`
- Modify: `tests/test_explore_api.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_explore_api.py`:

```python
class TestCensusDemographicsEndpoint:
    @pytest.mark.asyncio
    async def test_returns_200_with_explore_response(self, override_auth):
        app = override_auth
        from d4bl.infra.database import get_db

        mock_result = MagicMock()
        mock_result.mappings.return_value.all.return_value = [
            {
                "state_fips": "28",
                "state_name": "Mississippi",
                "year": 2020,
                "race": "Black",
                "total_pop": 1000000,
                "avg_pct": 37.5,
            }
        ]

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        async def override_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_get_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/api/explore/census-demographics",
                params={"state_fips": "28", "metric": "population"},
            )

        assert response.status_code == 200
        data = response.json()
        assert len(data["rows"]) == 1
        assert data["rows"][0]["state_fips"] == "28"
        assert data["rows"][0]["state_name"] == "Mississippi"
        assert data["rows"][0]["race"] == "Black"
        assert data["available_races"] == ["Black"]
        assert data["available_years"] == [2020]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/william-meroxa/Development/d4bl_ai_agent && python -m pytest tests/test_explore_api.py::TestCensusDemographicsEndpoint -v`
Expected: FAIL (404 — endpoint doesn't exist)

- [ ] **Step 3: Add imports to api.py**

In `src/d4bl/app/api.py`, add `BjsIncarceration`, `CdcMortality`, and `CensusDemographics` to the import block at lines 51-68:

```python
from d4bl.infra.database import (
    BjsIncarceration,
    BlsLaborStatistic,
    CdcHealthOutcome,
    CdcMortality,
    CensusDemographics,
    CensusIndicator,
    DoeCivilRights,
    EpaEnvironmentalJustice,
    EvaluationResult,
    FbiCrimeStat,
    HudFairHousing,
    PoliceViolenceIncident,
    PolicyBill,
    ResearchJob,
    UsdaFoodAccess,
    close_db,
    create_tables,
    get_db,
    init_db,
)
```

This import covers all 3 new endpoints (Tasks 6, 7, 8) so it only needs to be done once.

- [ ] **Step 4: Implement the Census Demographics endpoint**

```python
@app.get("/api/explore/census-demographics", response_model=ExploreResponse)
async def get_census_demographics(
    state_fips: str | None = None,
    metric: str | None = None,
    race: str | None = None,
    year: int | None = None,
    limit: int = 1000,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Census Decennial demographics aggregated to state level."""
    try:
        query = select(
            CensusDemographics.state_fips,
            CensusDemographics.state_name,
            CensusDemographics.year,
            CensusDemographics.race,
            func.sum(CensusDemographics.population).label("total_pop"),
            func.avg(CensusDemographics.pct_of_total).label("avg_pct"),
        ).group_by(
            CensusDemographics.state_fips,
            CensusDemographics.state_name,
            CensusDemographics.year,
            CensusDemographics.race,
        )
        if state_fips:
            query = query.where(CensusDemographics.state_fips == state_fips)
        if race:
            query = query.where(CensusDemographics.race == race)
        if year:
            query = query.where(CensusDemographics.year == year)
        query = query.order_by(CensusDemographics.state_fips).limit(max(1, min(limit, 5000)))

        result = await db.execute(query)
        rows_raw = result.mappings().all()

        # Choose value based on metric filter
        use_pct = metric == "pct_of_total"
        row_dicts = [
            {
                "state_fips": r["state_fips"],
                "state_name": r["state_name"] or FIPS_TO_NAME.get(r["state_fips"], r["state_fips"]),
                "value": round(float(r["avg_pct"]), 2) if use_pct else float(r["total_pop"]),
                "metric": "pct_of_total" if use_pct else "population",
                "year": r["year"],
                "race": r["race"],
            }
            for r in rows_raw
        ]

        return ExploreResponse(
            rows=[ExploreRow(**d) for d in row_dicts],
            national_average=compute_national_avg(row_dicts),
            available_metrics=["population", "pct_of_total"],
            available_years=distinct_values(row_dicts, "year"),
            available_races=distinct_values(row_dicts, "race"),
        )
    except Exception:
        logger.error("Failed to fetch Census demographics data", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch Census demographics data")
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd /Users/william-meroxa/Development/d4bl_ai_agent && python -m pytest tests/test_explore_api.py::TestCensusDemographicsEndpoint -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/d4bl/app/api.py tests/test_explore_api.py
git commit -m "feat: add Census Demographics explore endpoint (#98)"
```

### Task 7: Add CDC Mortality explore endpoint

**Files:**
- Modify: `src/d4bl/app/api.py`
- Modify: `tests/test_explore_api.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_explore_api.py`:

```python
class TestCdcMortalityEndpoint:
    @pytest.mark.asyncio
    async def test_returns_200_with_explore_response(self, override_auth):
        app = override_auth
        from d4bl.infra.database import get_db

        mock_row = MagicMock()
        mock_row.state_fips = "28"
        mock_row.state_name = "Mississippi"
        mock_row.age_adjusted_rate = 85.3
        mock_row.cause_of_death = "Heart Disease"
        mock_row.year = 2021
        mock_row.race = "Black"

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_row]

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        async def override_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_get_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/api/explore/cdc-mortality",
                params={"state_fips": "28", "cause_of_death": "Heart Disease"},
            )

        assert response.status_code == 200
        data = response.json()
        assert len(data["rows"]) == 1
        assert data["rows"][0]["state_fips"] == "28"
        assert data["rows"][0]["value"] == 85.3
        assert data["rows"][0]["metric"] == "Heart Disease"
        assert data["rows"][0]["race"] == "Black"
        assert data["available_races"] == ["Black"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/william-meroxa/Development/d4bl_ai_agent && python -m pytest tests/test_explore_api.py::TestCdcMortalityEndpoint -v`
Expected: FAIL (404)

- [ ] **Step 3: Implement the endpoint**

Add to `src/d4bl/app/api.py` (imports already added in Task 6 Step 3).

```python
@app.get("/api/explore/cdc-mortality", response_model=ExploreResponse)
async def get_cdc_mortality(
    state_fips: str | None = None,
    cause_of_death: str | None = None,
    race: str | None = None,
    year: int | None = None,
    limit: int = 1000,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """CDC mortality data — age-adjusted rates by cause and race."""
    try:
        query = select(CdcMortality)
        if state_fips:
            query = query.where(CdcMortality.state_fips == state_fips)
        if cause_of_death:
            query = query.where(CdcMortality.cause_of_death == cause_of_death)
        if race:
            query = query.where(CdcMortality.race == race)
        if year:
            query = query.where(CdcMortality.year == year)
        query = query.order_by(CdcMortality.state_fips).limit(max(1, min(limit, 5000)))

        result = await db.execute(query)
        rows_raw = result.scalars().all()

        row_dicts = [
            {
                "state_fips": r.state_fips,
                "state_name": r.state_name or FIPS_TO_NAME.get(r.state_fips, r.state_fips),
                "value": float(r.age_adjusted_rate) if r.age_adjusted_rate is not None else 0.0,
                "metric": r.cause_of_death,
                "year": r.year,
                "race": r.race,
            }
            for r in rows_raw
        ]

        return ExploreResponse(
            rows=[ExploreRow(**d) for d in row_dicts],
            national_average=compute_national_avg(row_dicts),
            available_metrics=distinct_values(row_dicts, "metric"),
            available_years=distinct_values(row_dicts, "year"),
            available_races=distinct_values(row_dicts, "race"),
        )
    except Exception:
        logger.error("Failed to fetch CDC mortality data", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch CDC mortality data")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/william-meroxa/Development/d4bl_ai_agent && python -m pytest tests/test_explore_api.py::TestCdcMortalityEndpoint -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/d4bl/app/api.py tests/test_explore_api.py
git commit -m "feat: add CDC Mortality explore endpoint (#98)"
```

### Task 8: Add BJS Incarceration explore endpoint

**Files:**
- Modify: `src/d4bl/app/api.py`
- Modify: `tests/test_explore_api.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_explore_api.py`:

```python
class TestBjsEndpoint:
    @pytest.mark.asyncio
    async def test_returns_200_with_explore_response(self, override_auth):
        app = override_auth
        from d4bl.infra.database import get_db

        mock_row = MagicMock()
        mock_row.state_abbrev = "MS"
        mock_row.state_name = "Mississippi"
        mock_row.value = 573.0
        mock_row.metric = "incarceration_rate"
        mock_row.year = 2022
        mock_row.race = "Black"

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_row]

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        async def override_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_get_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/api/explore/bjs",
                params={"state_fips": "28", "metric": "incarceration_rate"},
            )

        assert response.status_code == 200
        data = response.json()
        assert len(data["rows"]) == 1
        assert data["rows"][0]["state_fips"] == "28"
        assert data["rows"][0]["state_name"] == "Mississippi"
        assert data["rows"][0]["value"] == 573.0
        assert data["rows"][0]["metric"] == "incarceration_rate"
        assert data["rows"][0]["race"] == "Black"
        assert data["available_races"] == ["Black"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/william-meroxa/Development/d4bl_ai_agent && python -m pytest tests/test_explore_api.py::TestBjsEndpoint -v`
Expected: FAIL (404)

- [ ] **Step 3: Implement the endpoint**

Add to `src/d4bl/app/api.py` (imports already added in Task 6 Step 3).

```python
@app.get("/api/explore/bjs", response_model=ExploreResponse)
async def get_bjs_incarceration(
    state_fips: str | None = None,
    metric: str | None = None,
    race: str | None = None,
    year: int | None = None,
    limit: int = 1000,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """BJS incarceration data by race and state."""
    try:
        query = select(BjsIncarceration)
        if state_fips:
            abbrev = FIPS_TO_ABBREV.get(state_fips)
            if abbrev:
                query = query.where(BjsIncarceration.state_abbrev == abbrev)
        if metric:
            query = query.where(BjsIncarceration.metric == metric)
        if race:
            query = query.where(BjsIncarceration.race == race)
        if year:
            query = query.where(BjsIncarceration.year == year)
        query = query.order_by(BjsIncarceration.state_abbrev).limit(max(1, min(limit, 5000)))

        result = await db.execute(query)
        rows_raw = result.scalars().all()

        row_dicts = [
            {
                "state_fips": ABBREV_TO_FIPS.get(r.state_abbrev, ""),
                "state_name": r.state_name or FIPS_TO_NAME.get(ABBREV_TO_FIPS.get(r.state_abbrev, ""), ""),
                "value": float(r.value),
                "metric": r.metric,
                "year": r.year,
                "race": r.race,
            }
            for r in rows_raw
        ]

        return ExploreResponse(
            rows=[ExploreRow(**d) for d in row_dicts],
            national_average=compute_national_avg(row_dicts),
            available_metrics=distinct_values(row_dicts, "metric"),
            available_years=distinct_values(row_dicts, "year"),
            available_races=distinct_values(row_dicts, "race"),
        )
    except Exception:
        logger.error("Failed to fetch BJS incarceration data", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch BJS incarceration data")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/william-meroxa/Development/d4bl_ai_agent && python -m pytest tests/test_explore_api.py::TestBjsEndpoint -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/d4bl/app/api.py tests/test_explore_api.py
git commit -m "feat: add BJS Incarceration explore endpoint (#98)"
```

### Task 9: Add new endpoints to parametrized shape test

**Files:**
- Modify: `tests/test_explore_api.py`

- [ ] **Step 1: Update parametrized test to include new endpoints**

In `TestAllExploreEndpointsStandardShape`, add the 3 new paths to the `@pytest.mark.parametrize` list:

```python
@pytest.mark.parametrize("path", [
    "/api/explore/cdc",
    "/api/explore/epa",
    "/api/explore/fbi",
    "/api/explore/bls",
    "/api/explore/hud",
    "/api/explore/usda",
    "/api/explore/doe",
    "/api/explore/police-violence",
    "/api/explore/census-demographics",
    "/api/explore/cdc-mortality",
    "/api/explore/bjs",
])
```

- [ ] **Step 2: Run the parametrized test**

Run: `cd /Users/william-meroxa/Development/d4bl_ai_agent && python -m pytest tests/test_explore_api.py::TestAllExploreEndpointsStandardShape -v`
Expected: All 11 test cases PASS

- [ ] **Step 3: Run full test suite to verify no regressions**

Run: `cd /Users/william-meroxa/Development/d4bl_ai_agent && python -m pytest tests/test_explore_api.py -v`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add tests/test_explore_api.py
git commit -m "test: add new explore endpoints to parametrized shape test (#98)"
```

---

## Chunk 4: Final Verification

### Task 10: Frontend build and lint verification

- [ ] **Step 1: Run Next.js build**

Run: `cd ui-nextjs && npx next build 2>&1 | tail -30`
Expected: Build succeeds

- [ ] **Step 2: Run ESLint**

Run: `cd ui-nextjs && npm run lint 2>&1 | tail -20`
Expected: No new errors

- [ ] **Step 3: Run full backend test suite**

Run: `cd /Users/william-meroxa/Development/d4bl_ai_agent && python -m pytest tests/ -v --tb=short 2>&1 | tail -40`
Expected: All tests pass

- [ ] **Step 4: Commit any lint/type fixes if needed**

```bash
git add -A
git commit -m "fix: address lint and type issues (#98)"
```
