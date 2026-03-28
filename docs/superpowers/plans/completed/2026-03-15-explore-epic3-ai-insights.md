# Epic 3: AI Insights — Annotations, Explain, Conversational

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add three layers of AI-powered insight to the explore page: inline annotations (pre-computed), one-click LLM explanations, and a conversational query bar.

**Architecture:** Layer 1 (annotations) is a new API endpoint querying `state_summary` for rankings and racial gaps — no LLM. Layer 2 (explain) is a POST endpoint that calls Ollama with structured data context. Layer 3 (conversational) wraps the existing query engine with explore page context. Frontend adds three new components.

**Tech Stack:** Python/FastAPI (backend), Ollama/LiteLLM (LLM), existing QueryEngine, Next.js/React/TypeScript (frontend)

**Spec:** `docs/superpowers/specs/2026-03-15-explore-page-overhaul-design.md` — Epic 3 + Appendix B + Appendix C

---

## File Structure

### Backend (create)
- `src/d4bl/app/explore_insights.py` — Three new endpoint handlers: state-summary, explain, explore-query

### Backend (modify)
- `src/d4bl/app/api.py` — Register the three new endpoints
- `src/d4bl/app/schemas.py` — Add Pydantic models for request/response

### Frontend (create)
- `ui-nextjs/components/explore/StateAnnotation.tsx` — Inline annotation panel (Layer 1)
- `ui-nextjs/components/explore/ExplainPanel.tsx` — AI explain button + collapsible panel (Layer 2)
- `ui-nextjs/components/explore/ExploreQueryBar.tsx` — Conversational query input + results (Layer 3)

### Frontend (modify)
- `ui-nextjs/app/explore/page.tsx` — Add the three new components to the layout

### Tests (create)
- `tests/test_explore_insights.py` — Tests for all three endpoints

---

## Task 3.1a: State summary API endpoint

**Files:**
- Create: `src/d4bl/app/explore_insights.py`
- Modify: `src/d4bl/app/api.py`
- Modify: `src/d4bl/app/schemas.py`
- Test: `tests/test_explore_insights.py`

- [ ] **Step 1: Add Pydantic schemas**

In `src/d4bl/app/schemas.py`, add the response models:

```python
class RacialGapGroup(BaseModel):
    race: str
    value: float

class RacialGap(BaseModel):
    groups: list[RacialGapGroup]
    max_ratio: float
    max_ratio_label: str

class StateSummaryResponse(BaseModel):
    state_fips: str
    state_name: str
    metric: str
    value: float
    national_average: float
    national_rank: int
    national_rank_total: int
    percentile: float
    racial_gap: RacialGap | None
    year: int
    source: str
```

- [ ] **Step 2: Create explore_insights.py with state-summary handler**

```python
# src/d4bl/app/explore_insights.py
"""AI insight endpoints for the explore page."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from d4bl.app.auth import get_current_user
from d4bl.app.schemas import StateSummaryResponse, RacialGap, RacialGapGroup
from d4bl.infra.database import get_db
from d4bl.infra.state_summary import StateSummary

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/explore", tags=["explore-insights"])


@router.get("/state-summary", response_model=StateSummaryResponse)
async def get_state_summary(
    source: str = Query(...),
    state_fips: str = Query(...),
    metric: str = Query(...),
    year: int | None = None,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Pre-computed state summary with rank, percentile, and racial gap."""
    # Get all states for this source+metric to compute rank
    query = (
        select(StateSummary)
        .where(
            StateSummary.source == source,
            StateSummary.metric == metric,
            StateSummary.race == "total",
        )
        .order_by(StateSummary.value.desc())
    )
    if year:
        query = query.where(StateSummary.year == year)
    all_states = await db.execute(query)
    all_rows = all_states.scalars().all()

    if not all_rows:
        raise HTTPException(status_code=404, detail="No data found")

    # Find the target state and compute stats
    values = [r.value for r in all_rows]
    national_avg = sum(values) / len(values)
    total_states = len(all_rows)

    target = None
    rank = 0
    for i, r in enumerate(all_rows):
        if r.state_fips == state_fips:
            target = r
            rank = i + 1
            break

    if not target:
        raise HTTPException(status_code=404, detail="State not found in data")

    # Percentile: % of states with value <= this state's value
    below_count = sum(1 for v in values if v <= target.value)
    percentile = (below_count / total_states) * 100

    # Racial gap: get all race rows for this state
    racial_gap = None
    race_query = (
        select(StateSummary)
        .where(
            StateSummary.source == source,
            StateSummary.metric == metric,
            StateSummary.state_fips == state_fips,
            StateSummary.race != "total",
        )
    )
    if year:
        race_query = race_query.where(StateSummary.year == year)
    race_rows = await db.execute(race_query)
    race_data = race_rows.scalars().all()

    if len(race_data) >= 2:
        groups = [RacialGapGroup(race=r.race, value=r.value) for r in race_data]
        sorted_groups = sorted(groups, key=lambda g: g.value, reverse=True)
        highest = sorted_groups[0]
        lowest = sorted_groups[-1]
        ratio = highest.value / lowest.value if lowest.value > 0 else 0
        racial_gap = RacialGap(
            groups=groups,
            max_ratio=round(ratio, 1),
            max_ratio_label=f"{highest.race} residents: {ratio:.1f}× {lowest.race} rate",
        )

    return StateSummaryResponse(
        state_fips=target.state_fips,
        state_name=target.state_name,
        metric=target.metric,
        value=target.value,
        national_average=round(national_avg, 2),
        national_rank=rank,
        national_rank_total=total_states,
        percentile=round(percentile, 1),
        racial_gap=racial_gap,
        year=target.year,
        source=source,
    )
```

- [ ] **Step 3: Register router in api.py**

In `src/d4bl/app/api.py`, after the existing router includes, add:

```python
from d4bl.app.explore_insights import router as explore_insights_router
app.include_router(explore_insights_router)
```

- [ ] **Step 4: Write tests**

Create `tests/test_explore_insights.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock
from httpx import ASGITransport, AsyncClient
from d4bl.app.api import app


class TestStateSummaryEndpoint:
    @pytest.mark.asyncio
    async def test_returns_rank_and_percentile(self, override_auth):
        app = override_auth
        from d4bl.infra.database import get_db

        # Mock 3 states: CA=60, TX=50, MS=40
        rows = []
        for fips, name, val in [("06", "California", 60.0), ("48", "Texas", 50.0), ("28", "Mississippi", 40.0)]:
            r = MagicMock()
            r.state_fips = fips
            r.state_name = name
            r.metric = "homeownership_rate"
            r.race = "total"
            r.year = 2022
            r.value = val
            r.source = "census"
            rows.append(r)

        mock_result_all = MagicMock()
        mock_result_all.scalars.return_value.all.return_value = rows

        # No race data
        mock_result_race = MagicMock()
        mock_result_race.scalars.return_value.all.return_value = []

        mock_freshness = MagicMock()
        mock_freshness.scalar.return_value = None

        async def _mock_execute(stmt, *a, **kw):
            s = str(stmt)
            if "ingestion_run" in s.lower():
                return mock_freshness
            if "!= :race" in s or "!= 'total'" in s.lower():
                return mock_result_race
            return mock_result_all

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(side_effect=_mock_execute)

        async def override_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_get_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                "/api/explore/state-summary",
                params={"source": "census", "state_fips": "48", "metric": "homeownership_rate"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["national_rank"] == 2  # TX is 2nd (CA=1st, TX=2nd, MS=3rd)
        assert data["national_rank_total"] == 3
        assert data["national_average"] == 50.0
        assert data["value"] == 50.0
        assert data["racial_gap"] is None

    @pytest.mark.asyncio
    async def test_404_when_state_not_found(self, override_auth):
        app = override_auth
        from d4bl.infra.database import get_db

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []

        mock_freshness = MagicMock()
        mock_freshness.scalar.return_value = None

        async def _mock_execute(stmt, *a, **kw):
            s = str(stmt)
            if "ingestion_run" in s.lower():
                return mock_freshness
            return mock_result

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(side_effect=_mock_execute)

        async def override_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_get_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                "/api/explore/state-summary",
                params={"source": "census", "state_fips": "99", "metric": "fake"},
            )

        assert resp.status_code == 404
```

- [ ] **Step 5: Run tests**

Run: `python -m pytest tests/test_explore_insights.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/d4bl/app/explore_insights.py src/d4bl/app/schemas.py src/d4bl/app/api.py tests/test_explore_insights.py
git commit -m "feat: add /api/explore/state-summary endpoint with rank, percentile, racial gap"
```

---

## Task 3.1b: Inline state annotation panel

**Files:**
- Create: `ui-nextjs/components/explore/StateAnnotation.tsx`
- Modify: `ui-nextjs/app/explore/page.tsx`

- [ ] **Step 1: Create StateAnnotation component**

Create `ui-nextjs/components/explore/StateAnnotation.tsx` that fetches from `/api/explore/state-summary` and displays inline stats:

```tsx
"use client";

import { useState, useEffect } from "react";
import { humanizeMetric } from "@/lib/explore-config";
import { API_BASE } from "@/lib/api";
import { useAuthHeaders } from "@/hooks/useAuthHeaders";

interface StateAnnotationProps {
  source: string;
  stateFips: string;
  metric: string | null;
  accent: string;
}

interface StateSummaryData {
  state_name: string;
  value: number;
  national_average: number;
  national_rank: number;
  national_rank_total: number;
  percentile: number;
  racial_gap: {
    max_ratio: number;
    max_ratio_label: string;
  } | null;
}

export default function StateAnnotation({
  source,
  stateFips,
  metric,
  accent,
}: StateAnnotationProps) {
  const [data, setData] = useState<StateSummaryData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const headers = useAuthHeaders();

  useEffect(() => {
    if (!metric || !stateFips) return;

    const controller = new AbortController();
    setLoading(true);
    setError(null);

    const params = new URLSearchParams({ source, state_fips: stateFips, metric });
    fetch(`${API_BASE}/api/explore/state-summary?${params}`, {
      headers,
      signal: controller.signal,
    })
      .then((r) => {
        if (!r.ok) throw new Error("Failed to load summary");
        return r.json();
      })
      .then(setData)
      .catch((e) => {
        if (e.name !== "AbortError") setError(e.message);
      })
      .finally(() => setLoading(false));

    return () => controller.abort();
  }, [source, stateFips, metric, headers]);

  if (loading) {
    return (
      <div className="flex gap-3 animate-pulse">
        <div className="h-4 w-20 rounded bg-[#333]" />
        <div className="h-4 w-16 rounded bg-[#333]" />
        <div className="h-4 w-24 rounded bg-[#333]" />
      </div>
    );
  }

  if (error || !data) return null;

  const isAboveAvg = data.value >= data.national_average;

  return (
    <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-[#999]">
      <span>
        Ranked{" "}
        <span className="font-medium text-white">
          #{data.national_rank}
        </span>{" "}
        of {data.national_rank_total} states
      </span>
      <span>
        <span
          className="font-medium"
          style={{ color: isAboveAvg ? accent : "#999" }}
        >
          {data.percentile.toFixed(0)}th
        </span>{" "}
        percentile
      </span>
      {data.racial_gap && (
        <span className="text-[#a8a8a8]">
          {data.racial_gap.max_ratio_label}
        </span>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Wire into explore page**

In `ui-nextjs/app/explore/page.tsx`, add `StateAnnotation` in the state detail section, between the state name header and the chart:

```tsx
import StateAnnotation from "@/components/explore/StateAnnotation";

// After PolicyBadge, before the chart conditional:
<StateAnnotation
  source={activeSource.key}
  stateFips={filters.selectedState}
  metric={filters.metric}
  accent={activeSource.accent}
/>
```

- [ ] **Step 3: Build and lint**

Run: `cd ui-nextjs && npm run build && npm run lint`

- [ ] **Step 4: Commit**

```bash
git add ui-nextjs/components/explore/StateAnnotation.tsx ui-nextjs/app/explore/page.tsx
git commit -m "feat: add inline state annotation panel with rank, percentile, racial gap"
```

---

## Task 3.2: "Explain this view" LLM endpoint

**Files:**
- Modify: `src/d4bl/app/explore_insights.py`
- Modify: `src/d4bl/app/schemas.py`
- Test: `tests/test_explore_insights.py`

- [ ] **Step 1: Add explain schemas**

In `src/d4bl/app/schemas.py`:

```python
class ExplainRequest(BaseModel):
    source: str
    metric: str
    state_fips: str
    state_name: str
    value: float
    national_average: float
    racial_gap: RacialGap | None = None
    year: int

class ExplainResponse(BaseModel):
    narrative: str
    methodology_note: str
    caveats: list[str]
    generated_at: str
```

- [ ] **Step 2: Add explain endpoint to explore_insights.py**

```python
from datetime import datetime, timezone
from litellm import acompletion
from d4bl.app.schemas import ExplainRequest, ExplainResponse
from d4bl.settings import get_settings

EXPLAIN_SYSTEM_PROMPT = """You are a racial equity data analyst writing for policy researchers.
Given structured data about a U.S. state, write a concise 2-3 paragraph analysis.

Your analysis must:
1. Explain the metric value in context (what does this number mean for residents)
2. Compare to the national average with plain-language framing
3. Describe racial disparities if data is provided
4. Note any relevant policy implications

Be precise, cite the numbers, and avoid speculation. Write for an expert audience."""

EXPLAIN_USER_TEMPLATE = """Analyze this data:

State: {state_name} ({state_fips})
Metric: {metric}
Value: {value}
National Average: {national_average}
Year: {year}
Data Source: {source}
{racial_gap_section}

Provide your analysis as JSON with these fields:
- narrative: 2-3 paragraph analysis
- methodology_note: brief note about data source and collection method
- caveats: array of known limitations"""


@router.post("/explain", response_model=ExplainResponse)
async def explain_view(
    request: ExplainRequest,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate LLM explanation of the current explore view."""
    racial_gap_section = ""
    if request.racial_gap:
        groups = ", ".join(
            f"{g.race}: {g.value}" for g in request.racial_gap.groups
        )
        racial_gap_section = (
            f"Racial breakdown: {groups}\n"
            f"Max gap: {request.racial_gap.max_ratio_label}"
        )

    user_prompt = EXPLAIN_USER_TEMPLATE.format(
        state_name=request.state_name,
        state_fips=request.state_fips,
        metric=request.metric,
        value=request.value,
        national_average=request.national_average,
        year=request.year,
        source=request.source,
        racial_gap_section=racial_gap_section,
    )

    try:
        settings = get_settings()
        response = await acompletion(
            model=f"ollama/{settings.ollama_model}",
            messages=[
                {"role": "system", "content": EXPLAIN_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            api_base=settings.ollama_base_url,
            max_tokens=500,
            temperature=0.3,
            timeout=30,
        )

        raw = response.choices[0].message.content

        # Try to parse as JSON, fall back to using raw text as narrative
        import json
        try:
            parsed = json.loads(raw)
            narrative = parsed.get("narrative", raw)
            methodology = parsed.get("methodology_note", f"Data from {request.source}, {request.year}")
            caveats = parsed.get("caveats", [])
        except json.JSONDecodeError:
            narrative = raw
            methodology = f"Data from {request.source}, {request.year}"
            caveats = []

        return ExplainResponse(
            narrative=narrative,
            methodology_note=methodology,
            caveats=caveats if isinstance(caveats, list) else [str(caveats)],
            generated_at=datetime.now(timezone.utc).isoformat(),
        )
    except Exception as e:
        logger.error("Explain endpoint failed: %s", e, exc_info=True)
        raise HTTPException(status_code=503, detail="AI analysis unavailable — check that Ollama is running")
```

- [ ] **Step 3: Write tests**

Add to `tests/test_explore_insights.py`:

```python
class TestExplainEndpoint:
    @pytest.mark.asyncio
    async def test_returns_narrative(self, override_auth):
        app = override_auth
        from d4bl.infra.database import get_db

        mock_db = AsyncMock()
        mock_freshness = MagicMock()
        mock_freshness.scalar.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_freshness)

        async def override_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_get_db

        with patch("d4bl.app.explore_insights.acompletion") as mock_llm:
            mock_response = MagicMock()
            mock_response.choices = [MagicMock()]
            mock_response.choices[0].message.content = json.dumps({
                "narrative": "Test analysis.",
                "methodology_note": "Census ACS 5-year estimates",
                "caveats": ["Self-reported data"],
            })
            mock_llm.return_value = mock_response

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post("/api/explore/explain", json={
                    "source": "census",
                    "metric": "poverty_rate",
                    "state_fips": "28",
                    "state_name": "Mississippi",
                    "value": 19.6,
                    "national_average": 12.4,
                    "year": 2022,
                })

        assert resp.status_code == 200
        data = resp.json()
        assert "narrative" in data
        assert "methodology_note" in data
        assert "caveats" in data
        assert "generated_at" in data

    @pytest.mark.asyncio
    async def test_503_when_ollama_down(self, override_auth):
        app = override_auth
        from d4bl.infra.database import get_db

        mock_db = AsyncMock()
        mock_freshness = MagicMock()
        mock_freshness.scalar.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_freshness)

        async def override_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_get_db

        with patch("d4bl.app.explore_insights.acompletion", side_effect=Exception("Connection refused")):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post("/api/explore/explain", json={
                    "source": "census",
                    "metric": "poverty_rate",
                    "state_fips": "28",
                    "state_name": "Mississippi",
                    "value": 19.6,
                    "national_average": 12.4,
                    "year": 2022,
                })

        assert resp.status_code == 503
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_explore_insights.py -v`

- [ ] **Step 5: Commit**

```bash
git add src/d4bl/app/explore_insights.py src/d4bl/app/schemas.py tests/test_explore_insights.py
git commit -m "feat: add /api/explore/explain LLM endpoint with structured narrative"
```

---

## Task 3.3: "Explain" button + collapsible AI panel

**Files:**
- Create: `ui-nextjs/components/explore/ExplainPanel.tsx`
- Modify: `ui-nextjs/app/explore/page.tsx`

- [ ] **Step 1: Create ExplainPanel component**

Create `ui-nextjs/components/explore/ExplainPanel.tsx`:

The component shows an "Explain" button. On click, calls POST `/api/explore/explain` with the current view context. Shows the narrative in a collapsible panel with "AI Analysis" badge. Handles loading, error (with retry), and timeout states per Appendix C.

Key features:
- Button: "✦ Explain" with accent color
- Loading: animated shimmer
- Panel: collapsible, shows narrative, methodology note, caveats
- Error: "AI analysis unavailable" with retry button
- Timeout: 10 second fetch timeout

- [ ] **Step 2: Wire into explore page**

Add ExplainPanel in the state detail section, after StateAnnotation and before the chart:

```tsx
import ExplainPanel from "@/components/explore/ExplainPanel";

<ExplainPanel
  source={activeSource.key}
  metric={filters.metric || exploreData.available_metrics?.[0] || ""}
  stateFips={filters.selectedState}
  stateName={selectedStateName}
  value={stateDetailValue}
  nationalAverage={exploreData.national_average ?? 0}
  year={/* latest year from data */}
  accent={activeSource.accent}
/>
```

- [ ] **Step 3: Build and lint**

Run: `cd ui-nextjs && npm run build && npm run lint`

- [ ] **Step 4: Commit**

```bash
git add ui-nextjs/components/explore/ExplainPanel.tsx ui-nextjs/app/explore/page.tsx
git commit -m "feat: add Explain button with collapsible AI analysis panel"
```

---

## Task 3.4a: Context-aware query endpoint

**Files:**
- Modify: `src/d4bl/app/explore_insights.py`
- Modify: `src/d4bl/app/schemas.py`
- Test: `tests/test_explore_insights.py`

- [ ] **Step 1: Add query schemas**

In `src/d4bl/app/schemas.py`:

```python
class ExploreQueryContext(BaseModel):
    source: str
    metric: str | None = None
    state_fips: str | None = None
    race: str | None = None
    year: int | None = None

class ExploreQueryRequest(BaseModel):
    question: str
    context: ExploreQueryContext

class ExploreQueryResponse(BaseModel):
    answer: str
    data: list[ExploreRow] | None = None
    visualization_hint: str | None = None
```

- [ ] **Step 2: Add query endpoint**

In `src/d4bl/app/explore_insights.py`:

```python
from d4bl.app.schemas import ExploreQueryRequest, ExploreQueryResponse, ExploreRow
from d4bl.query.engine import QueryEngine

_query_engine: QueryEngine | None = None

def _get_query_engine() -> QueryEngine:
    global _query_engine
    if _query_engine is None:
        _query_engine = QueryEngine()
    return _query_engine


@router.post("/query", response_model=ExploreQueryResponse)
async def explore_query(
    request: ExploreQueryRequest,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Context-aware natural language query for explore page."""
    ctx = request.context
    # Prepend context to the question for the query engine
    context_parts = [f"Data source: {ctx.source}"]
    if ctx.metric:
        context_parts.append(f"Metric: {ctx.metric}")
    if ctx.state_fips:
        context_parts.append(f"State FIPS: {ctx.state_fips}")
    if ctx.race:
        context_parts.append(f"Race filter: {ctx.race}")
    if ctx.year:
        context_parts.append(f"Year: {ctx.year}")

    augmented_question = (
        f"Context: {', '.join(context_parts)}. "
        f"Question: {request.question}"
    )

    try:
        engine = _get_query_engine()
        result = await engine.query(db=db, question=augmented_question)

        return ExploreQueryResponse(
            answer=result.answer,
            data=None,  # Future: parse structured data from results
            visualization_hint=None,
        )
    except Exception as e:
        logger.error("Explore query failed: %s", e, exc_info=True)
        raise HTTPException(status_code=503, detail=str(e))
```

- [ ] **Step 3: Write tests**

Add to `tests/test_explore_insights.py`:

```python
class TestExploreQueryEndpoint:
    @pytest.mark.asyncio
    async def test_returns_answer(self, override_auth):
        app = override_auth
        from d4bl.infra.database import get_db

        mock_db = AsyncMock()
        mock_freshness = MagicMock()
        mock_freshness.scalar.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_freshness)

        async def override_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_get_db

        mock_result = MagicMock()
        mock_result.answer = "Mississippi has the highest poverty rate."
        mock_result.sources = []

        with patch("d4bl.app.explore_insights._get_query_engine") as mock_engine_fn:
            mock_engine = MagicMock()
            mock_engine.query = AsyncMock(return_value=mock_result)
            mock_engine_fn.return_value = mock_engine

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post("/api/explore/query", json={
                    "question": "Which state has the highest poverty rate?",
                    "context": {"source": "census", "metric": "poverty_rate"},
                })

        assert resp.status_code == 200
        data = resp.json()
        assert "answer" in data
        assert "Mississippi" in data["answer"]
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_explore_insights.py -v`

- [ ] **Step 5: Commit**

```bash
git add src/d4bl/app/explore_insights.py src/d4bl/app/schemas.py tests/test_explore_insights.py
git commit -m "feat: add /api/explore/query context-aware endpoint using query engine"
```

---

## Task 3.4b: Conversational query bar UI

**Files:**
- Create: `ui-nextjs/components/explore/ExploreQueryBar.tsx`
- Modify: `ui-nextjs/app/explore/page.tsx`

- [ ] **Step 1: Create ExploreQueryBar component**

Create `ui-nextjs/components/explore/ExploreQueryBar.tsx`:

The component shows a text input with placeholder "Ask about this data..." and a submit button. On submit, POSTs to `/api/explore/query` with the question and current explore context. Displays the answer inline below the input. Handles loading, error, and empty states per Appendix C.

Key features:
- Input: text field with accent-colored border on focus
- Submit: button or Enter key
- Loading: "Analyzing..." with animated dots
- Result: answer text below input
- Error: inline error message with the error detail
- Context: passes current source, metric, state_fips, race, year

- [ ] **Step 2: Wire into explore page**

Add ExploreQueryBar at the bottom of the explore page, after the state detail section:

```tsx
import ExploreQueryBar from "@/components/explore/ExploreQueryBar";

{exploreData && (
  <ExploreQueryBar
    source={activeSource.key}
    metric={filters.metric}
    stateFips={filters.selectedState}
    race={filters.race}
    year={filters.year}
    accent={activeSource.accent}
  />
)}
```

- [ ] **Step 3: Build and lint**

Run: `cd ui-nextjs && npm run build && npm run lint`

- [ ] **Step 4: Commit**

```bash
git add ui-nextjs/components/explore/ExploreQueryBar.tsx ui-nextjs/app/explore/page.tsx
git commit -m "feat: add conversational query bar with context-aware explore queries"
```

---

## Post-Epic Verification

- [ ] **Run full test suite**

```bash
python -m pytest tests/ -q
cd ui-nextjs && npm run build && npm run lint
```

- [ ] **Manual smoke test**
1. Select a state — inline annotations appear (rank, percentile, racial gap)
2. Click "Explain" — loading state, then AI narrative appears with methodology note
3. Click "Explain" again — panel collapses
4. Type a question in query bar — answer appears inline
5. Disconnect Ollama — Explain shows "AI analysis unavailable" with retry button
6. Query bar shows appropriate error when Ollama is down
