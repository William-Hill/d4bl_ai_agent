# Explore Page Visualizations Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Wire 8 new data tables into the explore page with data source tabs, diverging choropleth maps, and source-specific detail charts.

**Architecture:** Add 8 new API endpoints returning a standardized response shape (rows + national_average + available filter values). Build a tab-based frontend that reuses the existing StateMap and RacialGapChart, adding new components for non-race sources and empty states.

**Tech Stack:** FastAPI, SQLAlchemy (async), Pydantic, Next.js, React, Recharts, react-simple-maps, d3-scale, Tailwind CSS 4

**Design doc:** `docs/plans/2026-03-11-explore-visualizations-design.md`

---

### Task 1: Standardized Explore Response Schema

**Files:**
- Modify: `src/d4bl/app/schemas.py`
- Test: `tests/test_explore_schemas.py`

**Step 1: Write the failing test**

Add to `tests/test_explore_schemas.py`:

```python
from d4bl.app.schemas import ExploreRow, ExploreResponse


def test_explore_row_minimal():
    row = ExploreRow(
        state_fips="06",
        state_name="California",
        value=12.3,
        metric="Asthma",
        year=2022,
    )
    assert row.state_fips == "06"
    assert row.race is None


def test_explore_row_with_race():
    row = ExploreRow(
        state_fips="06",
        state_name="California",
        value=5.1,
        metric="Unemployment Rate",
        race="black",
        year=2022,
    )
    assert row.race == "black"


def test_explore_response():
    resp = ExploreResponse(
        rows=[
            ExploreRow(
                state_fips="06",
                state_name="California",
                value=12.3,
                metric="Asthma",
                year=2022,
            )
        ],
        national_average=10.5,
        available_metrics=["Asthma", "Obesity"],
        available_years=[2021, 2022],
        available_races=[],
    )
    assert resp.national_average == 10.5
    assert len(resp.rows) == 1
    assert resp.available_races == []
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_explore_schemas.py::test_explore_row_minimal tests/test_explore_schemas.py::test_explore_row_with_race tests/test_explore_schemas.py::test_explore_response -v`
Expected: FAIL with ImportError

**Step 3: Write minimal implementation**

Add to `src/d4bl/app/schemas.py`:

```python
class ExploreRow(BaseModel):
    state_fips: str
    state_name: str
    value: float
    metric: str
    year: int
    race: str | None = None


class ExploreResponse(BaseModel):
    rows: list[ExploreRow]
    national_average: float | None
    available_metrics: list[str]
    available_years: list[int]
    available_races: list[str]
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_explore_schemas.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/d4bl/app/schemas.py tests/test_explore_schemas.py
git commit -m "feat: add ExploreRow and ExploreResponse schemas (#72)"
```

---

### Task 2: Helper — compute national average and distinct filter values

**Files:**
- Create: `src/d4bl/app/explore_helpers.py`
- Test: `tests/test_explore_helpers.py`

**Step 1: Write the failing test**

Create `tests/test_explore_helpers.py`:

```python
from d4bl.app.explore_helpers import compute_national_avg, distinct_values


def test_compute_national_avg():
    rows = [
        {"state_fips": "06", "value": 10.0},
        {"state_fips": "36", "value": 20.0},
        {"state_fips": "48", "value": 30.0},
    ]
    assert compute_national_avg(rows) == 20.0


def test_compute_national_avg_empty():
    assert compute_national_avg([]) is None


def test_distinct_values():
    rows = [
        {"metric": "Asthma", "year": 2022},
        {"metric": "Obesity", "year": 2022},
        {"metric": "Asthma", "year": 2021},
    ]
    assert sorted(distinct_values(rows, "metric")) == ["Asthma", "Obesity"]
    assert sorted(distinct_values(rows, "year")) == [2021, 2022]
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_explore_helpers.py -v`
Expected: FAIL with ImportError

**Step 3: Write minimal implementation**

Create `src/d4bl/app/explore_helpers.py`:

```python
"""Shared helpers for explore API endpoints."""

from __future__ import annotations

from typing import Any, Sequence


def compute_national_avg(rows: Sequence[dict[str, Any]]) -> float | None:
    """Return mean of 'value' field across rows, or None if empty."""
    values = [r["value"] for r in rows if r.get("value") is not None]
    if not values:
        return None
    return round(sum(values) / len(values), 4)


def distinct_values(rows: Sequence[dict[str, Any]], key: str) -> list[Any]:
    """Return sorted unique values for *key* across rows."""
    return sorted({r[key] for r in rows if r.get(key) is not None})
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_explore_helpers.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/d4bl/app/explore_helpers.py tests/test_explore_helpers.py
git commit -m "feat: add explore helper utilities (#72)"
```

---

### Task 3: CDC Health Outcomes API endpoint

**Files:**
- Modify: `src/d4bl/app/api.py`
- Test: `tests/test_explore_api.py`

**Step 1: Write the failing test**

Add to `tests/test_explore_api.py`:

```python
@pytest.mark.asyncio
async def test_get_cdc_health(override_auth):
    """GET /api/explore/cdc returns ExploreResponse shape."""
    app = override_auth
    mock_db = AsyncMock(spec=AsyncSession)

    # Mock a result set
    mock_row = MagicMock()
    mock_row.state_fips = "06"
    mock_row.geography_name = "California"
    mock_row.data_value = 10.5
    mock_row.measure = "Asthma"
    mock_row.year = 2022

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mock_row]
    mock_db.execute = AsyncMock(return_value=mock_result)

    app.dependency_overrides[get_db] = lambda: mock_db

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        res = await client.get("/api/explore/cdc")
        assert res.status_code == 200
        body = res.json()
        assert "rows" in body
        assert "national_average" in body
        assert "available_metrics" in body
        assert "available_years" in body
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_explore_api.py::test_get_cdc_health -v`
Expected: FAIL with 404 (endpoint not found)

**Step 3: Write minimal implementation**

Add to `src/d4bl/app/api.py`:

```python
from d4bl.app.schemas import ExploreRow, ExploreResponse
from d4bl.app.explore_helpers import compute_national_avg, distinct_values
from d4bl.infra.database import CdcHealthOutcome


@app.get("/api/explore/cdc", response_model=ExploreResponse)
async def get_cdc_health(
    state_fips: str | None = None,
    measure: str | None = None,
    year: int | None = None,
    limit: int = 1000,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """CDC health outcomes aggregated to state level."""
    try:
        query = select(CdcHealthOutcome)
        if state_fips:
            query = query.where(CdcHealthOutcome.state_fips == state_fips)
        if measure:
            query = query.where(CdcHealthOutcome.measure == measure)
        if year:
            query = query.where(CdcHealthOutcome.year == year)
        query = query.where(
            CdcHealthOutcome.geography_type == "state"
        ).limit(min(limit, 5000))

        result = await db.execute(query)
        rows_raw = result.scalars().all()

        row_dicts = [
            {
                "state_fips": r.state_fips,
                "state_name": r.geography_name,
                "value": r.data_value,
                "metric": r.measure,
                "year": r.year,
            }
            for r in rows_raw
        ]

        return ExploreResponse(
            rows=[ExploreRow(**d) for d in row_dicts],
            national_average=compute_national_avg(row_dicts),
            available_metrics=distinct_values(row_dicts, "metric"),
            available_years=distinct_values(row_dicts, "year"),
            available_races=[],
        )
    except Exception:
        logger.error("Failed to fetch CDC health data", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch CDC health data")
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_explore_api.py::test_get_cdc_health -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/d4bl/app/api.py tests/test_explore_api.py
git commit -m "feat: add CDC health outcomes explore endpoint (#72)"
```

---

### Task 4: Remaining 7 explore API endpoints

Build the remaining endpoints following the same pattern as Task 3. Each endpoint maps table columns to the standardized `ExploreRow` shape.

**Files:**
- Modify: `src/d4bl/app/api.py`
- Test: `tests/test_explore_api.py`

**Step 1: Write failing tests for all 7 endpoints**

Add tests to `tests/test_explore_api.py` — one per endpoint. Each test follows the same mock pattern as `test_get_cdc_health` but with the appropriate mock row fields. Test names:
- `test_get_epa_environmental_justice`
- `test_get_fbi_crime`
- `test_get_bls_labor`
- `test_get_hud_housing`
- `test_get_usda_food`
- `test_get_doe_civil_rights`
- `test_get_police_violence`

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_explore_api.py -k "epa or fbi or bls or hud or usda or doe or police" -v`
Expected: FAIL with 404 for each

**Step 3: Implement all 7 endpoints**

Add to `src/d4bl/app/api.py`. Column mappings for each:

| Endpoint | Model | value field | metric field | race field | geography filter |
|----------|-------|-------------|-------------|------------|-----------------|
| `/api/explore/epa` | `EpaEnvironmentalJustice` | `raw_value` | `indicator` | None | aggregate tracts: use `func.avg` grouped by `state_fips` |
| `/api/explore/fbi` | `FbiCrimeStat` | `value` | `offense` | `race` | `state_abbrev` (map to state_name) |
| `/api/explore/bls` | `BlsLaborStatistic` | `value` | `metric` | `race` | `state_fips` |
| `/api/explore/hud` | `HudFairHousing` | `value` | `indicator` | None | `geography_type == "state"` |
| `/api/explore/usda` | `UsdaFoodAccess` | `value` | `indicator` | None | aggregate tracts: use `func.avg` grouped by `state_fips` |
| `/api/explore/doe` | `DoeCivilRights` | `value` | `metric` | `race` | aggregate districts: use `func.avg` grouped by `state` |
| `/api/explore/police-violence` | `PoliceViolenceIncident` | count(*) | `"incidents"` (literal) | `race` | group by `state`, `year` |

**Important notes for aggregation endpoints (EPA, USDA, DOE, Police Violence):**
- Use `select(Model.state_fips, func.avg(Model.value).label("value"), ...)` with `.group_by()`
- Access results via `result.mappings().all()` instead of `.scalars().all()`
- For Police Violence, use `func.count()` as the value and group by state + race + year

**FBI special case:**
- Uses `state_abbrev` (2-letter) not `state_fips` (2-digit). Need a reverse ABBREV_TO_FIPS mapping or return `state_abbrev` and let the frontend map it.
- Recommendation: add `state_fips` to the response by using a lookup dict in the endpoint. The frontend StateMap needs FIPS codes.

```python
# Add near top of api.py
ABBREV_TO_FIPS: dict[str, str] = {v: k for k, v in {
    "01": "AL", "02": "AK", "04": "AZ", "05": "AR", "06": "CA", "08": "CO",
    "09": "CT", "10": "DE", "11": "DC", "12": "FL", "13": "GA", "15": "HI",
    "16": "ID", "17": "IL", "18": "IN", "19": "IA", "20": "KS", "21": "KY",
    "22": "LA", "23": "ME", "24": "MD", "25": "MA", "26": "MI", "27": "MN",
    "28": "MS", "29": "MO", "30": "MT", "31": "NE", "32": "NV", "33": "NH",
    "34": "NJ", "35": "NM", "36": "NY", "37": "NC", "38": "ND", "39": "OH",
    "40": "OK", "41": "OR", "42": "PA", "44": "RI", "45": "SC", "46": "SD",
    "47": "TN", "48": "TX", "49": "UT", "50": "VT", "51": "VA", "53": "WA",
    "54": "WV", "55": "WI", "56": "WY",
}.items()}
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_explore_api.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add src/d4bl/app/api.py tests/test_explore_api.py
git commit -m "feat: add 7 remaining explore API endpoints (#72)"
```

---

### Task 5: Frontend types and data source config

**Files:**
- Modify: `ui-nextjs/lib/types.ts`
- Create: `ui-nextjs/lib/explore-config.ts`

**Step 1: Add TypeScript types**

Add to `ui-nextjs/lib/types.ts`:

```typescript
export interface ExploreRow {
  state_fips: string;
  state_name: string;
  value: number;
  metric: string;
  year: number;
  race: string | null;
}

export interface ExploreResponse {
  rows: ExploreRow[];
  national_average: number | null;
  available_metrics: string[];
  available_years: number[];
  available_races: string[];
}
```

**Step 2: Create data source config**

Create `ui-nextjs/lib/explore-config.ts`:

```typescript
export interface DataSourceConfig {
  key: string;
  label: string;
  accent: string;
  endpoint: string;
  hasRace: boolean;
  primaryFilterKey: string;   // query param name for the metric/measure filter
  primaryFilterLabel: string; // display label (e.g., "Measure", "Indicator", "Offense")
}

export const DATA_SOURCES: DataSourceConfig[] = [
  {
    key: "census",
    label: "Census ACS",
    accent: "#00ff32",
    endpoint: "/api/explore/indicators",
    hasRace: true,
    primaryFilterKey: "metric",
    primaryFilterLabel: "Metric",
  },
  {
    key: "cdc",
    label: "CDC Health",
    accent: "#ff6b6b",
    endpoint: "/api/explore/cdc",
    hasRace: false,
    primaryFilterKey: "measure",
    primaryFilterLabel: "Measure",
  },
  {
    key: "epa",
    label: "EPA Environment",
    accent: "#4ecdc4",
    endpoint: "/api/explore/epa",
    hasRace: false,
    primaryFilterKey: "indicator",
    primaryFilterLabel: "Indicator",
  },
  {
    key: "fbi",
    label: "FBI Crime",
    accent: "#ffd93d",
    endpoint: "/api/explore/fbi",
    hasRace: true,
    primaryFilterKey: "offense",
    primaryFilterLabel: "Offense",
  },
  {
    key: "bls",
    label: "BLS Labor",
    accent: "#6c5ce7",
    endpoint: "/api/explore/bls",
    hasRace: true,
    primaryFilterKey: "metric",
    primaryFilterLabel: "Metric",
  },
  {
    key: "hud",
    label: "HUD Housing",
    accent: "#fd79a8",
    endpoint: "/api/explore/hud",
    hasRace: false,
    primaryFilterKey: "indicator",
    primaryFilterLabel: "Indicator",
  },
  {
    key: "usda",
    label: "USDA Food",
    accent: "#00b894",
    endpoint: "/api/explore/usda",
    hasRace: false,
    primaryFilterKey: "indicator",
    primaryFilterLabel: "Indicator",
  },
  {
    key: "doe",
    label: "DOE Education",
    accent: "#fdcb6e",
    endpoint: "/api/explore/doe",
    hasRace: true,
    primaryFilterKey: "metric",
    primaryFilterLabel: "Metric",
  },
  {
    key: "police",
    label: "Police Violence",
    accent: "#e17055",
    endpoint: "/api/explore/police-violence",
    hasRace: true,
    primaryFilterKey: "metric",
    primaryFilterLabel: "Metric",
  },
];
```

**Step 3: Commit**

```bash
git add ui-nextjs/lib/types.ts ui-nextjs/lib/explore-config.ts
git commit -m "feat: add frontend types and data source config (#72)"
```

---

### Task 6: DataSourceTabs component

**Files:**
- Create: `ui-nextjs/components/explore/DataSourceTabs.tsx`

**Step 1: Build the component**

Create `ui-nextjs/components/explore/DataSourceTabs.tsx`:

```tsx
'use client';

import { DATA_SOURCES, DataSourceConfig } from '@/lib/explore-config';

interface Props {
  activeKey: string;
  onSelect: (source: DataSourceConfig) => void;
}

export default function DataSourceTabs({ activeKey, onSelect }: Props) {
  return (
    <div className="flex gap-2 overflow-x-auto pb-2 mb-6 scrollbar-thin">
      {DATA_SOURCES.map((src) => {
        const isActive = src.key === activeKey;
        return (
          <button
            key={src.key}
            onClick={() => onSelect(src)}
            className={`
              relative flex-shrink-0 px-4 py-2 rounded-full text-sm font-medium
              transition-all duration-200 border
              ${isActive
                ? 'text-white border-transparent'
                : 'text-gray-400 border-[#404040] hover:text-white hover:border-gray-500'
              }
            `}
            style={isActive ? {
              backgroundColor: `${src.accent}20`,
              borderColor: src.accent,
              color: src.accent,
            } : undefined}
          >
            {src.label}
            {isActive && (
              <span
                className="absolute bottom-0 left-1/2 -translate-x-1/2 w-8 h-0.5 rounded-full"
                style={{ backgroundColor: src.accent, boxShadow: `0 0 8px ${src.accent}60` }}
              />
            )}
          </button>
        );
      })}
    </div>
  );
}
```

**Step 2: Commit**

```bash
git add ui-nextjs/components/explore/DataSourceTabs.tsx
git commit -m "feat: add DataSourceTabs component (#72)"
```

---

### Task 7: EmptyDataState component

**Files:**
- Create: `ui-nextjs/components/explore/EmptyDataState.tsx`

**Step 1: Build the component**

Create `ui-nextjs/components/explore/EmptyDataState.tsx`:

```tsx
interface Props {
  sourceName: string;
  accent: string;
}

export default function EmptyDataState({ sourceName, accent }: Props) {
  return (
    <div className="bg-[#1a1a1a] border border-[#404040] rounded-lg p-12 text-center">
      <div
        className="inline-block w-12 h-12 rounded-full mb-4 opacity-30"
        style={{ backgroundColor: accent }}
      />
      <h3 className="text-lg font-semibold text-white mb-2">
        No {sourceName} data available
      </h3>
      <p className="text-gray-500 text-sm max-w-md mx-auto">
        This data source has not been ingested yet. Run the corresponding
        Dagster pipeline to populate it.
      </p>
    </div>
  );
}
```

**Step 2: Commit**

```bash
git add ui-nextjs/components/explore/EmptyDataState.tsx
git commit -m "feat: add EmptyDataState component (#72)"
```

---

### Task 8: StateVsNationalChart component

**Files:**
- Create: `ui-nextjs/components/explore/StateVsNationalChart.tsx`

**Step 1: Build the component**

Create `ui-nextjs/components/explore/StateVsNationalChart.tsx`:

```tsx
'use client';

import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from 'recharts';

interface Props {
  stateValue: number;
  nationalAverage: number;
  stateName: string;
  metric: string;
  accent: string;
}

export default function StateVsNationalChart({
  stateValue,
  nationalAverage,
  stateName,
  metric,
  accent,
}: Props) {
  const data = [
    { name: stateName, value: stateValue },
    { name: 'National Avg', value: nationalAverage },
  ];

  const diff = stateValue - nationalAverage;
  const pctDiff = nationalAverage !== 0
    ? ((diff / nationalAverage) * 100).toFixed(1)
    : '0';

  return (
    <div className="bg-[#1a1a1a] border border-[#404040] rounded-lg p-4">
      <div className="flex items-baseline justify-between mb-4">
        <h3 className="text-base font-semibold text-white">
          {metric} — {stateName}
        </h3>
        <span
          className="text-sm font-mono"
          style={{ color: diff >= 0 ? accent : '#777' }}
        >
          {diff >= 0 ? '+' : ''}{pctDiff}% vs national
        </span>
      </div>
      <ResponsiveContainer width="100%" height={200}>
        <BarChart data={data} barCategoryGap="30%">
          <CartesianGrid strokeDasharray="3 3" stroke="#333" />
          <XAxis dataKey="name" tick={{ fill: '#999', fontSize: 12 }} />
          <YAxis tick={{ fill: '#999', fontSize: 12 }} />
          <Tooltip
            contentStyle={{ backgroundColor: '#292929', border: '1px solid #404040', color: '#fff' }}
          />
          <Bar dataKey="value" radius={[4, 4, 0, 0]}>
            <Cell fill={accent} />
            <Cell fill="#555" />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
```

**Step 2: Commit**

```bash
git add ui-nextjs/components/explore/StateVsNationalChart.tsx
git commit -m "feat: add StateVsNationalChart component (#72)"
```

---

### Task 9: PolicyBadge component

**Files:**
- Create: `ui-nextjs/components/explore/PolicyBadge.tsx`

**Step 1: Build the component**

Create `ui-nextjs/components/explore/PolicyBadge.tsx`:

```tsx
'use client';

import { useState } from 'react';
import PolicyTable from './PolicyTable';
import { PolicyBill } from '@/lib/types';

interface Props {
  bills: PolicyBill[];
  stateName: string;
}

export default function PolicyBadge({ bills, stateName }: Props) {
  const [open, setOpen] = useState(false);

  if (!bills.length) return null;

  return (
    <>
      <button
        onClick={() => setOpen(!open)}
        className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium
          bg-[#00ff32]/10 text-[#00ff32] border border-[#00ff32]/30
          hover:bg-[#00ff32]/20 transition-colors"
      >
        <span className="w-1.5 h-1.5 rounded-full bg-[#00ff32]" />
        {bills.length} bill{bills.length !== 1 ? 's' : ''}
      </button>

      {open && (
        <div className="fixed inset-y-0 right-0 w-full max-w-lg z-50 flex">
          {/* Backdrop */}
          <div
            className="fixed inset-0 bg-black/50"
            onClick={() => setOpen(false)}
          />
          {/* Panel */}
          <div className="relative ml-auto h-full w-full max-w-lg bg-[#1a1a1a] border-l border-[#404040] overflow-y-auto p-6 shadow-2xl">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold text-white">
                Policy Tracker — <span className="text-[#00ff32]">{stateName}</span>
              </h2>
              <button
                onClick={() => setOpen(false)}
                className="text-gray-500 hover:text-white text-xl"
              >
                &times;
              </button>
            </div>
            <PolicyTable bills={bills} />
          </div>
        </div>
      )}
    </>
  );
}
```

**Step 2: Commit**

```bash
git add ui-nextjs/components/explore/PolicyBadge.tsx
git commit -m "feat: add PolicyBadge slide-in panel component (#72)"
```

---

### Task 10: Update StateMap to accept accent color + diverging scale

**Files:**
- Modify: `ui-nextjs/components/explore/StateMap.tsx`

**Step 1: Read the current component** (already known from exploration)

**Step 2: Modify StateMap**

Changes needed:
- Add `accent` and `nationalAverage` props
- Replace the single-hue green scale with a diverging scale:
  - Below average: `#555` (gray) → midpoint
  - Above average: midpoint → `accent` color
- Use `d3-scale` `scaleDiverging` or two `scaleLinear` ranges joined at the midpoint

Update the Props interface:

```typescript
interface Props {
  indicators: { state_fips?: string; fips_code?: string; value: number }[];
  selectedStateFips: string | null;
  onSelectState: (fips: string, name: string) => void;
  accent?: string;
  nationalAverage?: number | null;
}
```

Update the color scale logic:

```typescript
const avg = nationalAverage ?? (min + max) / 2;
const colorScale = (val: number) => {
  if (val <= avg) {
    // gray to white midpoint
    const t = max === min ? 0.5 : (val - min) / (avg - min);
    return d3.interpolateRgb('#444', '#888')(Math.min(t, 1));
  }
  // midpoint to accent
  const t = avg === max ? 1 : (val - avg) / (max - avg);
  return d3.interpolateRgb('#888', accent ?? '#00ff32')(Math.min(t, 1));
};
```

Note: Need to add `d3-interpolate` dependency. Check if it's already installed; if not, add it.

**Step 3: Run the frontend dev server to verify visually**

Run: `cd ui-nextjs && npm run build`
Expected: Builds without errors

**Step 4: Commit**

```bash
git add ui-nextjs/components/explore/StateMap.tsx
git commit -m "feat: update StateMap with diverging color scale and accent prop (#72)"
```

---

### Task 11: Generalize MetricFilterPanel

**Files:**
- Modify: `ui-nextjs/components/explore/MetricFilterPanel.tsx`

**Step 1: Update the component**

The current MetricFilterPanel has hardcoded Census ACS metrics/races/years. Generalize it to accept dynamic options from the `ExploreResponse`:

```typescript
export interface ExploreFilters {
  metric: string;       // was union type, now any string
  race: string | null;  // null for sources without race
  year: number;
  selectedState: string | null;
}

interface Props {
  filters: ExploreFilters;
  onChange: (f: ExploreFilters) => void;
  availableMetrics: string[];
  availableYears: number[];
  availableRaces: string[];
  primaryFilterLabel: string;  // "Metric", "Measure", "Indicator", etc.
  accent: string;
}
```

Key changes:
- Render metric radio buttons from `availableMetrics` prop (not hardcoded)
- Conditionally render race filter only when `availableRaces.length > 0`
- Render year dropdown from `availableYears` prop
- Use `accent` color for the active radio indicator
- Use `primaryFilterLabel` as the section heading

**Step 2: Build to verify**

Run: `cd ui-nextjs && npm run build`
Expected: Builds without errors

**Step 3: Commit**

```bash
git add ui-nextjs/components/explore/MetricFilterPanel.tsx
git commit -m "feat: generalize MetricFilterPanel for dynamic filter options (#72)"
```

---

### Task 12: Refactor ExplorePage to orchestrate tabs

**Files:**
- Modify: `ui-nextjs/app/explore/page.tsx`

This is the largest task. The page needs to:

1. Render `DataSourceTabs` at the top
2. Track the active data source in state
3. Fetch data from the active source's endpoint (using `ExploreResponse` shape for new sources, legacy shape for Census)
4. Pass accent color and national average to `StateMap`
5. Show `RacialGapChart` for sources with race, `StateVsNationalChart` for sources without
6. Show `PolicyBadge` instead of inline `PolicyTable`
7. Show `EmptyDataState` when response has zero rows

**Step 1: Refactor the page**

Key state changes:

```typescript
const [activeSource, setActiveSource] = useState<DataSourceConfig>(DATA_SOURCES[0]);
const [exploreData, setExploreData] = useState<ExploreResponse | null>(null);
```

Data fetching — replace the three separate fetch functions with a unified one:

```typescript
const fetchExploreData = useCallback(async (signal: AbortSignal) => {
  if (!session?.access_token) return;

  const params = new URLSearchParams();

  // For Census ACS, use the legacy endpoint format
  if (activeSource.key === 'census') {
    if (filters.metric) params.set('metric', filters.metric);
    if (filters.race) params.set('race', filters.race);
    params.set('year', String(filters.year));
    params.set('geography_type', 'state');
  } else {
    // New endpoints use standardized params
    if (filters.metric) params.set(activeSource.primaryFilterKey, filters.metric);
    if (filters.race) params.set('race', filters.race);
    params.set('year', String(filters.year));
  }

  if (filters.selectedState) {
    params.set('state_fips', filters.selectedState);
  }

  const res = await fetch(
    `${API_BASE}${activeSource.endpoint}?${params}`,
    { signal, headers: getHeaders() },
  );
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const data = await res.json();

  // Normalize Census legacy response to ExploreResponse shape
  if (activeSource.key === 'census' && Array.isArray(data)) {
    const rows = data.map((r: IndicatorRow) => ({
      state_fips: r.state_fips,
      state_name: r.geography_name,
      value: r.value,
      metric: r.metric,
      year: r.year,
      race: r.race,
    }));
    setExploreData({
      rows,
      national_average: rows.length
        ? rows.reduce((s, r) => s + r.value, 0) / rows.length
        : null,
      available_metrics: [...new Set(rows.map(r => r.metric))].sort(),
      available_years: [...new Set(rows.map(r => r.year))].sort(),
      available_races: [...new Set(rows.map(r => r.race).filter(Boolean))].sort() as string[],
    });
  } else {
    setExploreData(data);
  }
}, [activeSource, filters, session?.access_token, getHeaders]);
```

Render logic:

```tsx
{/* Tabs */}
<DataSourceTabs activeKey={activeSource.key} onSelect={handleSourceChange} />

{/* Map + Filters */}
<div className="grid grid-cols-1 lg:grid-cols-[1fr_260px] gap-4 mb-6">
  {exploreData && exploreData.rows.length > 0 ? (
    <StateMap
      indicators={exploreData.rows.map(r => ({
        state_fips: r.state_fips,
        fips_code: r.state_fips,
        geography_name: r.state_name,
        value: r.value,
      }))}
      selectedStateFips={filters.selectedState}
      onSelectState={handleSelectState}
      accent={activeSource.accent}
      nationalAverage={exploreData.national_average}
    />
  ) : (
    <EmptyDataState sourceName={activeSource.label} accent={activeSource.accent} />
  )}
  <MetricFilterPanel
    filters={filters}
    onChange={setFilters}
    availableMetrics={exploreData?.available_metrics ?? []}
    availableYears={exploreData?.available_years ?? []}
    availableRaces={exploreData?.available_races ?? []}
    primaryFilterLabel={activeSource.primaryFilterLabel}
    accent={activeSource.accent}
  />
</div>

{/* Detail chart — race or state-vs-national */}
{filters.selectedState && exploreData && exploreData.rows.length > 0 && (
  activeSource.hasRace ? (
    <RacialGapChart
      indicators={chartIndicators}
      metric={filters.metric}
      stateName={selectedStateName}
    />
  ) : (
    <StateVsNationalChart
      stateValue={stateDetail?.value ?? 0}
      nationalAverage={exploreData.national_average ?? 0}
      stateName={selectedStateName}
      metric={filters.metric}
      accent={activeSource.accent}
    />
  )
)}

{/* Policy badge — inline next to state name */}
{filters.selectedState && (
  <PolicyBadge bills={bills} stateName={selectedStateName} />
)}
```

When switching sources, reset filters to defaults:

```typescript
const handleSourceChange = (src: DataSourceConfig) => {
  setActiveSource(src);
  setFilters({
    metric: '',
    race: src.hasRace ? 'total' : null,
    year: 2022,
    selectedState: null,
  });
  setExploreData(null);
};
```

**Step 2: Fetch initial filter values**

On source change, first fetch without state_fips to get available_metrics/years/races, then set filters.metric to the first available metric. This may require a two-phase fetch or handling in the useEffect.

**Step 3: Build to verify**

Run: `cd ui-nextjs && npm run build`
Expected: Builds without errors

**Step 4: Commit**

```bash
git add ui-nextjs/app/explore/page.tsx
git commit -m "feat: refactor explore page with data source tabs and unified fetching (#72)"
```

---

### Task 13: Install d3-interpolate if needed

**Files:**
- Modify: `ui-nextjs/package.json`

**Step 1: Check and install**

Run: `cd ui-nextjs && npm ls d3-interpolate`

If not installed:
Run: `cd ui-nextjs && npm install d3-interpolate @types/d3-interpolate`

**Step 2: Commit**

```bash
git add ui-nextjs/package.json ui-nextjs/package-lock.json
git commit -m "chore: add d3-interpolate for diverging color scale (#72)"
```

---

### Task 14: Integration test — full round trip

**Files:**
- Test: `tests/test_explore_api.py`

**Step 1: Write integration test for ExploreResponse shape**

Add a test that verifies all 8 new endpoints return valid `ExploreResponse` JSON shape:

```python
@pytest.mark.asyncio
@pytest.mark.parametrize("path", [
    "/api/explore/cdc",
    "/api/explore/epa",
    "/api/explore/fbi",
    "/api/explore/bls",
    "/api/explore/hud",
    "/api/explore/usda",
    "/api/explore/doe",
    "/api/explore/police-violence",
])
async def test_explore_endpoint_returns_standard_shape(override_auth, path):
    app = override_auth
    mock_db = AsyncMock(spec=AsyncSession)
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_result.mappings.return_value.all.return_value = []
    mock_db.execute = AsyncMock(return_value=mock_result)
    app.dependency_overrides[get_db] = lambda: mock_db

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        res = await client.get(path)
        assert res.status_code == 200
        body = res.json()
        assert isinstance(body["rows"], list)
        assert "national_average" in body
        assert "available_metrics" in body
        assert "available_years" in body
        assert "available_races" in body
```

**Step 2: Run to verify**

Run: `pytest tests/test_explore_api.py::test_explore_endpoint_returns_standard_shape -v`
Expected: ALL 8 PASS

**Step 3: Commit**

```bash
git add tests/test_explore_api.py
git commit -m "test: add parametrized integration test for all explore endpoints (#72)"
```

---

### Task 15: Frontend build verification and polish

**Step 1: Build the frontend**

Run: `cd ui-nextjs && npm run build`
Expected: Clean build, no errors

**Step 2: Run linter**

Run: `cd ui-nextjs && npm run lint`
Expected: No errors

**Step 3: Fix any issues found**

**Step 4: Final commit**

```bash
git add -A
git commit -m "fix: address build and lint issues (#72)"
```

---

### Task 16: Backend test suite verification

**Step 1: Run full backend test suite**

Run: `pytest tests/ -v`
Expected: All tests pass, including existing tests that shouldn't be broken

**Step 2: Fix any regressions**

**Step 3: Commit if needed**

---

## Task Summary

| Task | Description | Type |
|------|-------------|------|
| 1 | ExploreRow/ExploreResponse schemas | Backend TDD |
| 2 | Helper functions (avg, distinct) | Backend TDD |
| 3 | CDC Health endpoint | Backend TDD |
| 4 | 7 remaining endpoints | Backend TDD |
| 5 | Frontend types + config | Frontend |
| 6 | DataSourceTabs component | Frontend |
| 7 | EmptyDataState component | Frontend |
| 8 | StateVsNationalChart component | Frontend |
| 9 | PolicyBadge component | Frontend |
| 10 | Update StateMap (diverging scale) | Frontend |
| 11 | Generalize MetricFilterPanel | Frontend |
| 12 | Refactor ExplorePage | Frontend |
| 13 | Install d3-interpolate | Chore |
| 14 | Integration tests | Backend TDD |
| 15 | Frontend build verification | Verification |
| 16 | Backend test suite verification | Verification |
