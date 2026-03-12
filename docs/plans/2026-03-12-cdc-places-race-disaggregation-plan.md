# CDC PLACES Race Disaggregation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Cross-reference CDC PLACES health data with Census ACS demographics to produce race-weighted health outcome estimates at county and tract levels.

**Architecture:** Four incremental PRs. PR 1 adds tract-level CDC PLACES ingestion. PR 2 creates the ACS overlay computation asset with a new DB table. PR 3 adds a backend API endpoint. PR 4 wires the frontend to show race-disaggregated CDC data.

**Tech Stack:** Dagster assets, aiohttp, SQLAlchemy (asyncpg), FastAPI, Next.js/React, Recharts

---

## PR 1: CDC PLACES Tract-Level Ingestion

Branch: `feat/cdc-places-tract-75`

### Task 1.1: Add tract-level tests

**Files:**
- Modify: `dagster/tests/test_cdc_places_asset.py`

**Step 1: Write the failing tests**

Add these tests to `dagster/tests/test_cdc_places_asset.py`:

```python
from d4bl_pipelines.assets.apis.cdc_places import (
    CDC_MEASURES,
    CDC_PLACES_TRACT_URL,
    CDC_PLACES_URL,
    cdc_places_health,
    cdc_places_tract_health,
)


def test_cdc_places_tract_asset_exists():
    """The cdc_places_tract_health asset should be importable."""
    assert cdc_places_tract_health is not None


def test_cdc_places_tract_asset_group_name():
    """Tract asset should belong to the 'apis' group."""
    spec = cdc_places_tract_health.specs_by_key
    key = next(iter(spec))
    assert spec[key].group_name == "apis"


def test_cdc_places_tract_url_is_tract_endpoint():
    """Tract URL should point to the census tract SODA endpoint."""
    assert "cwsq-ngmh" in CDC_PLACES_TRACT_URL


def test_cdc_places_county_url_is_county_endpoint():
    """County URL should point to the county SODA endpoint."""
    assert "swc5-untb" in CDC_PLACES_URL
```

**Step 2: Run tests to verify they fail**

Run: `cd dagster && python -m pytest tests/test_cdc_places_asset.py -v`
Expected: FAIL — `ImportError: cannot import name 'CDC_PLACES_TRACT_URL'`

**Step 3: Commit failing tests**

```bash
git add dagster/tests/test_cdc_places_asset.py
git commit -m "test: add failing tests for CDC PLACES tract-level asset (#75)"
```

### Task 1.2: Implement tract-level CDC PLACES asset

**Files:**
- Modify: `dagster/d4bl_pipelines/assets/apis/cdc_places.py`

**Step 1: Add tract URL constant and extract shared fetch helper**

At the top of `cdc_places.py`, after `CDC_PLACES_URL`, add:

```python
# SODA API endpoint for CDC PLACES census-tract-level data
CDC_PLACES_TRACT_URL = "https://data.cdc.gov/resource/cwsq-ngmh.json"
```

Then add a shared helper function after the constants:

```python
async def _fetch_places_measures(
    http_session: aiohttp.ClientSession,
    url: str,
    year: int,
    measures: list[str],
    fips_field: str,
    select_fields: str,
    context,
) -> list[dict]:
    """Fetch paginated CDC PLACES data for all measures from a SODA endpoint.

    Args:
        url: SODA API endpoint URL.
        year: Data year to fetch.
        measures: List of measure IDs (e.g. ["DIABETES", "OBESITY"]).
        fips_field: API field name for the FIPS code (e.g. "countyfips" or "locationid").
        select_fields: Comma-separated list of fields for $select param.
        context: Dagster context for logging.

    Returns:
        List of parsed row dicts with keys: fips, geo_name, state_fips,
        measure, category, value, dvt, low_cl, high_cl, pop.
    """
    results = []
    for measure in measures:
        offset = 0
        limit = 5000
        while True:
            params = {
                "$where": f"year={year} AND measureid='{measure}'",
                "$limit": str(limit),
                "$offset": str(offset),
                "$select": select_fields,
            }
            timeout = aiohttp.ClientTimeout(total=120)
            async with http_session.get(url, params=params, timeout=timeout) as resp:
                resp.raise_for_status()
                rows = await resp.json()

            if not rows:
                break

            for row in rows:
                fips = row.get(fips_field)
                data_val = row.get("data_value")
                if not fips or data_val is None:
                    continue
                try:
                    value = float(data_val)
                except (ValueError, TypeError):
                    continue

                low_cl = None
                high_cl = None
                try:
                    low_cl = float(row.get("low_confidence_limit", ""))
                except (ValueError, TypeError):
                    pass
                try:
                    high_cl = float(row.get("high_confidence_limit", ""))
                except (ValueError, TypeError):
                    pass

                pop = None
                try:
                    pop = int(row.get("totalpopulation", ""))
                except (ValueError, TypeError):
                    pass

                results.append({
                    "fips": fips,
                    "geo_name": row.get("locationname", ""),
                    "state_fips": fips[:2],
                    "measure": measure,
                    "category": MEASURE_CATEGORIES.get(measure, "other"),
                    "value": value,
                    "dvt": row.get("data_value_type", "Crude prevalence"),
                    "low_cl": low_cl,
                    "high_cl": high_cl,
                    "pop": pop,
                })

            context.log.info(
                f"  {measure}: fetched {len(rows)} rows (offset={offset})"
            )
            if len(rows) < limit:
                break
            offset += limit

    return results
```

**Step 2: Add the tract-level asset**

Add below the existing `cdc_places_health` asset:

```python
@asset(
    group_name="apis",
    description=(
        "Health outcomes and prevention measures by census tract from CDC PLACES. "
        "Includes diabetes, blood pressure, asthma, mental health, and more. "
        "~83,500 tracts × 10 measures."
    ),
    metadata={
        "source": "CDC PLACES (SODA API — tract level)",
        "methodology": "D4BL equity-focused health data collection",
    },
    required_resource_keys={"db_url", "langfuse"},
)
async def cdc_places_tract_health(
    context: AssetExecutionContext,
) -> MaterializeResult:
    """Fetch CDC PLACES tract-level data and upsert into cdc_health_outcomes."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    db_url = context.resources.db_url
    year = int(os.environ.get("CDC_PLACES_YEAR", "2023"))

    langfuse = context.resources.langfuse
    trace = None
    try:
        if langfuse:
            trace = langfuse.trace(
                name="dagster:cdc_places_tract_health",
                metadata={"year": year},
            )
    except Exception as exc:
        context.log.warning(f"Langfuse trace init failed: {exc}")
        langfuse = None

    engine = create_async_engine(db_url, pool_size=3, max_overflow=5)
    async_session = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    records_ingested = 0
    states_seen: set[str] = set()
    measures_seen: set[str] = set()

    context.log.info(f"Fetching CDC PLACES tract-level data for year={year}")

    select_fields = (
        "year,stateabbr,statedesc,locationname,"
        "locationid,measureid,measure,"
        "data_value,data_value_type,low_confidence_limit,"
        "high_confidence_limit,totalpopulation,category"
    )

    try:
        async with aiohttp.ClientSession() as http_session:
            parsed_rows = await _fetch_places_measures(
                http_session=http_session,
                url=CDC_PLACES_TRACT_URL,
                year=year,
                measures=CDC_MEASURES,
                fips_field="locationid",
                select_fields=select_fields,
                context=context,
            )

            # Batch upsert
            upsert_sql = text("""
                INSERT INTO cdc_health_outcomes
                    (id, fips_code, geography_type,
                     geography_name, state_fips, year,
                     measure, category, data_value,
                     data_value_type,
                     low_confidence_limit,
                     high_confidence_limit,
                     total_population)
                VALUES
                    (CAST(:id AS UUID), :fips, 'tract',
                     :geo_name, :state_fips, :year,
                     :measure, :category, :value,
                     :dvt, :low_cl, :high_cl, :pop)
                ON CONFLICT (fips_code, year, measure,
                             data_value_type)
                DO UPDATE SET
                    data_value = :value,
                    low_confidence_limit = :low_cl,
                    high_confidence_limit = :high_cl,
                    total_population = :pop,
                    geography_name = :geo_name
            """)

            batch_size = 2000
            for i in range(0, len(parsed_rows), batch_size):
                batch = parsed_rows[i : i + batch_size]
                async with async_session() as session:
                    for row in batch:
                        fips = row["fips"]
                        states_seen.add(fips[:2])
                        measures_seen.add(row["measure"])

                        record_id = uuid.uuid5(
                            uuid.NAMESPACE_URL,
                            f"cdc:{fips}:{year}:{row['measure']}:{row['dvt']}",
                        )

                        await session.execute(
                            upsert_sql,
                            {
                                "id": str(record_id),
                                "fips": fips,
                                "geo_name": row["geo_name"],
                                "state_fips": row["state_fips"],
                                "year": year,
                                "measure": MEASURE_NAMES.get(
                                    row["measure"], row["measure"].lower()
                                ),
                                "category": row["category"],
                                "value": row["value"],
                                "dvt": row["dvt"],
                                "low_cl": row["low_cl"],
                                "high_cl": row["high_cl"],
                                "pop": row["pop"],
                            },
                        )
                        records_ingested += 1
                    await session.commit()

                context.log.info(
                    f"Committed batch {i // batch_size + 1} "
                    f"({records_ingested} total records)"
                )
    finally:
        await engine.dispose()

    bias_flags = []
    if len(measures_seen) < len(CDC_MEASURES):
        missing = set(CDC_MEASURES) - measures_seen
        bias_flags.append(f"missing_measures: {sorted(missing)}")
    bias_flags.append(
        "limitation: no race disaggregation in PLACES"
    )

    flush_langfuse(langfuse, trace, records_ingested)

    context.log.info(
        f"Ingested {records_ingested} CDC PLACES tract records "
        f"across {len(states_seen)} states"
    )

    return MaterializeResult(
        metadata={
            "records_ingested": records_ingested,
            "year": year,
            "states_covered": len(states_seen),
            "measures_covered": sorted(measures_seen),
            "source_url": CDC_PLACES_TRACT_URL,
            "bias_flags": MetadataValue.json_serializable(bias_flags),
        }
    )
```

**Step 3: Run tests to verify they pass**

Run: `cd dagster && python -m pytest tests/test_cdc_places_asset.py -v`
Expected: all PASS

**Step 4: Commit**

```bash
git add dagster/d4bl_pipelines/assets/apis/cdc_places.py
git commit -m "feat: add CDC PLACES tract-level ingestion asset (#75)"
```

### Task 1.3: Register asset and add schedule

**Files:**
- Modify: `dagster/d4bl_pipelines/assets/apis/__init__.py`
- Modify: `dagster/d4bl_pipelines/assets/__init__.py`
- Modify: `dagster/d4bl_pipelines/schedules.py`

**Step 1: Register in apis/__init__.py**

Add to imports:
```python
from d4bl_pipelines.assets.apis.cdc_places import cdc_places_health, cdc_places_tract_health
```

Add `"cdc_places_tract_health"` to `__all__`.

**Step 2: Register in assets/__init__.py**

Add to imports:
```python
from d4bl_pipelines.assets.apis import (
    ...
    cdc_places_health,
    cdc_places_tract_health,
    ...
)
```

Add `"cdc_places_tract_health"` to `__all__`.

**Step 3: Add schedule**

In `schedules.py`, add to `STATIC_SCHEDULES`:
```python
"cdc_places_tract_health": "0 0 1 */3 *",  # Quarterly — 1st of every 3rd month
```

**Step 4: Run all tests**

Run: `cd dagster && python -m pytest tests/ -v`
Expected: all PASS

**Step 5: Commit**

```bash
git add dagster/d4bl_pipelines/assets/apis/__init__.py dagster/d4bl_pipelines/assets/__init__.py dagster/d4bl_pipelines/schedules.py
git commit -m "feat: register CDC PLACES tract asset and add schedule (#75)"
```

### Task 1.4: Create PR

```bash
gh pr create --title "feat: add CDC PLACES tract-level ingestion (#75)" --body "$(cat <<'EOF'
## Summary
- Add `cdc_places_tract_health` Dagster asset fetching ~83,500 census tracts from CDC PLACES SODA API
- Extract shared `_fetch_places_measures()` helper to DRY county and tract fetching
- Add quarterly schedule matching county asset
- Closes: Part 1 of #75

## Test plan
- [ ] `pytest dagster/tests/test_cdc_places_asset.py -v` passes
- [ ] Manual: `dagster dev` shows new asset in UI
EOF
)"
```

---

## PR 2: ACS Race Overlay Computation

Branch: `feat/cdc-acs-overlay-75` (off latest main after PR 1 merges)

### Task 2.1: Add migration for cdc_acs_race_estimates table

**Files:**
- Create: `supabase/migrations/20260312000001_add_cdc_acs_race_estimates.sql`

**Step 1: Write the migration**

```sql
-- CDC + ACS race-weighted health outcome estimates
CREATE TABLE IF NOT EXISTS cdc_acs_race_estimates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    fips_code VARCHAR(11) NOT NULL,
    geography_type VARCHAR(10) NOT NULL,
    geography_name VARCHAR(200) NOT NULL,
    state_fips VARCHAR(2) NOT NULL,
    year INTEGER NOT NULL,
    measure VARCHAR(50) NOT NULL,
    race VARCHAR(20) NOT NULL,
    health_rate FLOAT NOT NULL,
    race_population_share FLOAT NOT NULL,
    estimated_value FLOAT NOT NULL,
    total_population INTEGER,
    confidence_low FLOAT,
    confidence_high FLOAT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_cdc_acs_race_key
    ON cdc_acs_race_estimates(fips_code, year, measure, race);
CREATE INDEX IF NOT EXISTS ix_cdc_acs_race_state
    ON cdc_acs_race_estimates(state_fips, measure, year, race);
CREATE INDEX IF NOT EXISTS ix_cdc_acs_race_geo_type
    ON cdc_acs_race_estimates(geography_type, year);

-- RLS
ALTER TABLE cdc_acs_race_estimates ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Authenticated users can read cdc_acs_race_estimates"
    ON cdc_acs_race_estimates FOR SELECT
    USING (auth.role() = 'authenticated');

CREATE POLICY "Admins can manage cdc_acs_race_estimates"
    ON cdc_acs_race_estimates FOR ALL
    USING (EXISTS (SELECT 1 FROM profiles WHERE profiles.id = auth.uid() AND profiles.role = 'admin'))
    WITH CHECK (EXISTS (SELECT 1 FROM profiles WHERE profiles.id = auth.uid() AND profiles.role = 'admin'));
```

**Step 2: Commit**

```bash
git add supabase/migrations/20260312000001_add_cdc_acs_race_estimates.sql
git commit -m "feat: add migration for cdc_acs_race_estimates table (#75)"
```

### Task 2.2: Add SQLAlchemy model

**Files:**
- Modify: `src/d4bl/infra/database.py`

**Step 1: Add the model**

Add after `CdcHealthOutcome` class:

```python
class CdcAcsRaceEstimate(Base):
    """Race-weighted CDC health estimates via ACS demographic overlay."""
    __tablename__ = "cdc_acs_race_estimates"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    fips_code = Column(String(11), nullable=False, index=True)
    geography_type = Column(String(10), nullable=False)
    geography_name = Column(String(200), nullable=False)
    state_fips = Column(String(2), nullable=False, index=True)
    year = Column(Integer, nullable=False)
    measure = Column(String(50), nullable=False)
    race = Column(String(20), nullable=False)
    health_rate = Column(Float, nullable=False)
    race_population_share = Column(Float, nullable=False)
    estimated_value = Column(Float, nullable=False)
    total_population = Column(Integer, nullable=True)
    confidence_low = Column(Float, nullable=True)
    confidence_high = Column(Float, nullable=True)
    created_at = Column(DateTime, nullable=False, default=_utc_now)

    __table_args__ = (
        UniqueConstraint(
            "fips_code", "year", "measure", "race",
            name="uq_cdc_acs_race_key",
        ),
        Index("ix_cdc_acs_race_state", "state_fips", "measure", "year", "race"),
        Index("ix_cdc_acs_race_geo_type", "geography_type", "year"),
    )
```

**Step 2: Commit**

```bash
git add src/d4bl/infra/database.py
git commit -m "feat: add CdcAcsRaceEstimate model (#75)"
```

### Task 2.3: Write overlay tests

**Files:**
- Create: `dagster/tests/test_cdc_acs_overlay.py`

**Step 1: Write the failing tests**

```python
from d4bl_pipelines.assets.apis.cdc_acs_overlay import (
    RACES,
    compute_race_estimates,
    cdc_acs_race_overlay,
)


def test_overlay_asset_exists():
    """The cdc_acs_race_overlay asset should be importable."""
    assert cdc_acs_race_overlay is not None


def test_overlay_asset_group_name():
    """Overlay asset should belong to the 'apis' group."""
    spec = cdc_acs_race_overlay.specs_by_key
    key = next(iter(spec))
    assert spec[key].group_name == "apis"


def test_races_includes_expected():
    """Should include black, white, hispanic."""
    assert "black" in RACES
    assert "white" in RACES
    assert "hispanic" in RACES


def test_compute_race_estimates_basic():
    """Proportional attribution: health_rate * (race_pop / total_pop)."""
    cdc_row = {
        "fips_code": "17031",
        "geography_type": "county",
        "geography_name": "Cook County",
        "state_fips": "17",
        "year": 2023,
        "measure": "diabetes",
        "data_value": 12.0,
        "low_confidence_limit": 10.0,
        "high_confidence_limit": 14.0,
    }
    acs_pops = {
        "total": 5000000,
        "black": 1200000,
        "white": 2000000,
        "hispanic": 1300000,
    }
    results = compute_race_estimates(cdc_row, acs_pops)

    assert len(results) == 3  # black, white, hispanic (not total)

    black_result = next(r for r in results if r["race"] == "black")
    assert black_result["health_rate"] == 12.0
    assert abs(black_result["race_population_share"] - 0.24) < 0.001
    assert abs(black_result["estimated_value"] - 2.88) < 0.01
    assert black_result["total_population"] == 5000000


def test_compute_race_estimates_zero_total_pop():
    """Should return empty list when total population is zero."""
    cdc_row = {
        "fips_code": "99999",
        "geography_type": "county",
        "geography_name": "Empty County",
        "state_fips": "99",
        "year": 2023,
        "measure": "diabetes",
        "data_value": 10.0,
        "low_confidence_limit": None,
        "high_confidence_limit": None,
    }
    acs_pops = {"total": 0, "black": 0, "white": 0, "hispanic": 0}
    results = compute_race_estimates(cdc_row, acs_pops)
    assert results == []


def test_compute_race_estimates_missing_race():
    """Should skip races not present in ACS data."""
    cdc_row = {
        "fips_code": "17031",
        "geography_type": "county",
        "geography_name": "Cook County",
        "state_fips": "17",
        "year": 2023,
        "measure": "obesity",
        "data_value": 30.0,
        "low_confidence_limit": 28.0,
        "high_confidence_limit": 32.0,
    }
    acs_pops = {"total": 1000, "black": 300}
    results = compute_race_estimates(cdc_row, acs_pops)

    assert len(results) == 1
    assert results[0]["race"] == "black"
```

**Step 2: Run tests to verify they fail**

Run: `cd dagster && python -m pytest tests/test_cdc_acs_overlay.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Commit**

```bash
git add dagster/tests/test_cdc_acs_overlay.py
git commit -m "test: add failing tests for CDC ACS race overlay (#75)"
```

### Task 2.4: Implement overlay asset

**Files:**
- Create: `dagster/d4bl_pipelines/assets/apis/cdc_acs_overlay.py`

**Step 1: Write the implementation**

```python
"""CDC PLACES + Census ACS race overlay computation.

Joins CDC PLACES health outcomes with Census ACS demographics to produce
race-weighted health outcome estimates via proportional attribution.
"""

import os
import uuid

from d4bl_pipelines.utils import flush_langfuse
from dagster import (
    AssetExecutionContext,
    MaterializeResult,
    MetadataValue,
    asset,
)

RACES = ["black", "white", "hispanic"]

# Census ACS metrics used for population shares
POP_METRIC = "homeownership_rate"  # We use its denominator (total households) as proxy
# Actually we need raw population — ACS stores race-specific values per metric.
# We'll query the poverty_rate metric's denominator-equivalent: the "total" race row
# gives total pop, and race-specific rows give race pop.
# But census_indicators stores (fips, year, race, metric, value) where value is a rate.
# We need to find the population counts. The Census ACS asset computes rates from
# numerator/denominator, but only stores the rate and margin_of_error — not raw pop.
#
# Alternative approach: query Census API directly for population variables,
# or use the ACS data we have. Since census_indicators stores rates (e.g. poverty_rate
# for each race), we can't derive population counts from rates alone.
#
# Simplest fix: use the CDC PLACES total_population for the geography, and Census ACS
# race-specific population proportions. But we don't have those stored either.
#
# Best approach for MVP: Query Census ACS API for B01003_001E (total pop) and
# B01003 race-specific tables during overlay computation. OR, add a population
# metric to the existing Census ACS pipeline.
#
# For this implementation: we'll query the Census ACS API directly for population
# by race at county and tract levels. This keeps the overlay self-contained.

CENSUS_BASE_URL = "https://api.census.gov/data"

# Population variables by race
# B03002: Hispanic or Latino Origin by Race
POP_VARIABLES = {
    "total": "B03002_001E",       # Total population
    "white": "B03002_003E",       # White alone, not Hispanic
    "black": "B03002_004E",       # Black alone
    "hispanic": "B03002_012E",    # Hispanic or Latino
}

POP_VAR_LIST = ",".join(POP_VARIABLES.values())


async def _fetch_acs_population(http_session, year, level, state_fips=None):
    """Fetch population by race from Census ACS API.

    Args:
        http_session: aiohttp session.
        year: ACS year.
        level: 'county' or 'tract'.
        state_fips: Required for tract-level queries.

    Returns:
        Dict mapping fips_code -> {race: population}.
    """
    import aiohttp

    api_key = os.environ.get("CENSUS_API_KEY", "")
    base = f"{CENSUS_BASE_URL}/{year}/acs/acs5"

    if level == "county":
        params = {
            "get": f"NAME,{POP_VAR_LIST}",
            "for": "county:*",
            "key": api_key,
        }
    else:
        params = {
            "get": f"NAME,{POP_VAR_LIST}",
            "for": "tract:*",
            "in": f"state:{state_fips}",
            "key": api_key,
        }

    timeout = aiohttp.ClientTimeout(total=120)
    async with http_session.get(base, params=params, timeout=timeout) as resp:
        resp.raise_for_status()
        data = await resp.json()

    if not data or len(data) < 2:
        return {}

    header = data[0]
    results = {}

    # Find column indices
    var_indices = {}
    for race, var in POP_VARIABLES.items():
        if var in header:
            var_indices[race] = header.index(var)

    state_idx = header.index("state") if "state" in header else None
    county_idx = header.index("county") if "county" in header else None
    tract_idx = header.index("tract") if "tract" in header else None

    for row in data[1:]:
        if level == "county" and state_idx is not None and county_idx is not None:
            fips = row[state_idx] + row[county_idx]
        elif level == "tract" and state_idx is not None and county_idx is not None and tract_idx is not None:
            fips = row[state_idx] + row[county_idx] + row[tract_idx]
        else:
            continue

        pops = {}
        for race, idx in var_indices.items():
            try:
                pops[race] = int(float(row[idx]))
            except (ValueError, TypeError):
                pass

        if pops.get("total", 0) > 0:
            results[fips] = pops

    return results


def compute_race_estimates(cdc_row, acs_pops):
    """Compute race-weighted estimates for a single CDC PLACES record.

    Args:
        cdc_row: Dict with keys: fips_code, geography_type, geography_name,
                 state_fips, year, measure, data_value,
                 low_confidence_limit, high_confidence_limit.
        acs_pops: Dict mapping race -> population count.
                  Must include 'total' key.

    Returns:
        List of dicts, one per race, with computed estimates.
    """
    total_pop = acs_pops.get("total", 0)
    if total_pop <= 0:
        return []

    health_rate = cdc_row["data_value"]
    results = []

    for race in RACES:
        race_pop = acs_pops.get(race)
        if race_pop is None:
            continue

        share = race_pop / total_pop
        estimated = health_rate * share

        results.append({
            "fips_code": cdc_row["fips_code"],
            "geography_type": cdc_row["geography_type"],
            "geography_name": cdc_row["geography_name"],
            "state_fips": cdc_row["state_fips"],
            "year": cdc_row["year"],
            "measure": cdc_row["measure"],
            "race": race,
            "health_rate": health_rate,
            "race_population_share": round(share, 6),
            "estimated_value": round(estimated, 4),
            "total_population": total_pop,
            "confidence_low": cdc_row.get("low_confidence_limit"),
            "confidence_high": cdc_row.get("high_confidence_limit"),
        })

    return results


# All 51 state FIPS codes (50 states + DC)
STATE_FIPS = [
    "01", "02", "04", "05", "06", "08", "09", "10", "11", "12",
    "13", "15", "16", "17", "18", "19", "20", "21", "22", "23",
    "24", "25", "26", "27", "28", "29", "30", "31", "32", "33",
    "34", "35", "36", "37", "38", "39", "40", "41", "42", "44",
    "45", "46", "47", "48", "49", "50", "51", "53", "54", "55",
    "56",
]


@asset(
    group_name="apis",
    description=(
        "Race-weighted health outcome estimates by county and tract. "
        "Joins CDC PLACES health rates with Census ACS population by race "
        "using proportional attribution."
    ),
    metadata={
        "source": "CDC PLACES + Census ACS (computed overlay)",
        "methodology": (
            "D4BL equity-focused: proportional attribution of health rates "
            "by racial population share. Limitation: assumes uniform health "
            "rate across racial groups within each geography."
        ),
    },
    required_resource_keys={"db_url", "langfuse"},
    deps=["cdc_places_health", "census_acs_county_indicators"],
)
async def cdc_acs_race_overlay(
    context: AssetExecutionContext,
) -> MaterializeResult:
    """Compute race-weighted CDC health estimates using ACS demographics."""
    import aiohttp
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    db_url = context.resources.db_url
    year = int(os.environ.get("CDC_PLACES_YEAR", "2023"))
    acs_year = int(os.environ.get("ACS_YEAR", "2022"))

    langfuse = context.resources.langfuse
    trace = None
    try:
        if langfuse:
            trace = langfuse.trace(
                name="dagster:cdc_acs_race_overlay",
                metadata={"cdc_year": year, "acs_year": acs_year},
            )
    except Exception as exc:
        context.log.warning(f"Langfuse trace init failed: {exc}")
        langfuse = None

    engine = create_async_engine(db_url, pool_size=3, max_overflow=5)
    async_session = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    records_ingested = 0
    geographies_processed = {"county": 0, "tract": 0}

    upsert_sql = text("""
        INSERT INTO cdc_acs_race_estimates
            (id, fips_code, geography_type, geography_name,
             state_fips, year, measure, race,
             health_rate, race_population_share, estimated_value,
             total_population, confidence_low, confidence_high)
        VALUES
            (CAST(:id AS UUID), :fips_code, :geography_type, :geography_name,
             :state_fips, :year, :measure, :race,
             :health_rate, :race_population_share, :estimated_value,
             :total_population, :confidence_low, :confidence_high)
        ON CONFLICT (fips_code, year, measure, race)
        DO UPDATE SET
            health_rate = :health_rate,
            race_population_share = :race_population_share,
            estimated_value = :estimated_value,
            total_population = :total_population,
            confidence_low = :confidence_low,
            confidence_high = :confidence_high,
            geography_name = :geography_name
    """)

    try:
        async with aiohttp.ClientSession() as http_session:
            # --- County level ---
            context.log.info("Processing county-level overlay...")
            acs_county_pops = await _fetch_acs_population(
                http_session, acs_year, "county"
            )
            context.log.info(
                f"Fetched ACS population for {len(acs_county_pops)} counties"
            )

            async with async_session() as session:
                result = await session.execute(
                    text("""
                        SELECT fips_code, geography_type, geography_name,
                               state_fips, year, measure, data_value,
                               low_confidence_limit, high_confidence_limit
                        FROM cdc_health_outcomes
                        WHERE geography_type = 'county' AND year = :year
                    """),
                    {"year": year},
                )
                cdc_county_rows = [dict(r._mapping) for r in result]

            context.log.info(
                f"Found {len(cdc_county_rows)} CDC county records"
            )

            batch = []
            for cdc_row in cdc_county_rows:
                fips = cdc_row["fips_code"]
                acs_pops = acs_county_pops.get(fips)
                if not acs_pops:
                    continue

                estimates = compute_race_estimates(cdc_row, acs_pops)
                for est in estimates:
                    est["id"] = str(uuid.uuid5(
                        uuid.NAMESPACE_URL,
                        f"cdc_acs:{est['fips_code']}:{est['year']}:"
                        f"{est['measure']}:{est['race']}",
                    ))
                    batch.append(est)

            async with async_session() as session:
                for row in batch:
                    await session.execute(upsert_sql, row)
                    records_ingested += 1
                await session.commit()

            geographies_processed["county"] = len(batch)
            context.log.info(
                f"County overlay complete: {len(batch)} records"
            )

            # --- Tract level ---
            context.log.info("Processing tract-level overlay...")

            # Check if we have tract-level CDC data
            async with async_session() as session:
                result = await session.execute(
                    text("""
                        SELECT COUNT(*) as cnt
                        FROM cdc_health_outcomes
                        WHERE geography_type = 'tract' AND year = :year
                    """),
                    {"year": year},
                )
                tract_count = result.scalar()

            if tract_count and tract_count > 0:
                for st_fips in STATE_FIPS:
                    context.log.info(
                        f"  Tract overlay for state {st_fips}..."
                    )
                    acs_tract_pops = await _fetch_acs_population(
                        http_session, acs_year, "tract",
                        state_fips=st_fips,
                    )

                    async with async_session() as session:
                        result = await session.execute(
                            text("""
                                SELECT fips_code, geography_type,
                                       geography_name, state_fips, year,
                                       measure, data_value,
                                       low_confidence_limit,
                                       high_confidence_limit
                                FROM cdc_health_outcomes
                                WHERE geography_type = 'tract'
                                  AND year = :year
                                  AND state_fips = :state_fips
                            """),
                            {"year": year, "state_fips": st_fips},
                        )
                        cdc_tract_rows = [
                            dict(r._mapping) for r in result
                        ]

                    batch = []
                    for cdc_row in cdc_tract_rows:
                        fips = cdc_row["fips_code"]
                        acs_pops = acs_tract_pops.get(fips)
                        if not acs_pops:
                            continue

                        estimates = compute_race_estimates(cdc_row, acs_pops)
                        for est in estimates:
                            est["id"] = str(uuid.uuid5(
                                uuid.NAMESPACE_URL,
                                f"cdc_acs:{est['fips_code']}:{est['year']}:"
                                f"{est['measure']}:{est['race']}",
                            ))
                            batch.append(est)

                    if batch:
                        async with async_session() as session:
                            for row in batch:
                                await session.execute(upsert_sql, row)
                                records_ingested += 1
                            await session.commit()
                        geographies_processed["tract"] += len(batch)

                context.log.info(
                    f"Tract overlay complete: "
                    f"{geographies_processed['tract']} records"
                )
            else:
                context.log.info(
                    "No tract-level CDC data found; skipping tract overlay"
                )
    finally:
        await engine.dispose()

    bias_flags = [
        "computed estimate via proportional attribution, not direct measurement",
        "assumes uniform health rate across racial groups within geography",
    ]

    flush_langfuse(langfuse, trace, records_ingested, extra_metadata={
        "county_records": geographies_processed["county"],
        "tract_records": geographies_processed["tract"],
    })

    context.log.info(
        f"Total overlay records: {records_ingested} "
        f"(county={geographies_processed['county']}, "
        f"tract={geographies_processed['tract']})"
    )

    return MaterializeResult(
        metadata={
            "records_ingested": records_ingested,
            "cdc_year": year,
            "acs_year": acs_year,
            "county_records": geographies_processed["county"],
            "tract_records": geographies_processed["tract"],
            "bias_flags": MetadataValue.json_serializable(bias_flags),
            "quality_score": MetadataValue.float(3.0),
        }
    )
```

**Step 2: Run tests**

Run: `cd dagster && python -m pytest tests/test_cdc_acs_overlay.py -v`
Expected: all PASS

**Step 3: Commit**

```bash
git add dagster/d4bl_pipelines/assets/apis/cdc_acs_overlay.py
git commit -m "feat: add CDC ACS race overlay computation asset (#75)"
```

### Task 2.5: Register overlay asset and schedule

**Files:**
- Modify: `dagster/d4bl_pipelines/assets/apis/__init__.py`
- Modify: `dagster/d4bl_pipelines/assets/__init__.py`
- Modify: `dagster/d4bl_pipelines/schedules.py`

**Step 1: Register in apis/__init__.py**

Add import:
```python
from d4bl_pipelines.assets.apis.cdc_acs_overlay import cdc_acs_race_overlay
```

Add `"cdc_acs_race_overlay"` to `__all__`.

**Step 2: Register in assets/__init__.py**

Add import:
```python
from d4bl_pipelines.assets.apis import (
    ...
    cdc_acs_race_overlay,
    ...
)
```

Add `"cdc_acs_race_overlay"` to `__all__`.

**Step 3: Add schedule**

In `schedules.py`, add to `STATIC_SCHEDULES`:
```python
"cdc_acs_race_overlay": "0 6 1 */3 *",  # Quarterly — 6 AM on 1st of every 3rd month (after PLACES)
```

**Step 4: Run all tests**

Run: `cd dagster && python -m pytest tests/ -v`
Expected: all PASS

**Step 5: Commit**

```bash
git add dagster/d4bl_pipelines/assets/apis/__init__.py dagster/d4bl_pipelines/assets/__init__.py dagster/d4bl_pipelines/schedules.py
git commit -m "feat: register overlay asset and add quarterly schedule (#75)"
```

### Task 2.6: Create PR

```bash
gh pr create --title "feat: add CDC+ACS race overlay computation (#75)" --body "$(cat <<'EOF'
## Summary
- New `cdc_acs_race_overlay` Dagster asset computing race-weighted health estimates
- Joins CDC PLACES health rates with Census ACS population by race (proportional attribution)
- Supports both county (~3,200) and tract (~83,500) geographies
- New `cdc_acs_race_estimates` DB table + migration + SQLAlchemy model
- Quarterly schedule runs after CDC PLACES refresh
- Part 2 of #75

## Test plan
- [ ] `pytest dagster/tests/test_cdc_acs_overlay.py -v` passes
- [ ] `pytest dagster/tests/ -v` passes (no regressions)
- [ ] Manual: migration applies cleanly
- [ ] Manual: `dagster dev` shows asset with upstream deps on cdc_places_health
EOF
)"
```

---

## PR 3: Backend API Endpoint

Branch: `feat/cdc-race-api-75` (off latest main after PR 2 merges)

### Task 3.1: Write endpoint test

**Files:**
- Check if endpoint integration tests exist. If not, this is a unit-level test for the query logic.

For now, we test via the existing pattern — the endpoint will follow the same structure as `/api/explore/cdc`.

### Task 3.2: Add the endpoint

**Files:**
- Modify: `src/d4bl/app/api.py`

**Step 1: Add import**

At the top of `api.py`, ensure `CdcAcsRaceEstimate` is imported. Find the existing import of `CdcHealthOutcome` and add alongside it:

```python
from d4bl.infra.database import (
    ...
    CdcAcsRaceEstimate,
    CdcHealthOutcome,
    ...
)
```

**Step 2: Add the endpoint**

Add after the existing `/api/explore/cdc` endpoint:

```python
@app.get("/api/explore/cdc-race", response_model=ExploreResponse)
async def get_cdc_race_estimates(
    state_fips: str | None = None,
    measure: str | None = None,
    race: str | None = None,
    year: int | None = None,
    geography_type: str | None = None,
    limit: int = 1000,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Race-weighted CDC health estimates via ACS overlay."""
    try:
        query = select(CdcAcsRaceEstimate)
        if state_fips:
            query = query.where(CdcAcsRaceEstimate.state_fips == state_fips)
        if measure:
            query = query.where(CdcAcsRaceEstimate.measure == measure)
        if race:
            query = query.where(CdcAcsRaceEstimate.race == race)
        if year:
            query = query.where(CdcAcsRaceEstimate.year == year)
        if geography_type:
            query = query.where(
                CdcAcsRaceEstimate.geography_type == geography_type
            )
        query = query.order_by(
            CdcAcsRaceEstimate.state_fips
        ).limit(max(1, min(limit, 5000)))

        result = await db.execute(query)
        rows_raw = result.scalars().all()

        row_dicts = [
            {
                "state_fips": r.state_fips,
                "state_name": r.geography_name,
                "value": r.estimated_value,
                "metric": r.measure,
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
        logger.error("Failed to fetch CDC race estimates", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to fetch CDC race estimates",
        )
```

**Step 3: Commit**

```bash
git add src/d4bl/app/api.py
git commit -m "feat: add /api/explore/cdc-race endpoint (#75)"
```

### Task 3.3: Create PR

```bash
gh pr create --title "feat: add API endpoint for CDC race estimates (#75)" --body "$(cat <<'EOF'
## Summary
- New `GET /api/explore/cdc-race` endpoint returning race-weighted CDC health estimates
- Supports filters: state_fips, measure, race, year, geography_type
- Returns standard ExploreResponse with available_races populated
- Part 3 of #75

## Test plan
- [ ] `curl localhost:8000/api/explore/cdc-race` returns ExploreResponse shape
- [ ] Filtering by race=black returns only black estimates
- [ ] No regressions on existing /api/explore/cdc endpoint
EOF
)"
```

---

## PR 4: Frontend Race Selector

Branch: `feat/cdc-race-frontend-75` (off latest main after PR 3 merges)

### Task 4.1: Add CDC Race data source config

**Files:**
- Modify: `ui-nextjs/lib/explore-config.ts`

**Step 1: Add new data source entry**

Add after the existing `cdc` entry in `DATA_SOURCES`:

```typescript
  {
    key: "cdc-race",
    label: "CDC Health × Race",
    accent: "#ff6b6b",
    endpoint: "/api/explore/cdc-race",
    hasRace: true,
    primaryFilterKey: "measure",
    primaryFilterLabel: "Measure",
  },
```

**Step 2: Commit**

```bash
git add ui-nextjs/lib/explore-config.ts
git commit -m "feat: add CDC Race data source to explore config (#75)"
```

### Task 4.2: Verify frontend renders correctly

**Step 1: Run the frontend**

Run: `cd ui-nextjs && npm run build`
Expected: Build succeeds with no errors.

The existing explore page logic already handles `hasRace: true` sources — it shows the `RacialGapChart` and race selector in `MetricFilterPanel`. No additional component changes should be needed.

**Step 2: Commit (if any fixes needed)**

```bash
git add -u
git commit -m "fix: adjust frontend for CDC race source (#75)"
```

### Task 4.3: Create PR

```bash
gh pr create --title "feat: add CDC Health x Race tab to data explorer (#75)" --body "$(cat <<'EOF'
## Summary
- Add "CDC Health × Race" tab to the data explorer
- Shows race-weighted health estimates with RacialGapChart
- Uses existing race selector and filter panel infrastructure
- Closes #75

## Test plan
- [ ] `npm run build` succeeds
- [ ] New tab appears in explore page
- [ ] Selecting a measure shows racial gap chart
- [ ] Race filter works correctly
EOF
)"
```
