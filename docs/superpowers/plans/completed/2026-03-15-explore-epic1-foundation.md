# Epic 1: Foundation — Map, Legend, Performance

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the most visible explore page problems — slow loading, missing map legend, and bad defaults — with no LLM dependency.

**Architecture:** Backend pre-aggregates tract-level data into a `state_summary` table during ingestion, unifies the Census ACS endpoint to return `ExploreResponse`, and adds TTL caching. Frontend adds localStorage persistence, a gradient legend bar, and directional color scales.

**Tech Stack:** Python/SQLAlchemy (backend), Next.js/React/TypeScript (frontend), d3-interpolate (color, already installed), cachetools (caching), react-simple-maps (existing map)

**Spec:** `docs/superpowers/specs/2026-03-15-explore-page-overhaul-design.md`

---

## File Structure

### Backend (create)
- `src/d4bl/infra/state_summary.py` — StateSummary SQLAlchemy model
- `scripts/ingestion/aggregate_state_summaries.py` — Post-ingestion aggregation script
- `src/d4bl/app/cache.py` — TTL cache middleware for explore endpoints

### Backend (modify)
- `src/d4bl/infra/database.py:111-146` — Update CensusIndicator query pattern
- `src/d4bl/app/api.py:598-641` — Rewrite `/api/explore/indicators` to return ExploreResponse
- `src/d4bl/app/api.py:683-740,884-941,942-1010,1130-1190` — Wire EPA, USDA, DOE, Census Decennial endpoints to query state_summary table instead of runtime aggregation
- `src/d4bl/app/explore_helpers.py:42-70` — Add build_response_from_summary() helper for state_summary queries
- `scripts/run_ingestion.py` — Call aggregate_state_summaries after source ingestion

### Frontend (create)
- `ui-nextjs/components/explore/MapLegend.tsx` — Gradient legend bar component

### Frontend (modify)
- `ui-nextjs/lib/explore-config.ts:41-199` — Add `highIsGood` and metric metadata per source
- `ui-nextjs/components/explore/StateMap.tsx:29-54` — Replace color scale with directional scales
- `ui-nextjs/app/explore/page.tsx:25-39,57-168` — Remove Census-specific transformation, add localStorage persistence

### Tests (create)
- `tests/test_state_summary.py` — Model + aggregation logic tests
- `tests/test_explore_cache.py` — Cache TTL + invalidation tests
- `tests/test_census_unified.py` — Census ACS ExploreResponse shape test

---

## Chunk 1: Backend Performance

### Task 1.1: Pre-aggregate tract-level data to state summaries

**Files:**
- Create: `src/d4bl/infra/state_summary.py`
- Modify: `src/d4bl/infra/database.py` (add import)
- Create: `scripts/ingestion/aggregate_state_summaries.py`
- Modify: `scripts/run_ingestion.py`
- Test: `tests/test_state_summary.py`

- [ ] **Step 1: Write the StateSummary model test**

```python
# tests/test_state_summary.py
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from d4bl.infra.state_summary import StateSummary
from d4bl.infra.database import Base


def test_state_summary_model_columns():
    """StateSummary model has all required columns."""
    assert hasattr(StateSummary, "source")
    assert hasattr(StateSummary, "state_fips")
    assert hasattr(StateSummary, "state_name")
    assert hasattr(StateSummary, "metric")
    assert hasattr(StateSummary, "race")
    assert hasattr(StateSummary, "year")
    assert hasattr(StateSummary, "value")
    assert hasattr(StateSummary, "sample_size")


def test_state_summary_unique_constraint():
    """StateSummary has unique constraint on (source, state_fips, metric, race, year)."""
    table = StateSummary.__table__
    unique_constraints = [c for c in table.constraints if hasattr(c, "columns") and len(c.columns) > 1]
    constraint_cols = None
    for uc in unique_constraints:
        cols = {col.name for col in uc.columns}
        if "source" in cols:
            constraint_cols = cols
    assert constraint_cols == {"source", "state_fips", "metric", "race", "year"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/william-meroxa/Development/d4bl_ai_agent && python -m pytest tests/test_state_summary.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'd4bl.infra.state_summary'`

- [ ] **Step 3: Write the StateSummary model**

```python
# src/d4bl/infra/state_summary.py
"""Denormalized state-level summary table for pre-aggregated explore data."""

from sqlalchemy import Column, Float, Integer, String, UniqueConstraint
from d4bl.infra.database import Base


class StateSummary(Base):
    __tablename__ = "state_summary"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source = Column(String(50), nullable=False, index=True)
    state_fips = Column(String(2), nullable=False, index=True)
    state_name = Column(String(100), nullable=False)
    metric = Column(String(200), nullable=False)
    race = Column(String(50), nullable=False, default="total")
    year = Column(Integer, nullable=False)
    value = Column(Float, nullable=False)
    sample_size = Column(Integer, nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "source", "state_fips", "metric", "race", "year",
            name="uq_state_summary_source_state_metric_race_year",
        ),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/william-meroxa/Development/d4bl_ai_agent && python -m pytest tests/test_state_summary.py -v`
Expected: PASS

- [ ] **Step 5: Write aggregation script tests**

```python
# tests/test_state_summary.py (append)
from unittest.mock import MagicMock, patch
from scripts.ingestion.aggregate_state_summaries import (
    aggregate_epa,
    aggregate_usda,
    aggregate_census_demographics,
    aggregate_doe,
)


def test_aggregate_epa_uses_population_weighted_avg():
    """EPA aggregation weights by tract population."""
    # Two tracts in state 01: pop 1000 val 80, pop 3000 val 40
    # Weighted avg = (1000*80 + 3000*40) / (1000+3000) = 200000/4000 = 50.0
    mock_session = MagicMock()
    rows = [
        {"state_fips": "01", "state_name": "Alabama", "indicator": "PM25", "year": 2022,
         "raw_value": 80.0, "population": 1000},
        {"state_fips": "01", "state_name": "Alabama", "indicator": "PM25", "year": 2022,
         "raw_value": 40.0, "population": 3000},
    ]
    result = aggregate_epa(rows)
    assert len(result) == 1
    assert result[0]["value"] == pytest.approx(50.0)
    assert result[0]["sample_size"] == 4000


def test_aggregate_census_demographics_sums_population():
    """Census Demographics sums tract populations and re-derives pct_of_total."""
    rows = [
        {"state_fips": "01", "state_name": "Alabama", "race": "black", "year": 2020,
         "population": 500},
        {"state_fips": "01", "state_name": "Alabama", "race": "black", "year": 2020,
         "population": 300},
        {"state_fips": "01", "state_name": "Alabama", "race": "total", "year": 2020,
         "population": 2000},
        {"state_fips": "01", "state_name": "Alabama", "race": "total", "year": 2020,
         "population": 3000},
    ]
    result = aggregate_census_demographics(rows)
    black_row = [r for r in result if r["race"] == "black"][0]
    total_row = [r for r in result if r["race"] == "total"][0]
    assert black_row["value"] == 800  # sum
    assert total_row["value"] == 5000  # sum
    assert black_row["sample_size"] == 5000  # state total pop for context
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `cd /Users/william-meroxa/Development/d4bl_ai_agent && python -m pytest tests/test_state_summary.py -v -k aggregate`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 7: Write the aggregation script**

```python
# scripts/ingestion/aggregate_state_summaries.py
"""Post-ingestion aggregation: collapse tract/county/district data to state-level summaries."""

import logging
from collections import defaultdict

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from d4bl.infra.state_summary import StateSummary
from d4bl.settings import get_settings

logger = logging.getLogger(__name__)


def aggregate_epa(rows: list[dict]) -> list[dict]:
    """Population-weighted average of EPA tract indicators per state."""
    groups = defaultdict(lambda: {"weighted_sum": 0.0, "total_pop": 0, "state_name": ""})
    for r in rows:
        key = (r["state_fips"], r["indicator"], r.get("year", 0))
        g = groups[key]
        pop = r.get("population") or 0
        g["weighted_sum"] += (r.get("raw_value") or 0) * pop
        g["total_pop"] += pop
        g["state_name"] = r["state_name"]
    result = []
    for (state_fips, metric, year), g in groups.items():
        if g["total_pop"] > 0:
            result.append({
                "source": "epa",
                "state_fips": state_fips,
                "state_name": g["state_name"],
                "metric": metric,
                "race": "total",
                "year": year,
                "value": g["weighted_sum"] / g["total_pop"],
                "sample_size": g["total_pop"],
            })
    return result


def aggregate_usda(rows: list[dict]) -> list[dict]:
    """Population-weighted average of USDA tract indicators per state."""
    groups = defaultdict(lambda: {"weighted_sum": 0.0, "total_pop": 0, "state_name": ""})
    for r in rows:
        key = (r["state_fips"], r["indicator"], r.get("year", 0))
        g = groups[key]
        pop = r.get("population") or 0
        g["weighted_sum"] += (r.get("value") or 0) * pop
        g["total_pop"] += pop
        g["state_name"] = r["state_name"]
    result = []
    for (state_fips, metric, year), g in groups.items():
        if g["total_pop"] > 0:
            result.append({
                "source": "usda",
                "state_fips": state_fips,
                "state_name": g["state_name"],
                "metric": metric,
                "race": "total",
                "year": year,
                "value": g["weighted_sum"] / g["total_pop"],
                "sample_size": g["total_pop"],
            })
    return result


def aggregate_census_demographics(rows: list[dict]) -> list[dict]:
    """Sum tract populations per state/race/year, re-derive pct_of_total."""
    groups = defaultdict(lambda: {"population": 0, "state_name": ""})
    for r in rows:
        key = (r["state_fips"], r["race"], r.get("year", 0))
        groups[key]["population"] += r.get("population") or 0
        groups[key]["state_name"] = r["state_name"]

    # Get state totals for pct_of_total
    state_totals = {}
    for (state_fips, race, year), g in groups.items():
        if race == "total":
            state_totals[(state_fips, year)] = g["population"]

    result = []
    for (state_fips, race, year), g in groups.items():
        total = state_totals.get((state_fips, year), 0)
        result.append({
            "source": "census-demographics",
            "state_fips": state_fips,
            "state_name": g["state_name"],
            "metric": "population",
            "race": race,
            "year": year,
            "value": g["population"],
            "sample_size": total,
        })
    return result


def aggregate_doe(rows: list[dict]) -> list[dict]:
    """Enrollment-weighted average of DOE district metrics per state."""
    groups = defaultdict(lambda: {"weighted_sum": 0.0, "total_enrollment": 0, "state_name": ""})
    for r in rows:
        # school_year is a string like "2020-2021" — extract start year as int
        school_year_str = r.get("school_year", "0")
        year_int = int(school_year_str.split("-")[0]) if "-" in str(school_year_str) else int(school_year_str)
        key = (r["state"], r["metric"], r["race"], year_int)
        g = groups[key]
        enrollment = r.get("total_enrollment") or 0
        g["weighted_sum"] += (r.get("value") or 0) * enrollment
        g["total_enrollment"] += enrollment
        g["state_name"] = r["state_name"]
    result = []
    for (state_abbrev, metric, race, year_int), g in groups.items():
        if g["total_enrollment"] > 0:
            result.append({
                "source": "doe",
                "state_fips": state_abbrev,  # DOE uses state abbreviation
                "state_name": g["state_name"],
                "metric": metric,
                "race": race,
                "year": year_int,
                "value": g["weighted_sum"] / g["total_enrollment"],
                "sample_size": g["total_enrollment"],
            })
    return result


def _get_sync_session() -> sessionmaker:
    """Create a synchronous session for aggregation scripts.
    Requires psycopg2-binary (or psycopg) to be installed.
    """
    from d4bl.infra.database import get_database_url
    sync_url = get_database_url().replace("+asyncpg", "")
    engine = create_engine(sync_url)
    return sessionmaker(bind=engine)


def run_aggregation(sources: list[str] | None = None):
    """Run state-level aggregation for specified sources (or all)."""
    all_sources = ["epa", "usda", "census-demographics", "doe"]
    targets = sources or all_sources
    SessionLocal = _get_sync_session()

    with SessionLocal() as session:
        for source in targets:
            logger.info(f"Aggregating {source}...")
            _aggregate_source(session, source)
        session.commit()
    logger.info("State summary aggregation complete.")


def _aggregate_source(session: Session, source: str):
    """Fetch raw data and upsert aggregated rows for one source."""
    fetch_sql = _fetch_query(source)
    if not fetch_sql:
        logger.warning(f"No aggregation query for source: {source}")
        return

    rows = [dict(r._mapping) for r in session.execute(text(fetch_sql))]
    if not rows:
        logger.info(f"No data found for {source}, skipping.")
        return

    aggregate_fn = {
        "epa": aggregate_epa,
        "usda": aggregate_usda,
        "census-demographics": aggregate_census_demographics,
        "doe": aggregate_doe,
    }[source]

    summaries = aggregate_fn(rows)
    logger.info(f"  {source}: {len(rows)} raw rows → {len(summaries)} summary rows")

    # Delete existing summaries for this source, then insert new ones
    session.query(StateSummary).filter(StateSummary.source == source).delete()
    for s in summaries:
        session.add(StateSummary(**s))


def _fetch_query(source: str) -> str | None:
    """Return SQL to fetch raw data for aggregation."""
    queries = {
        "epa": """
            SELECT state_fips, state_name, indicator, year,
                   raw_value, population
            FROM epa_environmental_justice
            WHERE population IS NOT NULL AND raw_value IS NOT NULL
        """,
        "usda": """
            SELECT state_fips, state_name, indicator, year,
                   value, population
            FROM usda_food_access
            WHERE population IS NOT NULL AND value IS NOT NULL
        """,
        "census-demographics": """
            SELECT state_fips, state_name, race, year, population
            FROM census_demographics
            WHERE geo_type = 'tract' AND population IS NOT NULL
        """,
        "doe": """
            SELECT state, state_name, metric, race, school_year, value, total_enrollment
            FROM doe_civil_rights
            WHERE total_enrollment IS NOT NULL AND value IS NOT NULL
        """,
    }
    return queries.get(source)


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    sources = sys.argv[1:] if len(sys.argv) > 1 else None
    run_aggregation(sources)
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `cd /Users/william-meroxa/Development/d4bl_ai_agent && python -m pytest tests/test_state_summary.py -v`
Expected: PASS

- [ ] **Step 9: Wire aggregation into run_ingestion.py**

Modify `scripts/run_ingestion.py` — add a post-ingestion step. At the end of the `main()` function, after all sources have run, add:

```python
from scripts.ingestion.aggregate_state_summaries import run_aggregation

# After all ingestion completes (results is a list of (name, records, duration, status) tuples):
AGGREGATION_SOURCES = {"epa", "usda", "census_decennial", "doe"}
completed_sources = [name for name, _, _, status in results if status == "ok" and name in AGGREGATION_SOURCES]
if completed_sources:
    logger.info(f"Running state-level aggregation for: {completed_sources}")
    run_aggregation(completed_sources)
```

- [ ] **Step 10: Create database migration for state_summary table**

```sql
-- supabase/migrations/20260315000001_add_state_summary_table.sql
CREATE TABLE IF NOT EXISTS state_summary (
    id SERIAL PRIMARY KEY,
    source VARCHAR(50) NOT NULL,
    state_fips VARCHAR(2) NOT NULL,
    state_name VARCHAR(100) NOT NULL,
    metric VARCHAR(200) NOT NULL,
    race VARCHAR(50) NOT NULL DEFAULT 'total',
    year INTEGER NOT NULL,
    value DOUBLE PRECISION NOT NULL,
    sample_size INTEGER,
    CONSTRAINT uq_state_summary_source_state_metric_race_year
        UNIQUE (source, state_fips, metric, race, year)
);

CREATE INDEX IF NOT EXISTS idx_state_summary_source ON state_summary (source);
CREATE INDEX IF NOT EXISTS idx_state_summary_state_fips ON state_summary (state_fips);
CREATE INDEX IF NOT EXISTS idx_state_summary_source_metric ON state_summary (source, metric);
```

- [ ] **Step 11: Commit**

```bash
git add src/d4bl/infra/state_summary.py scripts/ingestion/aggregate_state_summaries.py tests/test_state_summary.py supabase/migrations/20260315000001_add_state_summary_table.sql
git commit -m "feat: add state_summary model and aggregation script for tract-level sources"
```

---

### Task 1.1b: Wire EPA, USDA, DOE, Census Decennial endpoints to state_summary

**Files:**
- Modify: `src/d4bl/app/api.py:683-740` (EPA endpoint)
- Modify: `src/d4bl/app/api.py:884-941` (USDA endpoint)
- Modify: `src/d4bl/app/api.py:942-1010` (DOE endpoint)
- Modify: `src/d4bl/app/api.py:1130-1190` (Census Decennial endpoint)
- Modify: `src/d4bl/app/explore_helpers.py` (add state_summary query helper)

- [ ] **Step 1: Add build_response_from_summary helper**

In `src/d4bl/app/explore_helpers.py`, add a helper that queries the `state_summary` table and returns `ExploreResponse`:

```python
from d4bl.infra.state_summary import StateSummary

async def build_response_from_summary(
    session,
    source: str,
    state_fips: str | None = None,
    metric_key: str = "metric",
    metric_value: str | None = None,
    race: str | None = None,
    year: int | None = None,
    limit: int = 1000,
) -> dict:
    """Query state_summary table and return ExploreResponse shape."""
    query = select(StateSummary).where(StateSummary.source == source)
    if state_fips:
        query = query.where(StateSummary.state_fips == state_fips)
    if metric_value:
        query = query.where(StateSummary.metric == metric_value)
    if race:
        query = query.where(StateSummary.race == race)
    if year:
        query = query.where(StateSummary.year == year)
    query = query.limit(min(limit, 5000))

    result = await session.execute(query)
    rows_raw = result.scalars().all()

    rows = [
        {
            "state_fips": r.state_fips,
            "state_name": r.state_name,
            "value": r.value,
            "metric": r.metric,
            "year": r.year,
            "race": r.race,
        }
        for r in rows_raw
    ]

    return {
        "rows": rows,
        "national_average": compute_national_avg(rows),
        "available_metrics": distinct_values(rows, "metric"),
        "available_years": distinct_values(rows, "year"),
        "available_races": distinct_values(rows, "race"),
    }
```

- [ ] **Step 2: Replace EPA endpoint to use state_summary**

In the EPA endpoint (lines 683-740), replace the runtime aggregation query with:

```python
return await build_response_from_summary(
    db, source="epa", state_fips=state_fips,
    metric_value=indicator, year=year, limit=limit,
)
```

- [ ] **Step 3: Replace USDA, DOE, Census Decennial endpoints similarly**

Apply the same pattern to USDA (lines 884-941), DOE (lines 942-1010), and Census Decennial (lines 1130-1190), passing the appropriate `source` key and filter parameter names.

- [ ] **Step 4: Run existing tests to verify no regressions**

Run: `cd /Users/william-meroxa/Development/d4bl_ai_agent && python -m pytest tests/ -v --timeout=30`
Expected: All tests pass

- [ ] **Step 5: Commit**

```bash
git add src/d4bl/app/api.py src/d4bl/app/explore_helpers.py
git commit -m "feat: wire EPA, USDA, DOE, Census Decennial endpoints to pre-aggregated state_summary"
```

---

### Task 1.2: Unify Census ACS endpoint to ExploreResponse

**Files:**
- Modify: `src/d4bl/app/api.py:598-641`
- Modify: `src/d4bl/app/explore_helpers.py`
- Modify: `ui-nextjs/app/explore/page.tsx:57-168`
- Modify: `ui-nextjs/lib/explore-config.ts:16-28`
- Test: `tests/test_census_unified.py`

- [ ] **Step 1: Write the test for unified Census endpoint**

```python
# tests/test_census_unified.py
"""Test that /api/explore/indicators returns ExploreResponse shape."""
import pytest
from unittest.mock import MagicMock, AsyncMock
from d4bl.app.api import app
from httpx import AsyncClient, ASGITransport


@pytest.mark.asyncio
async def test_census_endpoint_returns_explore_response():
    """Census ACS endpoint returns ExploreResponse with rows, national_average, available_*."""
    from d4bl.app.api import get_current_user, get_db

    # Mock DB session that returns empty results
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []

    async def mock_db():
        mock_session = MagicMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        yield mock_session

    app.dependency_overrides[get_current_user] = lambda: {"sub": "test"}
    app.dependency_overrides[get_db] = mock_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/explore/indicators")
    finally:
        app.dependency_overrides.clear()
    data = resp.json()
    assert "rows" in data
    assert "national_average" in data
    assert "available_metrics" in data
    assert "available_years" in data
    assert "available_races" in data
    # Each row should have ExploreRow shape
    if data["rows"]:
        row = data["rows"][0]
        assert "state_fips" in row
        assert "state_name" in row
        assert "value" in row
        assert "metric" in row
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/william-meroxa/Development/d4bl_ai_agent && python -m pytest tests/test_census_unified.py -v`
Expected: FAIL — response returns `list[IndicatorItem]`, not `ExploreResponse`

- [ ] **Step 3: Rewrite the Census ACS endpoint in api.py**

Replace the `/api/explore/indicators` handler (lines 598-641) with a version that returns `ExploreResponse`. The key changes:
- Query CensusIndicator filtered to `geography_type='state'`
- Transform rows to `ExploreRow` shape (state_fips, state_name, value, metric, year, race)
- Use `build_state_agg_response` pattern to compute national_average and available_* lists
- When `state_fips` param provided AND race data exists, include per-race rows

```python
@app.get("/api/explore/indicators")
async def get_census_indicators(
    state_fips: str | None = None,
    metric: str | None = None,
    race: str | None = None,
    year: int | None = None,
    limit: int = 1000,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Census ACS indicators — returns ExploreResponse."""
    query = select(CensusIndicator).where(
        CensusIndicator.geography_type == "state"
    )
    if state_fips:
        query = query.where(CensusIndicator.state_fips == state_fips)
    if metric:
        query = query.where(CensusIndicator.metric == metric)
    if race:
        query = query.where(CensusIndicator.race == race)
    if year:
        query = query.where(CensusIndicator.year == year)
    query = query.limit(min(limit, 5000))
    result = await db.execute(query)
    rows_raw = result.scalars().all()

    rows = [
        {
            "state_fips": r.state_fips,
            "state_name": r.geography_name,
            "value": r.value,
            "metric": r.metric,
            "year": r.year,
            "race": r.race,
        }
        for r in rows_raw
    ]

    return {
        "rows": rows,
        "national_average": compute_national_avg(rows),
        "available_metrics": distinct_values(rows, "metric"),
        "available_years": distinct_values(rows, "year"),
        "available_races": distinct_values(rows, "race"),
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/william-meroxa/Development/d4bl_ai_agent && python -m pytest tests/test_census_unified.py -v`
Expected: PASS

- [ ] **Step 5: Remove Census-specific frontend transformation**

In `ui-nextjs/app/explore/page.tsx`, the `fetchData` function (lines 57-168) has a Census-specific code path (lines 66-115) that:
1. Calls `/api/explore/indicators` and gets `IndicatorRow[]`
2. Transforms to `ExploreRow[]` using `toIndicatorRow`
3. Fetches racial breakdown separately

Replace this with the unified path all other sources use (lines 117-131). The Census source should now work like every other source — one fetch, ExploreResponse back.

Also remove or simplify the `toIndicatorRow` helper in `explore-config.ts` (lines 16-28) since it's no longer needed.

Remove the `chartIndicators` state variable and the separate Census race breakdown fetch.

- [ ] **Step 6: Run frontend build to verify**

Run: `cd /Users/william-meroxa/Development/d4bl_ai_agent/ui-nextjs && npm run build`
Expected: Build succeeds with no type errors

- [ ] **Step 7: Commit**

```bash
git add src/d4bl/app/api.py ui-nextjs/app/explore/page.tsx ui-nextjs/lib/explore-config.ts tests/test_census_unified.py
git commit -m "feat: unify Census ACS endpoint to return ExploreResponse shape"
```

---

### Task 1.3: API response caching for explore endpoints

**Files:**
- Create: `src/d4bl/app/cache.py`
- Modify: `src/d4bl/app/api.py` (wrap explore endpoints)
- Test: `tests/test_explore_cache.py`

- [ ] **Step 1: Write cache tests**

```python
# tests/test_explore_cache.py
"""Test TTL cache for explore endpoints."""
import pytest
import time
from unittest.mock import MagicMock, patch
from d4bl.app.cache import ExploreCache


def test_cache_returns_cached_value():
    cache = ExploreCache(ttl_seconds=300)
    cache.set("key1", {"data": "value"})
    assert cache.get("key1") == {"data": "value"}


def test_cache_returns_none_for_missing_key():
    cache = ExploreCache(ttl_seconds=300)
    assert cache.get("missing") is None


def test_cache_expires_after_ttl():
    cache = ExploreCache(ttl_seconds=1)
    cache.set("key1", {"data": "value"})
    time.sleep(1.1)
    assert cache.get("key1") is None


def test_cache_invalidates_on_newer_ingestion():
    cache = ExploreCache(ttl_seconds=300)
    cache.set("key1", {"data": "old"})
    # Simulate ingestion completing after cache was set
    cache.invalidate_if_stale(newer_than=time.time() + 1)
    assert cache.get("key1") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/william-meroxa/Development/d4bl_ai_agent && python -m pytest tests/test_explore_cache.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write the cache module**

```python
# src/d4bl/app/cache.py
"""In-memory TTL cache for explore API endpoints."""

import time
import logging
from cachetools import TTLCache

logger = logging.getLogger(__name__)

# Max 200 cache entries, 5 minute TTL
_DEFAULT_TTL = 300
_DEFAULT_MAXSIZE = 200


class ExploreCache:
    def __init__(self, ttl_seconds: int = _DEFAULT_TTL, maxsize: int = _DEFAULT_MAXSIZE):
        self._cache = TTLCache(maxsize=maxsize, ttl=ttl_seconds)
        self._created_at: dict[str, float] = {}

    def get(self, key: str):
        return self._cache.get(key)

    def set(self, key: str, value):
        self._cache[key] = value
        self._created_at[key] = time.time()

    def invalidate_if_stale(self, newer_than: float):
        """Clear entries created before `newer_than` timestamp."""
        stale_keys = [
            k for k, created in self._created_at.items()
            if created < newer_than
        ]
        for k in stale_keys:
            self._cache.pop(k, None)
            self._created_at.pop(k, None)
        if stale_keys:
            logger.info(f"Cache: invalidated {len(stale_keys)} stale entries")

    def clear(self):
        self._cache.clear()
        self._created_at.clear()


# Singleton instance
explore_cache = ExploreCache()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/william-meroxa/Development/d4bl_ai_agent && python -m pytest tests/test_explore_cache.py -v`
Expected: PASS

- [ ] **Step 5: Install cachetools dependency**

Run: `cd /Users/william-meroxa/Development/d4bl_ai_agent && pip install cachetools && pip freeze | grep cachetools >> requirements.txt`

- [ ] **Step 6: Wire cache into explore endpoints in api.py**

Add a helper function at the top of the explore endpoint section in `api.py`:

```python
from d4bl.app.cache import explore_cache
from d4bl.infra.database import IngestionRun

async def _check_cache_freshness(session):
    """Check if any ingestion completed after cache was populated."""
    result = await session.execute(
        select(func.max(IngestionRun.completed_at)).where(IngestionRun.status == "completed")
    )
    latest = result.scalar()
    if latest:
        explore_cache.invalidate_if_stale(newer_than=latest.timestamp())
```

Then in each explore endpoint, wrap the response:

```python
# At the start of each endpoint:
cache_key = f"{request.url.path}?{request.query_params}"
cached = explore_cache.get(cache_key)
if cached is not None:
    return cached

# ... existing query logic ...

# Before returning:
explore_cache.set(cache_key, response)
return response
```

- [ ] **Step 7: Run existing tests to verify no regressions**

Run: `cd /Users/william-meroxa/Development/d4bl_ai_agent && python -m pytest tests/ -v --timeout=30`
Expected: All tests pass

- [ ] **Step 8: Commit**

```bash
git add src/d4bl/app/cache.py src/d4bl/app/api.py tests/test_explore_cache.py requirements.txt
git commit -m "feat: add TTL cache for explore endpoints with ingestion-aware invalidation"
```

---

## Chunk 2: Frontend — Defaults, Legend, Color Scales

### Task 1.4: Smart defaults + localStorage persistence

**Files:**
- Modify: `ui-nextjs/app/explore/page.tsx:25-39`
- Test: Manual browser testing (localStorage is a browser API)

- [ ] **Step 1: Add localStorage persistence hooks to page.tsx**

Add constants and helper functions at the top of the explore page component:

```typescript
const STORAGE_KEY = "d4bl-explore-filters";

interface PersistedFilters {
  sourceKey: string;
  metric: string | null;
  race: string | null;
  year: number | null;
  selectedState: string | null;  // FIPS code, matches filters.selectedState
}

function loadPersistedFilters(): PersistedFilters | null {
  if (typeof window === "undefined") return null;
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    return stored ? JSON.parse(stored) : null;
  } catch {
    return null;
  }
}

function persistFilters(source: DataSourceConfig, filters: ExploreFilters) {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({
      sourceKey: source.key,
      metric: filters.metric,
      race: filters.race,
      year: filters.year,
      selectedState: filters.selectedState,
    }));
  } catch {
    // localStorage full or unavailable — ignore
  }
}
```

- [ ] **Step 2: Initialize state from localStorage or defaults**

Replace the initial state setup (lines 25-39) with:

```typescript
const [initialized, setInitialized] = useState(false);

// Default: Census ACS, Median Household Income
const defaultSource = DATA_SOURCES.find((s) => s.key === "census") ?? DATA_SOURCES[0];
const persisted = loadPersistedFilters();
const initialSource = persisted
  ? DATA_SOURCES.find((s) => s.key === persisted.sourceKey) ?? defaultSource
  : defaultSource;

const [activeSource, setActiveSource] = useState<DataSourceConfig>(initialSource);
const [filters, setFilters] = useState<ExploreFilters>({
  metric: persisted?.metric ?? "median_household_income",
  race: persisted?.race ?? null,
  year: persisted?.year ?? null,
  selectedState: persisted?.selectedState ?? null,
});
```

- [ ] **Step 3: Persist on filter/source changes**

Add a `useEffect` that persists whenever filters, source, or state selection changes:

```typescript
useEffect(() => {
  if (!initialized) return;
  persistFilters(activeSource, filters);
}, [activeSource, filters, initialized]);

// Set initialized after first data load
useEffect(() => {
  if (exploreData && !initialized) {
    setInitialized(true);
  }
}, [exploreData, initialized]);
```

- [ ] **Step 4: Run frontend build**

Run: `cd /Users/william-meroxa/Development/d4bl_ai_agent/ui-nextjs && npm run build`
Expected: Build succeeds

- [ ] **Step 5: Commit**

```bash
git add ui-nextjs/app/explore/page.tsx
git commit -m "feat: add localStorage persistence for explore page filters with Census ACS default"
```

---

### Task 1.5: Map legend with gradient bar and metric label

**Files:**
- Create: `ui-nextjs/components/explore/MapLegend.tsx`
- Modify: `ui-nextjs/app/explore/page.tsx` (add MapLegend below StateMap)

- [ ] **Step 1: Create MapLegend component**

```tsx
// ui-nextjs/components/explore/MapLegend.tsx
"use client";

interface MapLegendProps {
  min: number;
  max: number;
  nationalAverage: number | null;
  metric: string;
  colorStart: string;   // e.g., "#444"
  colorEnd: string;     // e.g., "#00ff32" or "#ff6b6b"
  accent: string;
}

function humanizeMetric(metric: string): string {
  return metric
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function formatValue(value: number): string {
  if (Math.abs(value) >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (Math.abs(value) >= 1_000) return `${(value / 1_000).toFixed(1)}K`;
  if (Number.isInteger(value)) return value.toString();
  return value.toFixed(1);
}

export default function MapLegend({
  min,
  max,
  nationalAverage,
  metric,
  colorStart,
  colorEnd,
  accent,
}: MapLegendProps) {
  const avgPosition =
    nationalAverage != null && max !== min
      ? ((nationalAverage - min) / (max - min)) * 100
      : null;

  return (
    <div className="mt-3 px-2">
      {/* Metric label */}
      <div className="text-xs mb-1.5" style={{ color: "#999" }}>
        Colored by:{" "}
        <span style={{ color: accent, fontWeight: 600 }}>
          {humanizeMetric(metric)}
        </span>
      </div>

      {/* Gradient bar */}
      <div className="relative h-3 rounded-sm overflow-hidden">
        <div
          className="absolute inset-0 rounded-sm"
          style={{
            background: `linear-gradient(to right, ${colorStart}, ${colorEnd})`,
          }}
        />
        {/* National average marker */}
        {avgPosition != null && (
          <div
            className="absolute top-0 h-full w-0.5"
            style={{
              left: `${avgPosition}%`,
              backgroundColor: "#fff",
              opacity: 0.8,
            }}
          />
        )}
      </div>

      {/* Labels */}
      <div className="relative flex justify-between mt-1 text-[10px]" style={{ color: "#777" }}>
        <span>{formatValue(min)}</span>
        {avgPosition != null && nationalAverage != null && (
          <span
            className="absolute"
            style={{
              left: `${avgPosition}%`,
              transform: "translateX(-50%)",
              color: "#ccc",
            }}
          >
            Avg: {formatValue(nationalAverage)}
          </span>
        )}
        <span>{formatValue(max)}</span>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Add MapLegend to the explore page**

In `ui-nextjs/app/explore/page.tsx`, import and render MapLegend directly below the StateMap component. Compute min/max from the current data:

```tsx
import MapLegend from "@/components/explore/MapLegend";

// Inside the render, after <StateMap>:
{exploreData && filters.metric && (() => {
  const values = exploreData.rows
    .filter((r) => r.metric === filters.metric)
    .map((r) => r.value)
    .filter((v) => v != null);
  if (values.length === 0) return null;
  const min = Math.min(...values);
  const max = Math.max(...values);
  return (
    <MapLegend
      min={min}
      max={max}
      nationalAverage={exploreData.national_average}
      metric={filters.metric}
      colorStart="#444"
      colorEnd={activeSource.accent}
      accent={activeSource.accent}
    />
  );
})()}
```

- [ ] **Step 3: Run frontend build**

Run: `cd /Users/william-meroxa/Development/d4bl_ai_agent/ui-nextjs && npm run build`
Expected: Build succeeds

- [ ] **Step 4: Commit**

```bash
git add ui-nextjs/components/explore/MapLegend.tsx ui-nextjs/app/explore/page.tsx
git commit -m "feat: add map legend with gradient bar, metric label, and national average marker"
```

---

### Task 1.6: Directional color scales per metric

**Files:**
- Modify: `ui-nextjs/lib/explore-config.ts:41-199` (add highIsGood per source)
- Modify: `ui-nextjs/components/explore/StateMap.tsx:29-54` (use directional color)
- Modify: `ui-nextjs/components/explore/MapLegend.tsx` (pass directional colors)
- Modify: `ui-nextjs/app/explore/page.tsx` (compute colorEnd from config)

- [ ] **Step 1: Install d3-scale-chromatic**

Note: `d3-interpolate` is already installed (used by StateMap.tsx). Verify with `npm ls d3-interpolate`. If missing: `npm install d3-interpolate @types/d3-interpolate`

- [ ] **Step 2: Add highIsGood config to explore-config.ts**

Add a `METRIC_DIRECTION` map to `explore-config.ts` that classifies each source's metrics. Also add a helper function:

```typescript
// Metric direction: true = high is good, false = high is bad, null = neutral
export const METRIC_DIRECTION: Record<string, Record<string, boolean | null>> = {
  census: {
    homeownership_rate: true,
    median_household_income: true,
    poverty_rate: false,
    unemployment_rate: false,
  },
  cdc: { default: false }, // Most CDC measures: higher prevalence = worse
  epa: { default: false }, // Higher environmental burden = worse
  fbi: { default: false }, // Higher crime = worse
  bls: {
    unemployment_rate: false,
    labor_force_participation: true,
    default: false,
  },
  hud: { default: false }, // Higher segregation = worse
  usda: { default: false }, // Higher food insecurity = worse
  doe: {
    suspension_rate: false,
    expulsion_rate: false,
    enrollment_rate: null,
    default: false,
  },
  police: { default: false },
  "census-demographics": { default: null },
  "cdc-mortality": { default: false },
  bjs: { default: false },
};

export function getMetricDirection(sourceKey: string, metric: string): boolean | null {
  const sourceDir = METRIC_DIRECTION[sourceKey];
  if (!sourceDir) return null;
  return sourceDir[metric] ?? sourceDir["default"] ?? null;
}

export function getDirectionalColors(
  sourceKey: string,
  metric: string,
  accent: string,
): { colorStart: string; colorEnd: string } {
  const direction = getMetricDirection(sourceKey, metric);
  if (direction === true) return { colorStart: "#444", colorEnd: "#22c55e" };  // green
  if (direction === false) return { colorStart: "#444", colorEnd: "#ef4444" }; // red
  return { colorStart: "#444", colorEnd: accent }; // neutral: source accent
}
```

- [ ] **Step 3: Update StateMap to use directional colors**

Modify `StateMap.tsx` (lines 29-54) to accept `colorStart` and `colorEnd` props instead of using the accent-only gradient:

```tsx
// Updated props
interface StateMapProps {
  indicators: IndicatorRow[];
  selectedStateFips: string | null;
  onSelectState: (fips: string, name: string) => void;
  accent?: string;
  nationalAverage?: number | null;
  colorStart?: string;
  colorEnd?: string;
}

// Updated color scale (replace lines 43-51)
const colorScale = (value: number) => {
  const start = colorStart || "#444";
  const end = colorEnd || accent;
  if (min === max) return end;
  const t = (value - min) / (max - min);
  return interpolateRgb(start, end)(t);
};
```

- [ ] **Step 4: Wire directional colors from explore page**

In `ui-nextjs/app/explore/page.tsx`, compute and pass directional colors:

```tsx
import { getDirectionalColors } from "@/lib/explore-config";

// In render, compute colors:
const dirColors = filters.metric
  ? getDirectionalColors(activeSource.key, filters.metric, activeSource.accent)
  : { colorStart: "#444", colorEnd: activeSource.accent };

// Pass to StateMap:
<StateMap
  indicators={mapIndicators}
  selectedStateFips={selectedStateFips}
  onSelectState={handleSelectState}
  accent={activeSource.accent}
  nationalAverage={exploreData?.national_average}
  colorStart={dirColors.colorStart}
  colorEnd={dirColors.colorEnd}
/>

// Pass to MapLegend:
<MapLegend
  min={min}
  max={max}
  nationalAverage={exploreData.national_average}
  metric={filters.metric}
  colorStart={dirColors.colorStart}
  colorEnd={dirColors.colorEnd}
  accent={activeSource.accent}
/>
```

- [ ] **Step 5: Run frontend build + lint**

Run: `cd /Users/william-meroxa/Development/d4bl_ai_agent/ui-nextjs && npm run build && npm run lint`
Expected: Build and lint succeed

- [ ] **Step 6: Commit**

```bash
git add ui-nextjs/lib/explore-config.ts ui-nextjs/components/explore/StateMap.tsx ui-nextjs/components/explore/MapLegend.tsx ui-nextjs/app/explore/page.tsx ui-nextjs/package.json ui-nextjs/package-lock.json
git commit -m "feat: add directional color scales (green=good, red=bad) with per-metric classification"
```

---

## Post-Epic Verification

- [ ] **Run full test suite**

```bash
cd /Users/william-meroxa/Development/d4bl_ai_agent && python -m pytest tests/ -v
cd ui-nextjs && npm run build && npm run lint
```

- [ ] **Manual smoke test**
1. Open explore page — should default to Census ACS / Median Household Income
2. Map should show green gradient (high income = good) with legend bar
3. Switch to CDC — map should show red gradient (high disease = bad) with legend
4. Select a state, change filters, reload — filters should persist
5. Switch to EPA or USDA — should load faster than before (pre-aggregated)
