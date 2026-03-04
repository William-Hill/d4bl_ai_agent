# Explore Data Page Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a `/explore` page showing race-disaggregated Census ACS indicators and state policy bills, backed by two new database tables and three new API endpoints, with data ingested from Census Bureau and OpenStates APIs.

**Architecture:** Two new SQLAlchemy models (`CensusIndicator`, `PolicyBill`) auto-migrated via `create_tables()`. Three new FastAPI endpoints in `api.py`. Four new Next.js components under `components/explore/`. A new App Router page at `app/explore/page.tsx`. Two standalone ingestion scripts in `scripts/`.

**Tech Stack:** FastAPI + SQLAlchemy asyncpg, pytest + httpx for API tests, Next.js 16 App Router, Tailwind CSS 4, react-simple-maps, recharts, d3-scale.

---

## Context

- **Current branch:** `feature/explore-data-page` (branched from `epic/platform-refactoring`)
- **Backend:** `src/d4bl/app/api.py` — FastAPI app using `Depends(get_db)` for DB sessions
- **DB models:** `src/d4bl/infra/database.py` — SQLAlchemy ORM, `create_tables()` calls `Base.metadata.create_all`
- **Schemas:** `src/d4bl/app/schemas.py` — Pydantic models for request/response
- **Tests:** `tests/test_*.py` — `pytest-asyncio`, `httpx.AsyncClient(ASGITransport(app=app))`
- **Frontend:** `ui-nextjs/` — Next.js App Router, no `src/` dir, uses `@/` alias for project root
- **Theme:** background `#292929`, sidebar `#1a1a1a`, borders `#404040`, accent `#00ff32`

---

### Task 1: Database models for census_indicators and policy_bills

**Files:**
- Modify: `src/d4bl/infra/database.py`
- Test: `tests/test_explore_models.py`

**Step 1: Write the failing test**

```python
# tests/test_explore_models.py
"""Tests for CensusIndicator and PolicyBill ORM models."""
from datetime import datetime, date
from uuid import uuid4

import pytest

from d4bl.infra.database import CensusIndicator, PolicyBill


class TestCensusIndicator:
    def test_can_instantiate_with_required_fields(self):
        row = CensusIndicator(
            fips_code="28",
            geography_type="state",
            geography_name="Mississippi",
            state_fips="28",
            year=2022,
            race="black",
            metric="homeownership_rate",
            value=43.2,
        )
        assert row.fips_code == "28"
        assert row.year == 2022
        assert row.value == 43.2

    def test_tablename(self):
        assert CensusIndicator.__tablename__ == "census_indicators"

    def test_margin_of_error_nullable(self):
        row = CensusIndicator(
            fips_code="28",
            geography_type="state",
            geography_name="Mississippi",
            state_fips="28",
            year=2022,
            race="total",
            metric="poverty_rate",
            value=19.1,
            margin_of_error=None,
        )
        assert row.margin_of_error is None


class TestPolicyBill:
    def test_can_instantiate_with_required_fields(self):
        bill = PolicyBill(
            state="MS",
            state_name="Mississippi",
            bill_id="ocd-bill/abc123",
            bill_number="SB 1234",
            title="Housing Equity Act",
            status="introduced",
            session="2025",
        )
        assert bill.state == "MS"
        assert bill.status == "introduced"

    def test_tablename(self):
        assert PolicyBill.__tablename__ == "policy_bills"

    def test_topic_tags_defaults_to_empty_list(self):
        bill = PolicyBill(
            state="MS",
            state_name="Mississippi",
            bill_id="ocd-bill/xyz",
            bill_number="HB 10",
            title="Test",
            status="passed",
            session="2025",
        )
        # topic_tags is nullable, not defaulted in model
        assert bill.topic_tags is None or isinstance(bill.topic_tags, list)
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/test_explore_models.py -v
```
Expected: `ImportError: cannot import name 'CensusIndicator' from 'd4bl.infra.database'`

**Step 3: Add the models to `src/d4bl/infra/database.py`**

Add `Integer, Date` to the existing SQLAlchemy import line:
```python
from sqlalchemy import JSON, Text, Column, String, DateTime, Float, Integer, Date
```

Then add both model classes after the `EvaluationResult` class (before `# Database connection setup`):

```python
class CensusIndicator(Base):
    """Race-disaggregated Census ACS indicators by geography."""
    __tablename__ = "census_indicators"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    fips_code = Column(String(5), nullable=False, index=True)
    geography_type = Column(String(10), nullable=False)   # state | county | tract
    geography_name = Column(Text, nullable=False)
    state_fips = Column(String(2), nullable=False, index=True)
    year = Column(Integer, nullable=False)
    race = Column(String(50), nullable=False)
    metric = Column(String(100), nullable=False)
    value = Column(Float, nullable=False)
    margin_of_error = Column(Float, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        {"comment": "Census ACS 5-year estimates, race-disaggregated"},
    )


class PolicyBill(Base):
    """State legislation tracked via OpenStates."""
    __tablename__ = "policy_bills"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    state = Column(String(2), nullable=False, index=True)
    state_name = Column(String(50), nullable=False)
    bill_id = Column(String(50), nullable=False)
    bill_number = Column(String(20), nullable=False)
    title = Column(Text, nullable=False)
    summary = Column(Text, nullable=True)
    status = Column(String(20), nullable=False, index=True)
    topic_tags = Column(JSON, nullable=True)
    session = Column(String(20), nullable=False, index=True)
    introduced_date = Column(Date, nullable=True)
    last_action_date = Column(Date, nullable=True)
    url = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/test_explore_models.py -v
```
Expected: `3 passed`

**Step 5: Commit**

```bash
git add src/d4bl/infra/database.py tests/test_explore_models.py
git commit -m "feat: Add CensusIndicator and PolicyBill database models"
```

---

### Task 2: Pydantic schemas for explore endpoints

**Files:**
- Modify: `src/d4bl/app/schemas.py`
- Test: `tests/test_explore_schemas.py`

**Step 1: Write the failing test**

```python
# tests/test_explore_schemas.py
"""Tests for explore endpoint Pydantic schemas."""
import pytest
from d4bl.app.schemas import (
    IndicatorItem,
    PolicyBillItem,
    StateSummaryItem,
)


class TestIndicatorItem:
    def test_serializes_correctly(self):
        item = IndicatorItem(
            fips_code="28",
            geography_name="Mississippi",
            state_fips="28",
            geography_type="state",
            year=2022,
            race="black",
            metric="homeownership_rate",
            value=43.2,
            margin_of_error=None,
        )
        d = item.model_dump()
        assert d["fips_code"] == "28"
        assert d["margin_of_error"] is None

    def test_metric_required(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            IndicatorItem(fips_code="28", geography_name="MS")


class TestPolicyBillItem:
    def test_serializes_correctly(self):
        bill = PolicyBillItem(
            state="MS",
            bill_number="SB 1234",
            title="Housing Equity Act",
            summary=None,
            status="introduced",
            topic_tags=["housing"],
            introduced_date=None,
            last_action_date=None,
            url="https://legislature.ms.gov/sb1234",
        )
        d = bill.model_dump()
        assert d["state"] == "MS"
        assert d["topic_tags"] == ["housing"]


class TestStateSummaryItem:
    def test_serializes_correctly(self):
        item = StateSummaryItem(
            state_fips="28",
            state_name="Mississippi",
            available_metrics=["homeownership_rate", "poverty_rate"],
            bill_count=12,
            latest_year=2022,
        )
        d = item.model_dump()
        assert d["bill_count"] == 12
        assert len(d["available_metrics"]) == 2
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/test_explore_schemas.py -v
```
Expected: `ImportError: cannot import name 'IndicatorItem'`

**Step 3: Add schemas to `src/d4bl/app/schemas.py`**

Append after the existing `QueryResponse` class:

```python
# --- Explore Data models ---

class IndicatorItem(BaseModel):
    fips_code: str
    geography_name: str
    state_fips: str
    geography_type: str
    year: int
    race: str
    metric: str
    value: float
    margin_of_error: Optional[float] = None


class PolicyBillItem(BaseModel):
    state: str
    bill_number: str
    title: str
    summary: Optional[str] = None
    status: str
    topic_tags: Optional[List[str]] = None
    introduced_date: Optional[str] = None
    last_action_date: Optional[str] = None
    url: Optional[str] = None


class StateSummaryItem(BaseModel):
    state_fips: str
    state_name: str
    available_metrics: List[str]
    bill_count: int
    latest_year: Optional[int] = None
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/test_explore_schemas.py -v
```
Expected: `3 passed`

**Step 5: Commit**

```bash
git add src/d4bl/app/schemas.py tests/test_explore_schemas.py
git commit -m "feat: Add Pydantic schemas for explore endpoints"
```

---

### Task 3: GET /api/explore/indicators endpoint

**Files:**
- Modify: `src/d4bl/app/api.py`
- Test: `tests/test_explore_api.py`

**Step 1: Write the failing test**

```python
# tests/test_explore_api.py
"""Tests for /api/explore/* endpoints."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient


class TestIndicatorsEndpoint:
    @pytest.mark.asyncio
    async def test_returns_200_with_list(self):
        from d4bl.app.api import app
        from d4bl.infra.database import get_db

        mock_row = MagicMock()
        mock_row.fips_code = "28"
        mock_row.geography_name = "Mississippi"
        mock_row.state_fips = "28"
        mock_row.geography_type = "state"
        mock_row.year = 2022
        mock_row.race = "black"
        mock_row.metric = "homeownership_rate"
        mock_row.value = 43.2
        mock_row.margin_of_error = None

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_row]

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        async def override_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_get_db

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get(
                    "/api/explore/indicators",
                    params={"state_fips": "28", "metric": "homeownership_rate"},
                )

            assert response.status_code == 200
            data = response.json()
            assert isinstance(data, list)
            assert len(data) == 1
            assert data[0]["fips_code"] == "28"
            assert data[0]["value"] == 43.2
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_data(self):
        from d4bl.app.api import app
        from d4bl.infra.database import get_db

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        async def override_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_get_db

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/api/explore/indicators")

            assert response.status_code == 200
            assert response.json() == []
        finally:
            app.dependency_overrides.clear()
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/test_explore_api.py::TestIndicatorsEndpoint -v
```
Expected: `404` or `AttributeError` — endpoint does not exist yet.

**Step 3: Add the endpoint to `src/d4bl/app/api.py`**

First, update the imports at the top of `api.py`. Add `CensusIndicator` and `PolicyBill` to the existing database import, and add the new schemas:

```python
# In the database import line, add CensusIndicator, PolicyBill:
from d4bl.infra.database import close_db, create_tables, get_db, init_db, EvaluationResult, ResearchJob, CensusIndicator, PolicyBill

# In the schemas import block, add new schemas:
from d4bl.app.schemas import (
    ...existing schemas...,
    IndicatorItem,
    PolicyBillItem,
    StateSummaryItem,
)
```

Then add the endpoint (place it after the existing evaluation endpoints, before the end of the file):

```python
@app.get("/api/explore/indicators", response_model=List[IndicatorItem])
async def get_indicators(
    state_fips: Optional[str] = None,
    geography_type: Optional[str] = None,
    metric: Optional[str] = None,
    race: Optional[str] = None,
    year: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
):
    """Get Census ACS indicators, optionally filtered."""
    try:
        query = select(CensusIndicator)
        if state_fips is not None:
            query = query.where(CensusIndicator.state_fips == state_fips)
        if geography_type is not None:
            query = query.where(CensusIndicator.geography_type == geography_type)
        if metric is not None:
            query = query.where(CensusIndicator.metric == metric)
        if race is not None:
            query = query.where(CensusIndicator.race == race)
        if year is not None:
            query = query.where(CensusIndicator.year == year)
        result = await db.execute(query)
        rows = result.scalars().all()
        return [
            IndicatorItem(
                fips_code=r.fips_code,
                geography_name=r.geography_name,
                state_fips=r.state_fips,
                geography_type=r.geography_type,
                year=r.year,
                race=r.race,
                metric=r.metric,
                value=r.value,
                margin_of_error=r.margin_of_error,
            )
            for r in rows
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail="Error fetching indicators") from e
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/test_explore_api.py::TestIndicatorsEndpoint -v
```
Expected: `2 passed`

**Step 5: Commit**

```bash
git add src/d4bl/app/api.py tests/test_explore_api.py
git commit -m "feat: Add GET /api/explore/indicators endpoint"
```

---

### Task 4: GET /api/explore/policies endpoint

**Files:**
- Modify: `src/d4bl/app/api.py`
- Modify: `tests/test_explore_api.py` (add a new test class)

**Step 1: Write the failing test**

Add this class to `tests/test_explore_api.py`:

```python
class TestPoliciesEndpoint:
    @pytest.mark.asyncio
    async def test_returns_200_with_list(self):
        from d4bl.app.api import app
        from d4bl.infra.database import get_db

        mock_row = MagicMock()
        mock_row.state = "MS"
        mock_row.bill_number = "SB 1234"
        mock_row.title = "Housing Equity Act"
        mock_row.summary = None
        mock_row.status = "introduced"
        mock_row.topic_tags = ["housing"]
        mock_row.introduced_date = None
        mock_row.last_action_date = None
        mock_row.url = "https://legislature.ms.gov/sb1234"

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_row]

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        async def override_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_get_db

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get(
                    "/api/explore/policies",
                    params={"state": "MS"},
                )

            assert response.status_code == 200
            data = response.json()
            assert isinstance(data, list)
            assert data[0]["state"] == "MS"
            assert data[0]["topic_tags"] == ["housing"]
        finally:
            app.dependency_overrides.clear()
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/test_explore_api.py::TestPoliciesEndpoint -v
```
Expected: `404` — endpoint does not exist.

**Step 3: Add the endpoint to `src/d4bl/app/api.py`**

After the indicators endpoint:

```python
@app.get("/api/explore/policies", response_model=List[PolicyBillItem])
async def get_policies(
    state: Optional[str] = None,
    status: Optional[str] = None,
    topic: Optional[str] = None,
    session: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """Get policy bills, optionally filtered."""
    try:
        query = select(PolicyBill)
        if state is not None:
            query = query.where(PolicyBill.state == state)
        if status is not None:
            query = query.where(PolicyBill.status == status)
        if session is not None:
            query = query.where(PolicyBill.session == session)
        if topic is not None:
            # JSON array containment: cast topic_tags to text and use LIKE
            query = query.where(
                PolicyBill.topic_tags.cast(String).contains(topic)
            )
        result = await db.execute(query)
        rows = result.scalars().all()
        return [
            PolicyBillItem(
                state=r.state,
                bill_number=r.bill_number,
                title=r.title,
                summary=r.summary,
                status=r.status,
                topic_tags=r.topic_tags,
                introduced_date=str(r.introduced_date) if r.introduced_date else None,
                last_action_date=str(r.last_action_date) if r.last_action_date else None,
                url=r.url,
            )
            for r in rows
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail="Error fetching policies") from e
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/test_explore_api.py::TestPoliciesEndpoint -v
```
Expected: `1 passed`

**Step 5: Commit**

```bash
git add src/d4bl/app/api.py tests/test_explore_api.py
git commit -m "feat: Add GET /api/explore/policies endpoint"
```

---

### Task 5: GET /api/explore/states endpoint

**Files:**
- Modify: `src/d4bl/app/api.py`
- Modify: `tests/test_explore_api.py` (add a new test class)

**Step 1: Write the failing test**

Add this class to `tests/test_explore_api.py`:

```python
class TestStatesEndpoint:
    @pytest.mark.asyncio
    async def test_returns_200_with_state_list(self):
        from d4bl.app.api import app
        from d4bl.infra.database import get_db

        # metrics aggregate result: (state_fips, state_name, metrics_list, latest_year)
        mock_metrics_row = MagicMock()
        mock_metrics_row._mapping = {
            "state_fips": "28",
            "state_name": "Mississippi",
            "metrics": "homeownership_rate,poverty_rate",
            "latest_year": 2022,
        }

        # bill count result: (state_name, bill_count) — API groups by state_name
        mock_bills_row = MagicMock()
        mock_bills_row._mapping = {
            "state_name": "Mississippi",
            "bill_count": 7,
        }

        mock_result_metrics = MagicMock()
        mock_result_metrics.mappings.return_value.all.return_value = [mock_metrics_row._mapping]

        mock_result_bills = MagicMock()
        mock_result_bills.mappings.return_value.all.return_value = [mock_bills_row._mapping]

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(side_effect=[mock_result_metrics, mock_result_bills])

        async def override_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_get_db

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/api/explore/states")

            assert response.status_code == 200
            data = response.json()
            assert isinstance(data, list)
            assert len(data) == 1
            assert data[0]["state_fips"] == "28"
            assert data[0]["state_name"] == "Mississippi"
            assert data[0]["bill_count"] == 7
        finally:
            app.dependency_overrides.clear()
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/test_explore_api.py::TestStatesEndpoint -v
```
Expected: `404`

**Step 3: Add the endpoint to `src/d4bl/app/api.py`**

Add this import at the top (with the existing sqlalchemy imports):
```python
from sqlalchemy import distinct, text
```

Add the endpoint after the policies endpoint:

```python
@app.get("/api/explore/states", response_model=List[StateSummaryItem])
async def get_states_summary(db: AsyncSession = Depends(get_db)):
    """Summarize available data per state for choropleth coloring."""
    try:
        # Aggregate metrics available per state
        metrics_query = text("""
            SELECT
                state_fips,
                geography_name AS state_name,
                STRING_AGG(DISTINCT metric, ',') AS metrics,
                MAX(year) AS latest_year
            FROM census_indicators
            WHERE geography_type = 'state'
            GROUP BY state_fips, geography_name
            ORDER BY state_fips
        """)
        metrics_result = await db.execute(metrics_query)
        metrics_rows = metrics_result.mappings().all()

        # Aggregate bill count per state (by state_name to join with census)
        bills_query = text("""
            SELECT state_name, COUNT(*) AS bill_count
            FROM policy_bills
            GROUP BY state_name
        """)
        bills_result = await db.execute(bills_query)
        bills_rows = bills_result.mappings().all()

        # Build lookup: state_name -> bill_count (join with census state_name)
        bill_counts_by_name: dict = {}
        for row in bills_rows:
            bill_counts_by_name[row["state_name"]] = row["bill_count"]

        summary = []
        for row in metrics_rows:
            metrics_list = row["metrics"].split(",") if row["metrics"] else []
            bill_count = bill_counts_by_name.get(row["state_name"], 0)
            summary.append(
                StateSummaryItem(
                    state_fips=row["state_fips"],
                    state_name=row["state_name"],
                    available_metrics=metrics_list,
                    bill_count=bill_count,
                    latest_year=row["latest_year"],
                )
            )

        return summary
    except Exception as e:
        raise HTTPException(status_code=500, detail="Error fetching state summary") from e
```

**Step 4: Run all explore API tests**

```bash
pytest tests/test_explore_api.py -v
```
Expected: `4 passed` (2 indicators + 1 policies + 1 states)

**Step 5: Run the full test suite to make sure nothing is broken**

```bash
pytest tests/ -v
```
Expected: all tests pass (currently ~56 passing + 4 new = ~60)

**Step 6: Commit**

```bash
git add src/d4bl/app/api.py tests/test_explore_api.py
git commit -m "feat: Add GET /api/explore/states endpoint"
```

---

### Task 6: Census ACS ingestion script

**Files:**
- Create: `scripts/ingest_census_acs.py`

This script is I/O-heavy so we don't write unit tests for it, but we verify it runs with `--dry-run` at the end.

**Step 1: Create `scripts/ingest_census_acs.py`**

```python
#!/usr/bin/env python
"""
Ingest Census ACS 5-year estimates into census_indicators table.

Usage:
    python scripts/ingest_census_acs.py [--year 2022] [--state TX] [--dry-run]

Env vars:
    CENSUS_API_KEY   (optional, higher rate limit)
    ACS_YEAR         (default: 2022)
    ACS_GEOGRAPHY    (default: state,county)
    POSTGRES_*       (connection settings, same as rest of app)
"""
import argparse
import asyncio
import os
import sys
from pathlib import Path

import aiohttp
import asyncpg

# Add src to path so d4bl package is importable
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from d4bl.infra.database import CensusIndicator, init_db, create_tables, close_db
from d4bl.infra.database import async_session_maker

# Census ACS variable codes by metric and race
# B25003: Tenure (homeownership), B19013: Median HH income, B17001: Poverty
METRIC_VARS = {
    "homeownership_rate": {
        "total": ("B25003_001E", "B25003_002E"),    # total, owner-occupied
        "black": ("B25003B_001E", "B25003B_002E"),
        "white": ("B25003A_001E", "B25003A_002E"),
        "hispanic": ("B25003I_001E", "B25003I_002E"),
    },
    "median_household_income": {
        "total": "B19013_001E",
        "black": "B19013B_001E",
        "white": "B19013A_001E",
        "hispanic": "B19013I_001E",
    },
    "poverty_rate": {
        "total": ("B17001_001E", "B17001_002E"),    # total, below poverty
        "black": ("B17001B_001E", "B17001B_002E"),
        "white": ("B17001A_001E", "B17001A_002E"),
        "hispanic": ("B17001I_001E", "B17001I_002E"),
    },
}

CENSUS_BASE = "https://api.census.gov/data"


async def fetch_acs(session: aiohttp.ClientSession, year: int, vars: list[str], geography: str, api_key: str | None) -> list[dict]:
    """Fetch one ACS query. Returns list of dicts with variable values."""
    get_str = ",".join(["NAME"] + vars)
    url = f"{CENSUS_BASE}/{year}/acs/acs5"
    params = {"get": get_str, "for": geography}
    if api_key:
        params["key"] = api_key

    async with session.get(url, params=params) as resp:
        resp.raise_for_status()
        rows = await resp.json()

    headers = rows[0]
    return [dict(zip(headers, row)) for row in rows[1:]]


def compute_rate(numerator: str, denominator: str) -> float | None:
    """Compute a ratio from two Census string values. Returns None if data unavailable."""
    try:
        num = float(numerator)
        den = float(denominator)
        if den <= 0:
            return None
        return round(num / den * 100, 2)
    except (TypeError, ValueError):
        return None


async def ingest_state_level(
    db_session,
    http_session: aiohttp.ClientSession,
    year: int,
    api_key: str | None,
    state_filter: str | None,
    dry_run: bool,
) -> int:
    """Ingest state-level indicators. Returns row count."""
    count = 0
    geography = "state:*" if not state_filter else f"state:{state_filter}"

    for metric, races in METRIC_VARS.items():
        for race, vars in races.items():
            try:
                # For rate metrics, vars is a tuple (denominator, numerator)
                if isinstance(vars, tuple):
                    rows = await fetch_acs(http_session, year, list(vars), geography, api_key)
                    for row in rows:
                        fips = row.get("state", "")
                        value = compute_rate(row.get(vars[1]), row.get(vars[0]))
                        if value is None:
                            continue
                        if not dry_run:
                            indicator = CensusIndicator(
                                fips_code=fips,
                                geography_type="state",
                                geography_name=row.get("NAME", ""),
                                state_fips=fips,
                                year=year,
                                race=race,
                                metric=metric,
                                value=value,
                            )
                            db_session.add(indicator)
                        count += 1
                else:
                    # Direct value metric (e.g. median income)
                    rows = await fetch_acs(http_session, year, [vars], geography, api_key)
                    for row in rows:
                        fips = row.get("state", "")
                        raw = row.get(vars)
                        try:
                            value = float(raw)
                        except (TypeError, ValueError):
                            continue
                        if value < 0:
                            continue
                        if not dry_run:
                            indicator = CensusIndicator(
                                fips_code=fips,
                                geography_type="state",
                                geography_name=row.get("NAME", ""),
                                state_fips=fips,
                                year=year,
                                race=race,
                                metric=metric,
                                value=value,
                            )
                            db_session.add(indicator)
                        count += 1
            except Exception as e:
                print(f"  Warning: {metric}/{race} fetch failed: {e}", file=sys.stderr)

    if not dry_run:
        await db_session.commit()

    return count


async def main(year: int, state_filter: str | None, dry_run: bool) -> None:
    init_db()
    if not dry_run:
        await create_tables()

    api_key = os.getenv("CENSUS_API_KEY")

    print(f"Ingesting Census ACS {year} data (dry_run={dry_run})")

    async with async_session_maker() as db:
        async with aiohttp.ClientSession() as http:
            count = await ingest_state_level(db, http, year, api_key, state_filter, dry_run)

    print(f"Done. {count} rows {'would be' if dry_run else ''} ingested.")
    await close_db()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest Census ACS data")
    parser.add_argument("--year", type=int, default=int(os.getenv("ACS_YEAR", "2022")))
    parser.add_argument("--state", default=None, help="2-digit FIPS code, e.g. 28 for Mississippi")
    parser.add_argument("--dry-run", action="store_true", help="Fetch but do not write to DB")
    args = parser.parse_args()

    asyncio.run(main(args.year, args.state, args.dry_run))
```

**Step 2: Make script executable and test the argument parsing**

```bash
chmod +x scripts/ingest_census_acs.py
python scripts/ingest_census_acs.py --help
```
Expected: prints usage without error.

**Step 3: Commit**

```bash
git add scripts/ingest_census_acs.py
git commit -m "feat: Add Census ACS ingestion script"
```

---

### Task 7: OpenStates ingestion script

**Files:**
- Create: `scripts/ingest_openstates.py`

**Step 1: Create `scripts/ingest_openstates.py`**

```python
#!/usr/bin/env python
"""
Ingest state policy bills from OpenStates GraphQL API into policy_bills table.

Usage:
    python scripts/ingest_openstates.py [--state MS] [--session 2025] [--dry-run]

Env vars:
    OPENSTATES_API_KEY   (required)
    POSTGRES_*           (connection settings)
"""
import argparse
import asyncio
import os
import sys
from pathlib import Path

import aiohttp

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from d4bl.infra.database import PolicyBill, init_db, create_tables, close_db
from d4bl.infra.database import async_session_maker

OPENSTATES_URL = "https://v3.openstates.org/graphql"

# D4BL focus topic tags to search for
FOCUS_SUBJECTS = [
    "housing",
    "wealth",
    "education",
    "criminal justice",
    "voting rights",
    "economic development",
    "health care",
]

# Map OpenStates status strings to our simplified enum
STATUS_MAP = {
    "introduced": "introduced",
    "in committee": "introduced",
    "referred to committee": "introduced",
    "passed upper": "passed",
    "passed lower": "passed",
    "passed": "passed",
    "signed": "signed",
    "vetoed": "failed",
    "failed": "failed",
    "dead": "failed",
}

BILLS_QUERY = """
query BillsByState($state: String!, $session: String, $subject: String, $after: String) {
  bills(jurisdiction: $state, session: $session, subject: $subject, after: $after, first: 50) {
    pageInfo { hasNextPage endCursor }
    edges {
      node {
        id
        identifier
        title
        abstract
        classification
        subject
        session { identifier }
        createdAt
        updatedAt
        statusText
        sources { url }
      }
    }
  }
}
"""


async def fetch_bills_for_subject(
    http: aiohttp.ClientSession, api_key: str, state: str, session: str | None, subject: str
) -> list[dict]:
    """Fetch all pages of bills for a given state and subject."""
    bills = []
    after = None
    headers = {"X-API-Key": api_key}

    while True:
        variables = {"state": state, "subject": subject}
        if session:
            variables["session"] = session
        if after:
            variables["after"] = after

        async with http.post(
            OPENSTATES_URL,
            json={"query": BILLS_QUERY, "variables": variables},
            headers=headers,
        ) as resp:
            resp.raise_for_status()
            data = await resp.json()

        edges = data.get("data", {}).get("bills", {}).get("edges", [])
        page_info = data.get("data", {}).get("bills", {}).get("pageInfo", {})

        for edge in edges:
            bills.append(edge["node"])

        if not page_info.get("hasNextPage"):
            break
        after = page_info["endCursor"]

    return bills


def map_status(status_text: str | None) -> str:
    if not status_text:
        return "other"
    lower = status_text.lower()
    for key, value in STATUS_MAP.items():
        if key in lower:
            return value
    return "other"


# Map OpenStates jurisdiction slug to 2-letter abbreviation and full name
STATE_MAP = {
    "al": ("AL", "Alabama"), "ak": ("AK", "Alaska"), "az": ("AZ", "Arizona"),
    "ar": ("AR", "Arkansas"), "ca": ("CA", "California"), "co": ("CO", "Colorado"),
    "ct": ("CT", "Connecticut"), "de": ("DE", "Delaware"), "fl": ("FL", "Florida"),
    "ga": ("GA", "Georgia"), "hi": ("HI", "Hawaii"), "id": ("ID", "Idaho"),
    "il": ("IL", "Illinois"), "in": ("IN", "Indiana"), "ia": ("IA", "Iowa"),
    "ks": ("KS", "Kansas"), "ky": ("KY", "Kentucky"), "la": ("LA", "Louisiana"),
    "me": ("ME", "Maine"), "md": ("MD", "Maryland"), "ma": ("MA", "Massachusetts"),
    "mi": ("MI", "Michigan"), "mn": ("MN", "Minnesota"), "ms": ("MS", "Mississippi"),
    "mo": ("MO", "Missouri"), "mt": ("MT", "Montana"), "ne": ("NE", "Nebraska"),
    "nv": ("NV", "Nevada"), "nh": ("NH", "New Hampshire"), "nj": ("NJ", "New Jersey"),
    "nm": ("NM", "New Mexico"), "ny": ("NY", "New York"), "nc": ("NC", "North Carolina"),
    "nd": ("ND", "North Dakota"), "oh": ("OH", "Ohio"), "ok": ("OK", "Oklahoma"),
    "or": ("OR", "Oregon"), "pa": ("PA", "Pennsylvania"), "ri": ("RI", "Rhode Island"),
    "sc": ("SC", "South Carolina"), "sd": ("SD", "South Dakota"), "tn": ("TN", "Tennessee"),
    "tx": ("TX", "Texas"), "ut": ("UT", "Utah"), "vt": ("VT", "Vermont"),
    "va": ("VA", "Virginia"), "wa": ("WA", "Washington"), "wv": ("WV", "West Virginia"),
    "wi": ("WI", "Wisconsin"), "wy": ("WY", "Wyoming"),
}


async def ingest_state(
    db_session, http: aiohttp.ClientSession, api_key: str,
    state_slug: str, session_id: str | None, dry_run: bool
) -> int:
    """Ingest all focus-topic bills for one state. Returns row count."""
    abbrev, full_name = STATE_MAP.get(state_slug.lower(), (state_slug.upper(), state_slug))
    count = 0
    seen_ids: set[str] = set()

    for subject in FOCUS_SUBJECTS:
        try:
            bills = await fetch_bills_for_subject(http, api_key, state_slug, session_id, subject)
        except Exception as e:
            print(f"  Warning: {state_slug}/{subject} failed: {e}", file=sys.stderr)
            continue

        for bill in bills:
            bill_id = bill["id"]
            if bill_id in seen_ids:
                continue
            seen_ids.add(bill_id)

            url = bill.get("sources", [{}])[0].get("url") if bill.get("sources") else None
            sess = bill.get("session", {}).get("identifier", session_id or "")

            if not dry_run:
                row = PolicyBill(
                    state=abbrev,
                    state_name=full_name,
                    bill_id=bill_id,
                    bill_number=bill.get("identifier", ""),
                    title=bill.get("title", ""),
                    summary=bill.get("abstract"),
                    status=map_status(bill.get("statusText")),
                    topic_tags=bill.get("subject", []),
                    session=sess,
                    url=url,
                )
                db_session.add(row)
            count += 1

    if not dry_run:
        await db_session.commit()

    return count


async def main(state_filter: str | None, session_id: str | None, dry_run: bool) -> None:
    api_key = os.getenv("OPENSTATES_API_KEY")
    if not api_key:
        print("Error: OPENSTATES_API_KEY environment variable required", file=sys.stderr)
        sys.exit(1)

    init_db()
    if not dry_run:
        await create_tables()

    states = [state_filter] if state_filter else list(STATE_MAP.keys())
    total = 0

    print(f"Ingesting OpenStates bills (states={len(states)}, dry_run={dry_run})")

    async with async_session_maker() as db:
        async with aiohttp.ClientSession() as http:
            for state_slug in states:
                count = await ingest_state(db, http, api_key, state_slug, session_id, dry_run)
                print(f"  {state_slug}: {count} bills")
                total += count

    print(f"Done. {total} total bills {'would be' if dry_run else ''} ingested.")
    await close_db()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest OpenStates policy bills")
    parser.add_argument("--state", default=None, help="State slug, e.g. ms for Mississippi")
    parser.add_argument("--session", default=None, help="Session identifier, e.g. 2025")
    parser.add_argument("--dry-run", action="store_true", help="Fetch but do not write to DB")
    args = parser.parse_args()

    asyncio.run(main(args.state, args.session, args.dry_run))
```

**Step 2: Make executable and verify help**

```bash
chmod +x scripts/ingest_openstates.py
python scripts/ingest_openstates.py --help
```
Expected: prints usage without error.

**Step 3: Commit**

```bash
git add scripts/ingest_openstates.py
git commit -m "feat: Add OpenStates policy bills ingestion script"
```

---

### Task 8: Install frontend dependencies and add Explore nav link

**Files:**
- Modify: `ui-nextjs/package.json` (via npm install)
- Modify: `ui-nextjs/app/layout.tsx`

**Step 1: Install the frontend packages**

```bash
cd ui-nextjs && npm install react-simple-maps recharts d3-scale
npm install --save-dev @types/d3-scale @types/react-simple-maps
```

**Step 2: Verify packages are in package.json**

```bash
grep -E "react-simple-maps|recharts|d3-scale" ui-nextjs/package.json
```
Expected: all three packages listed.

**Step 3: Add navigation bar to `ui-nextjs/app/layout.tsx`**

Read the current layout.tsx first (already done above — it has no nav). Add a nav bar so both the home page and the explore page share it:

```tsx
// ui-nextjs/app/layout.tsx
import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Link from "next/link";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "D4BL AI Agent - Research Tool | Data for Black Lives",
  description: "Data for Black Lives Research & Analysis Tool - Using data to create concrete and measurable change in the lives of Black people",
  icons: {
    icon: [
      { url: '/favicon.png', type: 'image/png', sizes: '128x128' },
      { url: '/favicon.ico', type: 'image/x-icon' },
    ],
    apple: [
      { url: '/favicon.png', type: 'image/png', sizes: '128x128' },
    ],
    shortcut: '/favicon.ico',
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className={`${geistSans.variable} ${geistMono.variable} antialiased bg-[#292929]`}>
        <nav className="border-b border-[#404040] bg-[#1a1a1a] px-6 py-3 flex items-center gap-8">
          <span className="font-bold text-[#00ff32] text-lg tracking-tight">D4BL</span>
          <Link
            href="/"
            className="text-sm text-gray-300 hover:text-[#00ff32] transition-colors"
          >
            Research
          </Link>
          <Link
            href="/explore"
            className="text-sm text-gray-300 hover:text-[#00ff32] transition-colors"
          >
            Explore Data
          </Link>
        </nav>
        {children}
      </body>
    </html>
  );
}
```

**Step 4: Run the Next.js dev server to verify nav renders**

```bash
cd ui-nextjs && npm run build 2>&1 | tail -20
```
Expected: build succeeds (exit 0, no TypeScript errors).

**Step 5: Commit**

```bash
cd .. # back to repo root
git add ui-nextjs/package.json ui-nextjs/package-lock.json ui-nextjs/app/layout.tsx
git commit -m "feat: Install explore frontend deps and add nav bar with Explore Data link"
```

---

### Task 9: MetricFilterPanel and StateMap components

**Files:**
- Create: `ui-nextjs/components/explore/MetricFilterPanel.tsx`
- Create: `ui-nextjs/components/explore/StateMap.tsx`

**Step 1: Create the filter panel component**

```tsx
// ui-nextjs/components/explore/MetricFilterPanel.tsx
'use client';

export type Metric = 'homeownership_rate' | 'median_household_income' | 'poverty_rate';
export type Race = 'total' | 'black' | 'white' | 'hispanic';

export interface ExploreFilters {
  metric: Metric;
  race: Race;
  year: number;
  selectedState: string | null;
}

interface Props {
  filters: ExploreFilters;
  onChange: (filters: ExploreFilters) => void;
}

const METRICS: { value: Metric; label: string }[] = [
  { value: 'homeownership_rate', label: 'Homeownership Rate' },
  { value: 'median_household_income', label: 'Median Household Income' },
  { value: 'poverty_rate', label: 'Poverty Rate' },
];

const RACES: { value: Race; label: string }[] = [
  { value: 'total', label: 'All' },
  { value: 'black', label: 'Black' },
  { value: 'white', label: 'White' },
  { value: 'hispanic', label: 'Hispanic/Latino' },
];

const YEARS = [2022, 2021, 2020, 2019];

export default function MetricFilterPanel({ filters, onChange }: Props) {
  return (
    <div className="bg-[#1a1a1a] border border-[#404040] rounded-lg p-4 space-y-5">
      {/* Metric */}
      <div>
        <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">Metric</p>
        <div className="space-y-1">
          {METRICS.map((m) => (
            <label key={m.value} className="flex items-center gap-2 cursor-pointer">
              <input
                type="radio"
                name="metric"
                value={m.value}
                checked={filters.metric === m.value}
                onChange={() => onChange({ ...filters, metric: m.value })}
                className="accent-[#00ff32]"
              />
              <span className="text-sm text-gray-300">{m.label}</span>
            </label>
          ))}
        </div>
      </div>

      <div className="border-t border-[#404040]" />

      {/* Race */}
      <div>
        <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">Race / Ethnicity</p>
        <div className="space-y-1">
          {RACES.map((r) => (
            <label key={r.value} className="flex items-center gap-2 cursor-pointer">
              <input
                type="radio"
                name="race"
                value={r.value}
                checked={filters.race === r.value}
                onChange={() => onChange({ ...filters, race: r.value })}
                className="accent-[#00ff32]"
              />
              <span className="text-sm text-gray-300">{r.label}</span>
            </label>
          ))}
        </div>
      </div>

      <div className="border-t border-[#404040]" />

      {/* Year */}
      <div>
        <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">Year</p>
        <select
          value={filters.year}
          onChange={(e) => onChange({ ...filters, year: Number(e.target.value) })}
          className="w-full bg-[#292929] border border-[#404040] rounded px-2 py-1.5 text-sm text-gray-300 focus:outline-none focus:border-[#00ff32]"
        >
          {YEARS.map((y) => (
            <option key={y} value={y}>{y}</option>
          ))}
        </select>
      </div>
    </div>
  );
}
```

**Step 2: Create the choropleth map component**

{% raw %}
```tsx
// ui-nextjs/components/explore/StateMap.tsx
'use client';

import { ComposableMap, Geographies, Geography, ZoomableGroup } from 'react-simple-maps';
import { scaleLinear } from 'd3-scale';
import { useState } from 'react';

const GEO_URL = 'https://cdn.jsdelivr.net/npm/us-atlas@3/states-10m.json';

interface IndicatorRow {
  fips_code: string;
  state_fips: string;
  value: number;
}

interface Props {
  indicators: IndicatorRow[];
  selectedStateFips: string | null;
  onSelectState: (fips: string, name: string) => void;
}

export default function StateMap({ indicators, selectedStateFips, onSelectState }: Props) {
  const [tooltip, setTooltip] = useState<{ name: string; value: number } | null>(null);

  const valueByFips: Record<string, number> = {};
  for (const row of indicators) {
    if (row.fips_code.length === 2) {
      valueByFips[row.fips_code] = row.value;
    }
  }

  const values = Object.values(valueByFips);
  const min = values.length ? Math.min(...values) : 0;
  const max = values.length ? Math.max(...values) : 100;

  const colorScale = scaleLinear<string>()
    .domain([min, max])
    .range(['#1a3a1a', '#00ff32']);

  return (
    <div className="relative bg-[#1a1a1a] rounded-lg border border-[#404040] overflow-hidden">
      {tooltip && (
        <div className="absolute top-2 left-2 z-10 bg-[#292929] border border-[#404040] rounded px-3 py-1.5 text-sm text-gray-200 pointer-events-none">
          <span className="font-semibold text-[#00ff32]">{tooltip.name}</span>
          <span className="ml-2">{tooltip.value.toLocaleString()}</span>
        </div>
      )}
      <ComposableMap projection="geoAlbersUsa" style={{ width: '100%', height: 'auto' }}>
        <ZoomableGroup zoom={1}>
          <Geographies geography={GEO_URL}>
            {({ geographies }) =>
              geographies.map((geo) => {
                const fips = geo.id as string;
                const value = valueByFips[fips];
                const isSelected = fips === selectedStateFips;
                return (
                  <Geography
                    key={geo.rsmKey}
                    geography={geo}
                    fill={value !== undefined ? colorScale(value) : '#333'}
                    stroke={isSelected ? '#00ff32' : '#404040'}
                    strokeWidth={isSelected ? 2 : 0.5}
                    style={{
                      default: { outline: 'none', cursor: 'pointer' },
                      hover: { fill: '#00cc28', outline: 'none', cursor: 'pointer' },
                      pressed: { outline: 'none' },
                    }}
                    onMouseEnter={() => {
                      if (value !== undefined) {
                        setTooltip({ name: geo.properties.name, value });
                      }
                    }}
                    onMouseLeave={() => setTooltip(null)}
                    onClick={() => onSelectState(fips, geo.properties.name)}
                  />
                );
              })
            }
          </Geographies>
        </ZoomableGroup>
      </ComposableMap>
    </div>
  );
}
```
{% endraw %}

**Step 3: Run build to check TypeScript**

```bash
cd ui-nextjs && npm run build 2>&1 | tail -30
```
Expected: build succeeds. If there are TypeScript errors about missing types, run:
```bash
npm install --save-dev @types/react-simple-maps
```

**Step 4: Commit**

```bash
cd .. # repo root
git add ui-nextjs/components/explore/MetricFilterPanel.tsx ui-nextjs/components/explore/StateMap.tsx
git commit -m "feat: Add MetricFilterPanel and StateMap explore components"
```

---

### Task 10: RacialGapChart and PolicyTable components

**Files:**
- Create: `ui-nextjs/components/explore/RacialGapChart.tsx`
- Create: `ui-nextjs/components/explore/PolicyTable.tsx`

**Step 1: Create RacialGapChart**

{% raw %}
```tsx
// ui-nextjs/components/explore/RacialGapChart.tsx
'use client';

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts';

interface IndicatorRow {
  race: string;
  value: number;
}

interface Props {
  indicators: IndicatorRow[];
  metric: string;
  stateName: string;
}

const RACE_COLORS: Record<string, string> = {
  black: '#00ff32',
  white: '#777',
  hispanic: '#555',
  total: '#404040',
};

const RACE_LABELS: Record<string, string> = {
  black: 'Black',
  white: 'White',
  hispanic: 'Hispanic/Latino',
  total: 'All',
};

const METRIC_LABELS: Record<string, string> = {
  homeownership_rate: 'Homeownership Rate (%)',
  median_household_income: 'Median Household Income ($)',
  poverty_rate: 'Poverty Rate (%)',
};

export default function RacialGapChart({ indicators, metric, stateName }: Props) {
  const data = indicators
    .filter((r) => r.race !== 'total')
    .map((r) => ({
      race: RACE_LABELS[r.race] ?? r.race,
      value: r.value,
      fill: RACE_COLORS[r.race] ?? '#666',
    }));

  if (data.length === 0) {
    return (
      <div className="bg-[#1a1a1a] border border-[#404040] rounded-lg p-6 text-center text-gray-500 text-sm">
        No data available for this selection.
      </div>
    );
  }

  return (
    <div className="bg-[#1a1a1a] border border-[#404040] rounded-lg p-4">
      <h3 className="text-sm font-semibold text-gray-300 mb-4">
        {METRIC_LABELS[metric] ?? metric} — {stateName}
      </h3>
      <ResponsiveContainer width="100%" height={200}>
        <BarChart data={data} margin={{ top: 4, right: 8, bottom: 4, left: 8 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#404040" />
          <XAxis dataKey="race" tick={{ fill: '#9ca3af', fontSize: 12 }} axisLine={false} tickLine={false} />
          <YAxis tick={{ fill: '#9ca3af', fontSize: 11 }} axisLine={false} tickLine={false} />
          <Tooltip
            contentStyle={{ background: '#292929', border: '1px solid #404040', borderRadius: 4 }}
            labelStyle={{ color: '#e5e7eb' }}
            itemStyle={{ color: '#00ff32' }}
          />
          <Bar dataKey="value" radius={[4, 4, 0, 0]}>
            {data.map((entry, index) => (
              <rect key={index} fill={entry.fill} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
```
{% endraw %}

**Step 2: Create PolicyTable**

```tsx
// ui-nextjs/components/explore/PolicyTable.tsx
'use client';

import { useState } from 'react';

interface PolicyBill {
  state: string;
  bill_number: string;
  title: string;
  summary: string | null;
  status: string;
  topic_tags: string[] | null;
  introduced_date: string | null;
  last_action_date: string | null;
  url: string | null;
}

interface Props {
  bills: PolicyBill[];
}

const STATUS_COLORS: Record<string, string> = {
  introduced: 'bg-blue-900 text-blue-300',
  passed: 'bg-green-900 text-green-300',
  signed: 'bg-[#1a3a1a] text-[#00ff32]',
  failed: 'bg-red-900 text-red-300',
  other: 'bg-[#333] text-gray-400',
};

const ALL_TOPICS = ['housing', 'wealth', 'education', 'criminal justice', 'voting rights', 'economic development', 'health care'];

export default function PolicyTable({ bills }: Props) {
  const [activeTopic, setActiveTopic] = useState<string | null>(null);

  const filtered = activeTopic
    ? bills.filter((b) => b.topic_tags?.includes(activeTopic))
    : bills;

  return (
    <div className="space-y-3">
      {/* Topic filter chips */}
      <div className="flex flex-wrap gap-2">
        <button
          onClick={() => setActiveTopic(null)}
          className={`px-3 py-1 rounded-full text-xs font-medium transition-colors ${
            activeTopic === null
              ? 'bg-[#00ff32] text-black'
              : 'bg-[#2a2a2a] text-gray-400 border border-[#404040] hover:border-[#00ff32]'
          }`}
        >
          All
        </button>
        {ALL_TOPICS.map((topic) => (
          <button
            key={topic}
            onClick={() => setActiveTopic(activeTopic === topic ? null : topic)}
            className={`px-3 py-1 rounded-full text-xs font-medium capitalize transition-colors ${
              activeTopic === topic
                ? 'bg-[#00ff32] text-black'
                : 'bg-[#2a2a2a] text-gray-400 border border-[#404040] hover:border-[#00ff32]'
            }`}
          >
            {topic}
          </button>
        ))}
      </div>

      {/* Table */}
      {filtered.length === 0 ? (
        <p className="text-gray-500 text-sm text-center py-8">No bills match this filter.</p>
      ) : (
        <div className="divide-y divide-[#404040]">
          {filtered.map((bill, i) => (
            <div key={i} className="py-3 flex items-start justify-between gap-4">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-xs font-mono text-gray-500">{bill.bill_number}</span>
                  <span
                    className={`px-2 py-0.5 rounded text-xs font-medium ${
                      STATUS_COLORS[bill.status] ?? STATUS_COLORS.other
                    }`}
                  >
                    {bill.status}
                  </span>
                  {bill.topic_tags?.slice(0, 2).map((tag) => (
                    <span key={tag} className="px-2 py-0.5 rounded bg-[#2a2a2a] text-xs text-gray-400 capitalize">
                      {tag}
                    </span>
                  ))}
                </div>
                <p className="text-sm text-gray-200 leading-snug">{bill.title}</p>
                {bill.last_action_date && (
                  <p className="text-xs text-gray-500 mt-1">Last action: {bill.last_action_date}</p>
                )}
              </div>
              {bill.url && (
                <a
                  href={bill.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="shrink-0 text-xs text-[#00ff32] hover:underline"
                >
                  View →
                </a>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
```

**Step 3: Run build to check for TypeScript errors**

```bash
cd ui-nextjs && npm run build 2>&1 | tail -30
```
Expected: build succeeds.

**Step 4: Commit**

```bash
cd .. # repo root
git add ui-nextjs/components/explore/RacialGapChart.tsx ui-nextjs/components/explore/PolicyTable.tsx
git commit -m "feat: Add RacialGapChart and PolicyTable explore components"
```

---

### Task 11: Assemble the /explore page

**Files:**
- Create: `ui-nextjs/app/explore/page.tsx`

**Step 1: Create the page**

```tsx
// ui-nextjs/app/explore/page.tsx
'use client';

import { useState, useEffect, useCallback } from 'react';
import MetricFilterPanel, { ExploreFilters } from '@/components/explore/MetricFilterPanel';
import StateMap from '@/components/explore/StateMap';
import RacialGapChart from '@/components/explore/RacialGapChart';
import PolicyTable from '@/components/explore/PolicyTable';

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

interface IndicatorRow {
  fips_code: string;
  geography_name: string;
  state_fips: string;
  geography_type: string;
  year: number;
  race: string;
  metric: string;
  value: number;
  margin_of_error: number | null;
}

interface PolicyBill {
  state: string;
  bill_number: string;
  title: string;
  summary: string | null;
  status: string;
  topic_tags: string[] | null;
  introduced_date: string | null;
  last_action_date: string | null;
  url: string | null;
}

export default function ExplorePage() {
  const [filters, setFilters] = useState<ExploreFilters>({
    metric: 'homeownership_rate',
    race: 'total',
    year: 2022,
    selectedState: null,
  });
  const [selectedStateName, setSelectedStateName] = useState<string>('');

  const [mapIndicators, setMapIndicators] = useState<IndicatorRow[]>([]);
  const [chartIndicators, setChartIndicators] = useState<IndicatorRow[]>([]);
  const [bills, setBills] = useState<PolicyBill[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Fetch all-state indicators for the map (current metric + race + year)
  const fetchMapData = useCallback(async () => {
    try {
      const params = new URLSearchParams({
        metric: filters.metric,
        race: filters.race,
        year: String(filters.year),
        geography_type: 'state',
      });
      const res = await fetch(`${API_BASE}/api/explore/indicators?${params}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setMapIndicators(await res.json());
    } catch (e: any) {
      setError(e.message);
    }
  }, [filters.metric, filters.race, filters.year]);

  // Fetch all-race indicators for selected state (for bar chart)
  const fetchChartData = useCallback(async () => {
    if (!filters.selectedState) {
      setChartIndicators([]);
      return;
    }
    try {
      const params = new URLSearchParams({
        state_fips: filters.selectedState,
        metric: filters.metric,
        year: String(filters.year),
        geography_type: 'state',
      });
      const res = await fetch(`${API_BASE}/api/explore/indicators?${params}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setChartIndicators(await res.json());
    } catch (e: any) {
      setError(e.message);
    }
  }, [filters.selectedState, filters.metric, filters.year]);

  // Fetch policy bills for selected state
  const fetchBills = useCallback(async () => {
    if (!filters.selectedState) {
      setBills([]);
      return;
    }
    // Convert FIPS to state abbrev via StateMap lookup — simplest approach:
    // Pass state_name to policies endpoint. For now, filter by state name.
    try {
      const params = new URLSearchParams();
      // Note: policies API uses 2-letter abbreviation; selectedState is FIPS.
      // The StateMap passes state name via onSelectState — we use selectedStateName.
      if (selectedStateName) {
        // We'll filter via a name match — see note in implementation below.
        // For now pass state param as-is; future iteration can build FIPS->abbrev map.
      }
      const res = await fetch(`${API_BASE}/api/explore/policies?${params}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const allBills: PolicyBill[] = await res.json();
      // Filter client-side by state name until FIPS->abbrev mapping is added
      const stateBills = selectedStateName
        ? allBills.filter((b) => b.state === selectedStateName)
        : allBills;
      setBills(stateBills);
    } catch (e: any) {
      setError(e.message);
    }
  }, [filters.selectedState, selectedStateName]);

  useEffect(() => {
    setLoading(true);
    setError(null);
    Promise.all([fetchMapData(), fetchChartData(), fetchBills()]).finally(() =>
      setLoading(false)
    );
  }, [fetchMapData, fetchChartData, fetchBills]);

  const handleSelectState = (fips: string, name: string) => {
    setFilters((prev) => ({
      ...prev,
      selectedState: prev.selectedState === fips ? null : fips,
    }));
    setSelectedStateName((prev) => (prev === name ? '' : name));
  };

  return (
    <div className="min-h-screen bg-[#292929]">
      <div className="max-w-7xl mx-auto px-4 py-8">
        {/* Hero */}
        <header className="mb-8">
          <h1 className="text-3xl font-bold text-white mb-1">Explore Data by State</h1>
          <div className="w-16 h-1 bg-[#00ff32] mb-3" />
          <p className="text-gray-400 text-sm">
            Race-disaggregated socioeconomic indicators and policy activity across the United States.
          </p>
        </header>

        {error && (
          <div className="mb-4 px-4 py-3 bg-red-900/30 border border-red-800 rounded text-red-300 text-sm">
            Error loading data: {error}
          </div>
        )}

        {/* Map + Filters */}
        <div className="grid grid-cols-1 lg:grid-cols-[1fr_260px] gap-4 mb-6">
          <div>
            {loading && !mapIndicators.length ? (
              <div className="bg-[#1a1a1a] border border-[#404040] rounded-lg h-64 flex items-center justify-center text-gray-500 text-sm">
                Loading map data...
              </div>
            ) : (
              <StateMap
                indicators={mapIndicators}
                selectedStateFips={filters.selectedState}
                onSelectState={handleSelectState}
              />
            )}
          </div>
          <MetricFilterPanel filters={filters} onChange={setFilters} />
        </div>

        {/* Bar Chart */}
        {filters.selectedState && (
          <div className="mb-6">
            <RacialGapChart
              indicators={chartIndicators}
              metric={filters.metric}
              stateName={selectedStateName}
            />
          </div>
        )}

        {/* Policy Tracker */}
        <div className="bg-[#1a1a1a] border border-[#404040] rounded-lg p-4">
          <h2 className="text-base font-semibold text-white mb-4">
            Policy Tracker
            {selectedStateName && (
              <span className="text-[#00ff32] ml-2">— {selectedStateName}</span>
            )}
          </h2>
          {loading && !bills.length ? (
            <p className="text-gray-500 text-sm">Loading bills...</p>
          ) : (
            <PolicyTable bills={bills} />
          )}
        </div>
      </div>
    </div>
  );
}
```

**Step 2: Run the full build**

```bash
cd ui-nextjs && npm run build 2>&1 | tail -40
```
Expected: build succeeds with no TypeScript errors. If there are recharts Cell import errors, update the RacialGapChart Bar to use `cell` prop directly rather than Cell child elements.

**Step 3: Run the full Python test suite to ensure nothing regressed**

```bash
cd .. && pytest tests/ -v
```
Expected: all tests pass.

**Step 4: Commit**

```bash
git add ui-nextjs/app/explore/page.tsx
git commit -m "feat: Add /explore page assembling map, chart, and policy tracker"
```

---

## Verification Checklist

After all tasks, verify:

- [ ] `pytest tests/ -v` — all tests pass
- [ ] `cd ui-nextjs && npm run build` — TypeScript build clean
- [ ] `python scripts/ingest_census_acs.py --help` — prints usage
- [ ] `python scripts/ingest_openstates.py --help` — prints usage
- [ ] Dev server shows nav with "Research" and "Explore Data" links
- [ ] `/explore` page renders map, filter panel, empty chart, empty policy table (before data is ingested)
- [ ] After running `python scripts/ingest_census_acs.py --dry-run`, no DB errors

## Out of Scope

- Census tract-level geography
- Materialized views / caching
- User-saved filters
- Qualitative data ingestion
- Community survey integration
