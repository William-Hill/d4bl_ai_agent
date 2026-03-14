# CDC WONDER Mortality Ingestion — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Ingest CDC mortality data from two SODA API datasets into a unified `cdc_mortality` table — state-level leading causes (`bi63-dtpu`) and national race-disaggregated excess deaths (`m74n-4hbs`).

**Architecture:** Two independent Dagster assets write to one table with `geography_type` distinguishing state vs national rows. Follows the CDC PLACES asset pattern (SODA API, async aiohttp, idempotent upserts, Langfuse tracing, lineage recording).

**Tech Stack:** Dagster, aiohttp, SQLAlchemy (async), PostgreSQL, Langfuse

**Design doc:** `docs/plans/2026-03-13-cdc-wonder-mortality-ingestion.md`

---

### Task 1: Add CdcMortality SQLAlchemy model

**Files:**
- Modify: `src/d4bl/infra/database.py:577` (after `PoliceViolenceIncident` class, before `get_database_url`)

**Step 1: Write the failing test**

Create `dagster/tests/test_cdc_mortality_asset.py`:

```python
# dagster/tests/test_cdc_mortality_asset.py
"""Tests for CDC mortality ingestion assets."""


def test_cdc_mortality_model_importable():
    """CdcMortality model should be importable from database module."""
    from d4bl.infra.database import CdcMortality

    assert CdcMortality.__tablename__ == "cdc_mortality"


def test_cdc_mortality_model_has_unique_constraint():
    """CdcMortality should have a unique constraint for idempotent upserts."""
    from d4bl.infra.database import CdcMortality

    constraint_names = [
        c.name for c in CdcMortality.__table_args__
        if hasattr(c, "name") and c.name and c.name.startswith("uq_")
    ]
    assert len(constraint_names) == 1
    assert "uq_cdc_mortality_key" in constraint_names
```

**Step 2: Run test to verify it fails**

Run: `cd dagster && python -m pytest tests/test_cdc_mortality_asset.py::test_cdc_mortality_model_importable -v`
Expected: FAIL with `ImportError: cannot import name 'CdcMortality'`

**Step 3: Write the model**

Add to `src/d4bl/infra/database.py` after the `PoliceViolenceIncident` class (before `# Database connection setup`):

```python
class CdcMortality(Base):
    """Mortality data from CDC WONDER / NCHS via SODA API."""
    __tablename__ = "cdc_mortality"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    geo_id = Column(String(20), nullable=False)
    geography_type = Column(String(10), nullable=False)
    state_fips = Column(String(2), nullable=True)
    state_name = Column(String(100), nullable=True)
    year = Column(Integer, nullable=False)
    cause_of_death = Column(String(200), nullable=False)
    race = Column(String(100), nullable=False, default="total")
    deaths = Column(Integer, nullable=True)
    age_adjusted_rate = Column(Float, nullable=True)
    created_at = Column(DateTime, nullable=False, default=_utc_now)

    __table_args__ = (
        UniqueConstraint(
            "geo_id", "year", "cause_of_death", "race",
            name="uq_cdc_mortality_key",
        ),
        Index("ix_cdc_mortality_state_year", "state_fips", "year", "cause_of_death", "race"),
        Index("ix_cdc_mortality_geo_type", "geography_type", "year"),
    )
```

**Step 4: Run tests to verify they pass**

Run: `cd dagster && python -m pytest tests/test_cdc_mortality_asset.py -v`
Expected: PASS (both tests)

**Step 5: Commit**

```bash
git add src/d4bl/infra/database.py dagster/tests/test_cdc_mortality_asset.py
git commit -m "feat: add CdcMortality database model (#91)"
```

---

### Task 2: Create state-level mortality asset with state FIPS mapping

**Files:**
- Create: `dagster/d4bl_pipelines/assets/apis/cdc_mortality.py`
- Test: `dagster/tests/test_cdc_mortality_asset.py`

**Step 1: Add asset import tests**

Append to `dagster/tests/test_cdc_mortality_asset.py`:

```python
def test_cdc_mortality_state_asset_exists():
    """The cdc_mortality_state asset should be importable."""
    from d4bl_pipelines.assets.apis.cdc_mortality import cdc_mortality_state

    assert cdc_mortality_state is not None


def test_cdc_mortality_state_asset_group():
    """Asset should belong to the 'apis' group."""
    from d4bl_pipelines.assets.apis.cdc_mortality import cdc_mortality_state

    spec = cdc_mortality_state.specs_by_key
    key = next(iter(spec))
    assert key.path[-1] == "cdc_mortality_state"
    assert spec[key].group_name == "apis"


def test_state_name_to_fips_mapping():
    """State name to FIPS mapping should cover all 50 states + DC."""
    from d4bl_pipelines.assets.apis.cdc_mortality import STATE_NAME_TO_FIPS

    assert len(STATE_NAME_TO_FIPS) >= 51
    assert STATE_NAME_TO_FIPS["Alabama"] == "01"
    assert STATE_NAME_TO_FIPS["District of Columbia"] == "11"
    assert STATE_NAME_TO_FIPS["Wyoming"] == "56"
```

**Step 2: Run tests to verify they fail**

Run: `cd dagster && python -m pytest tests/test_cdc_mortality_asset.py::test_cdc_mortality_state_asset_exists -v`
Expected: FAIL with `ModuleNotFoundError`

**Step 3: Create the asset file**

Create `dagster/d4bl_pipelines/assets/apis/cdc_mortality.py`:

```python
"""CDC mortality data ingestion assets.

Two assets write to a unified cdc_mortality table:
- cdc_mortality_state: state-level leading causes of death (SODA dataset bi63-dtpu)
- cdc_mortality_national_race: national race-disaggregated excess deaths (SODA dataset m74n-4hbs)
"""

import os
import uuid

import aiohttp

from d4bl_pipelines.utils import flush_langfuse
from dagster import (
    AssetExecutionContext,
    MaterializeResult,
    MetadataValue,
    asset,
)

# --- SODA API endpoints ---
CDC_STATE_MORTALITY_URL = "https://data.cdc.gov/resource/bi63-dtpu.json"
CDC_EXCESS_DEATHS_URL = "https://data.cdc.gov/resource/m74n-4hbs.json"

# --- State name → FIPS mapping (used by bi63-dtpu which returns state names) ---
STATE_NAME_TO_FIPS = {
    "Alabama": "01", "Alaska": "02", "Arizona": "04", "Arkansas": "05",
    "California": "06", "Colorado": "08", "Connecticut": "09", "Delaware": "10",
    "District of Columbia": "11", "Florida": "12", "Georgia": "13", "Hawaii": "15",
    "Idaho": "16", "Illinois": "17", "Indiana": "18", "Iowa": "19",
    "Kansas": "20", "Kentucky": "21", "Louisiana": "22", "Maine": "23",
    "Maryland": "24", "Massachusetts": "25", "Michigan": "26", "Minnesota": "27",
    "Mississippi": "28", "Missouri": "29", "Montana": "30", "Nebraska": "31",
    "Nevada": "32", "New Hampshire": "33", "New Jersey": "34", "New Mexico": "35",
    "New York": "36", "North Carolina": "37", "North Dakota": "38", "Ohio": "39",
    "Oklahoma": "40", "Oregon": "41", "Pennsylvania": "42", "Rhode Island": "44",
    "South Carolina": "45", "South Dakota": "46", "Tennessee": "47", "Texas": "48",
    "Utah": "49", "Vermont": "50", "Virginia": "51", "Washington": "53",
    "West Virginia": "54", "Wisconsin": "55", "Wyoming": "56",
}

# --- Race mapping for m74n-4hbs excess deaths dataset ---
RACE_MAP = {
    "Non-Hispanic White": "white",
    "Non-Hispanic Black": "black",
    "Hispanic": "hispanic",
    "Non-Hispanic Asian": "asian",
    "Non-Hispanic American Indian or Alaska Native": "native_american",
    "Other": "multiracial",
}


@asset(
    group_name="apis",
    description=(
        "State-level leading causes of death from NCHS (1999-2017). "
        "10 leading causes by state and year. No race disaggregation."
    ),
    metadata={
        "source": "NCHS Leading Causes of Death (SODA bi63-dtpu)",
        "methodology": "D4BL equity-focused mortality data collection",
    },
    required_resource_keys={"db_url", "langfuse"},
)
async def cdc_mortality_state(
    context: AssetExecutionContext,
) -> MaterializeResult:
    """Fetch state-level leading causes of death and upsert into cdc_mortality."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    db_url = context.resources.db_url

    # --- Langfuse tracing ---
    langfuse = context.resources.langfuse
    trace = None
    try:
        if langfuse:
            trace = langfuse.trace(
                name="dagster:cdc_mortality_state",
                metadata={"source": "bi63-dtpu"},
            )
    except Exception as exc:
        context.log.warning(f"Langfuse trace init failed: {exc}")
        langfuse = None

    engine = create_async_engine(db_url, pool_size=3, max_overflow=5)
    async_session = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    records_ingested = 0
    states_seen = set()
    causes_seen = set()
    years_seen = set()

    upsert_sql = text("""
        INSERT INTO cdc_mortality
            (id, geo_id, geography_type, state_fips, state_name,
             year, cause_of_death, race, deaths, age_adjusted_rate)
        VALUES
            (CAST(:id AS UUID), :geo_id, 'state', :state_fips, :state_name,
             :year, :cause_of_death, 'total', :deaths, :age_adjusted_rate)
        ON CONFLICT (geo_id, year, cause_of_death, race)
        DO UPDATE SET
            deaths = :deaths,
            age_adjusted_rate = :age_adjusted_rate,
            state_name = :state_name
    """)

    context.log.info("Fetching state-level mortality data from NCHS SODA API")

    try:
        async with aiohttp.ClientSession() as http_session:
            offset = 0
            limit = 50000
            while True:
                params = {
                    "$limit": str(limit),
                    "$offset": str(offset),
                    "$order": "year,state",
                }
                timeout = aiohttp.ClientTimeout(total=120)
                async with http_session.get(
                    CDC_STATE_MORTALITY_URL, params=params, timeout=timeout
                ) as resp:
                    resp.raise_for_status()
                    rows = await resp.json()

                if not rows:
                    break

                async with async_session() as session:
                    for row in rows:
                        state_name = row.get("state")
                        cause = row.get("cause_name")
                        year_str = row.get("year")

                        if not state_name or not cause or not year_str:
                            continue
                        # Skip the "All causes" aggregation row
                        if cause == "All causes":
                            continue
                        # Skip the "United States" national-level row
                        if state_name == "United States":
                            continue

                        state_fips = STATE_NAME_TO_FIPS.get(state_name)
                        if not state_fips:
                            continue

                        try:
                            year = int(year_str)
                        except (ValueError, TypeError):
                            continue

                        deaths = None
                        try:
                            deaths = int(row.get("deaths", ""))
                        except (ValueError, TypeError):
                            pass

                        aadr = None
                        try:
                            aadr = float(row.get("aadr", ""))
                        except (ValueError, TypeError):
                            pass

                        record_id = uuid.uuid5(
                            uuid.NAMESPACE_URL,
                            f"cdc-mortality:{state_fips}:{year}:{cause}:total",
                        )

                        await session.execute(upsert_sql, {
                            "id": str(record_id),
                            "geo_id": state_fips,
                            "state_fips": state_fips,
                            "state_name": state_name,
                            "year": year,
                            "cause_of_death": cause,
                            "deaths": deaths,
                            "age_adjusted_rate": aadr,
                        })
                        records_ingested += 1
                        states_seen.add(state_fips)
                        causes_seen.add(cause)
                        years_seen.add(year)

                    await session.commit()

                context.log.info(
                    f"Fetched {len(rows)} rows (offset={offset})"
                )
                if len(rows) < limit:
                    break
                offset += limit
    finally:
        await engine.dispose()

    bias_flags = [
        "race disaggregation not available from this source",
        "data ends 2017; source has not been updated since",
    ]
    if len(states_seen) < 51:
        bias_flags.append(
            f"missing {51 - len(states_seen)} states/territories"
        )

    flush_langfuse(langfuse, trace, records_ingested)

    context.log.info(
        f"Ingested {records_ingested} state mortality records "
        f"across {len(states_seen)} states, {len(years_seen)} years"
    )

    return MaterializeResult(
        metadata={
            "records_ingested": records_ingested,
            "states_covered": len(states_seen),
            "causes_covered": sorted(causes_seen),
            "year_range": f"{min(years_seen)}-{max(years_seen)}" if years_seen else "none",
            "source_url": CDC_STATE_MORTALITY_URL,
            "bias_flags": MetadataValue.json_serializable(bias_flags),
        }
    )
```

**Step 4: Run tests to verify they pass**

Run: `cd dagster && python -m pytest tests/test_cdc_mortality_asset.py -v`
Expected: PASS (5 tests)

**Step 5: Commit**

```bash
git add dagster/d4bl_pipelines/assets/apis/cdc_mortality.py dagster/tests/test_cdc_mortality_asset.py
git commit -m "feat: add cdc_mortality_state Dagster asset (#91)"
```

---

### Task 3: Create national race-disaggregated mortality asset

**Files:**
- Modify: `dagster/d4bl_pipelines/assets/apis/cdc_mortality.py`
- Test: `dagster/tests/test_cdc_mortality_asset.py`

**Step 1: Add tests**

Append to `dagster/tests/test_cdc_mortality_asset.py`:

```python
def test_cdc_mortality_national_race_asset_exists():
    """The cdc_mortality_national_race asset should be importable."""
    from d4bl_pipelines.assets.apis.cdc_mortality import cdc_mortality_national_race

    assert cdc_mortality_national_race is not None


def test_cdc_mortality_national_race_asset_group():
    """Asset should belong to the 'apis' group."""
    from d4bl_pipelines.assets.apis.cdc_mortality import cdc_mortality_national_race

    spec = cdc_mortality_national_race.specs_by_key
    key = next(iter(spec))
    assert key.path[-1] == "cdc_mortality_national_race"
    assert spec[key].group_name == "apis"


def test_race_map_covers_standard_categories():
    """RACE_MAP should map to D4BL standard race values."""
    from d4bl_pipelines.assets.apis.cdc_mortality import RACE_MAP

    d4bl_races = set(RACE_MAP.values())
    assert "black" in d4bl_races
    assert "white" in d4bl_races
    assert "hispanic" in d4bl_races
    assert "asian" in d4bl_races
    assert "native_american" in d4bl_races
```

**Step 2: Run tests to verify they fail**

Run: `cd dagster && python -m pytest tests/test_cdc_mortality_asset.py::test_cdc_mortality_national_race_asset_exists -v`
Expected: FAIL with `ImportError`

**Step 3: Add the national race asset**

Append to `dagster/d4bl_pipelines/assets/apis/cdc_mortality.py` (after the `cdc_mortality_state` function):

```python
@asset(
    group_name="apis",
    description=(
        "National race-disaggregated excess death counts from NCHS (2015-2023). "
        "Weekly data aggregated to annual totals by race/ethnicity."
    ),
    metadata={
        "source": "NCHS AH Excess Deaths by Race (SODA m74n-4hbs)",
        "methodology": "D4BL equity-focused mortality data collection",
    },
    required_resource_keys={"db_url", "langfuse"},
)
async def cdc_mortality_national_race(
    context: AssetExecutionContext,
) -> MaterializeResult:
    """Fetch national excess deaths by race and upsert into cdc_mortality."""
    from collections import defaultdict

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    db_url = context.resources.db_url

    # --- Langfuse tracing ---
    langfuse = context.resources.langfuse
    trace = None
    try:
        if langfuse:
            trace = langfuse.trace(
                name="dagster:cdc_mortality_national_race",
                metadata={"source": "m74n-4hbs"},
            )
    except Exception as exc:
        context.log.warning(f"Langfuse trace init failed: {exc}")
        langfuse = None

    engine = create_async_engine(db_url, pool_size=3, max_overflow=5)
    async_session = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    # Accumulate weekly deaths by (year, race) for annual aggregation
    annual_deaths: dict[tuple[int, str], float] = defaultdict(float)
    rows_fetched = 0

    context.log.info("Fetching national excess deaths by race from NCHS SODA API")

    try:
        async with aiohttp.ClientSession() as http_session:
            offset = 0
            limit = 50000
            while True:
                params = {
                    "$limit": str(limit),
                    "$offset": str(offset),
                    "$where": "sex='All Sex' AND agegroup='All Ages'",
                    "$select": "mmwryear,raceethnicity,deaths_unweighted",
                    "$order": "mmwryear,raceethnicity",
                }
                timeout = aiohttp.ClientTimeout(total=120)
                async with http_session.get(
                    CDC_EXCESS_DEATHS_URL, params=params, timeout=timeout
                ) as resp:
                    resp.raise_for_status()
                    rows = await resp.json()

                if not rows:
                    break

                for row in rows:
                    race_raw = row.get("raceethnicity", "")
                    year_str = row.get("mmwryear", "")
                    deaths_str = row.get("deaths_unweighted", "")

                    race = RACE_MAP.get(race_raw)
                    if not race:
                        continue

                    try:
                        year = int(year_str)
                        deaths = float(deaths_str)
                    except (ValueError, TypeError):
                        continue

                    annual_deaths[(year, race)] += deaths
                    rows_fetched += 1

                context.log.info(
                    f"Fetched {len(rows)} rows (offset={offset})"
                )
                if len(rows) < limit:
                    break
                offset += limit

        # --- Upsert aggregated annual totals ---
        upsert_sql = text("""
            INSERT INTO cdc_mortality
                (id, geo_id, geography_type, state_fips, state_name,
                 year, cause_of_death, race, deaths, age_adjusted_rate)
            VALUES
                (CAST(:id AS UUID), 'US', 'national', NULL, NULL,
                 :year, 'all_causes', :race, :deaths, NULL)
            ON CONFLICT (geo_id, year, cause_of_death, race)
            DO UPDATE SET
                deaths = :deaths
        """)

        records_ingested = 0
        years_seen = set()
        races_seen = set()

        async with async_session() as session:
            for (year, race), total_deaths in sorted(annual_deaths.items()):
                record_id = uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    f"cdc-mortality:US:{year}:all_causes:{race}",
                )
                await session.execute(upsert_sql, {
                    "id": str(record_id),
                    "year": year,
                    "race": race,
                    "deaths": int(total_deaths),
                })
                records_ingested += 1
                years_seen.add(year)
                races_seen.add(race)

            await session.commit()
    finally:
        await engine.dispose()

    bias_flags = [
        "national-level only; no state/county breakdown by race",
        "counts under 10 suppressed by NCHS",
        "weekly data aggregated to annual totals; some precision lost",
    ]

    flush_langfuse(langfuse, trace, records_ingested)

    context.log.info(
        f"Ingested {records_ingested} national mortality records "
        f"({len(races_seen)} races, {len(years_seen)} years) "
        f"from {rows_fetched} weekly rows"
    )

    return MaterializeResult(
        metadata={
            "records_ingested": records_ingested,
            "weekly_rows_fetched": rows_fetched,
            "races_covered": sorted(races_seen),
            "year_range": f"{min(years_seen)}-{max(years_seen)}" if years_seen else "none",
            "source_url": CDC_EXCESS_DEATHS_URL,
            "bias_flags": MetadataValue.json_serializable(bias_flags),
        }
    )
```

**Step 4: Run tests to verify they pass**

Run: `cd dagster && python -m pytest tests/test_cdc_mortality_asset.py -v`
Expected: PASS (8 tests)

**Step 5: Commit**

```bash
git add dagster/d4bl_pipelines/assets/apis/cdc_mortality.py dagster/tests/test_cdc_mortality_asset.py
git commit -m "feat: add cdc_mortality_national_race Dagster asset (#91)"
```

---

### Task 4: Register assets and add schedules

**Files:**
- Modify: `dagster/d4bl_pipelines/assets/apis/__init__.py`
- Modify: `dagster/d4bl_pipelines/assets/__init__.py`
- Modify: `dagster/d4bl_pipelines/schedules.py`

**Step 1: Register in apis/__init__.py**

Add to `dagster/d4bl_pipelines/assets/apis/__init__.py`:

Import (add after the `cdc_places` import, line 2):
```python
from d4bl_pipelines.assets.apis.cdc_mortality import (
    cdc_mortality_national_race,
    cdc_mortality_state,
)
```

Add to `__all__` list (after `"cdc_places_health"`, alphabetically):
```python
    "cdc_mortality_national_race",
    "cdc_mortality_state",
```

**Step 2: Register in assets/__init__.py**

Add to `dagster/d4bl_pipelines/assets/__init__.py`:

Import (add after the `cdc_places_health` import):
```python
    cdc_mortality_national_race,
    cdc_mortality_state,
```

Add to `__all__` list (after `"cdc_places_health"`, alphabetically):
```python
    "cdc_mortality_national_race",
    "cdc_mortality_state",
```

**Step 3: Add schedules**

Add to `STATIC_SCHEDULES` dict in `dagster/d4bl_pipelines/schedules.py` (after the `cdc_places_health` entry):

```python
    "cdc_mortality_state": "0 0 1 1 *",              # Annually — Jan 1
    "cdc_mortality_national_race": "0 0 1 */3 *",    # Quarterly — 1st of every 3rd month
```

**Step 4: Run existing schedule tests**

Run: `cd dagster && python -m pytest tests/test_schedules.py -v`
Expected: PASS

**Step 5: Run full test suite**

Run: `cd dagster && python -m pytest tests/ -v`
Expected: PASS (all tests including new ones)

**Step 6: Commit**

```bash
git add dagster/d4bl_pipelines/assets/apis/__init__.py dagster/d4bl_pipelines/assets/__init__.py dagster/d4bl_pipelines/schedules.py
git commit -m "feat: register CDC mortality assets and schedules (#91)"
```

---

### Task 5: Integration smoke test

**Step 1: Add a lightweight integration test**

Append to `dagster/tests/test_cdc_mortality_asset.py`:

```python
import pytest


@pytest.mark.integration
def test_cdc_mortality_state_soda_api_reachable():
    """Verify the SODA API endpoint returns data (requires network)."""
    import aiohttp
    import asyncio

    async def _fetch():
        url = "https://data.cdc.gov/resource/bi63-dtpu.json"
        params = {"$limit": "2", "$where": "year='2017' AND state='Alabama'"}
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as resp:
                assert resp.status == 200
                data = await resp.json()
                assert len(data) > 0
                assert "state" in data[0]
                assert "cause_name" in data[0]
                return data

    asyncio.run(_fetch())


@pytest.mark.integration
def test_cdc_mortality_national_race_soda_api_reachable():
    """Verify the excess deaths SODA API returns data (requires network)."""
    import aiohttp
    import asyncio

    async def _fetch():
        url = "https://data.cdc.gov/resource/m74n-4hbs.json"
        params = {
            "$limit": "2",
            "$where": "sex='All Sex' AND agegroup='All Ages'",
            "$select": "mmwryear,raceethnicity,deaths_unweighted",
        }
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as resp:
                assert resp.status == 200
                data = await resp.json()
                assert len(data) > 0
                assert "raceethnicity" in data[0]
                return data

    asyncio.run(_fetch())
```

**Step 2: Run integration tests**

Run: `cd dagster && python -m pytest tests/test_cdc_mortality_asset.py -v -m integration`
Expected: PASS (2 integration tests — verifies API endpoints are live and return expected fields)

**Step 3: Run full test suite one final time**

Run: `cd dagster && python -m pytest tests/ -v`
Expected: All PASS

**Step 4: Commit**

```bash
git add dagster/tests/test_cdc_mortality_asset.py
git commit -m "test: add CDC mortality SODA API integration smoke tests (#91)"
```
