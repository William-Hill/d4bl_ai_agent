# Data Sources Expansion Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add 8 new open data source Dagster assets with dedicated database tables, migrations, and tests to populate D4BL with equity-focused data.

**Architecture:** Each source is a hardcoded async Dagster asset in `dagster/d4bl_pipelines/assets/apis/`, with a dedicated SQLAlchemy model and Supabase migration. All assets follow the Census ACS pattern: async aiohttp, Langfuse tracing, lineage recording, bias flags, and graceful API key skipping.

**Tech Stack:** Dagster, SQLAlchemy, asyncpg, aiohttp, PostgreSQL (Supabase)

---

## Sprint 1: Database Foundation (Tables + Migration)

### Task 1: Add 8 SQLAlchemy models to database.py

**Files:**
- Modify: `src/d4bl/infra/database.py` (after `KeywordMonitor` class, ~line 367)

**Step 1: Add the 8 new model classes**

Add these models after the `KeywordMonitor` class (before `get_database_url()`):

```python
class CdcHealthOutcome(Base):
    """Health outcomes from CDC PLACES."""
    __tablename__ = "cdc_health_outcomes"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    fips_code = Column(String(11), nullable=False, index=True)
    geography_type = Column(String(10), nullable=False)
    geography_name = Column(Text, nullable=False)
    state_fips = Column(String(2), nullable=False, index=True)
    year = Column(Integer, nullable=False)
    measure = Column(String(200), nullable=False)
    category = Column(String(100), nullable=True)
    data_value = Column(Float, nullable=False)
    data_value_type = Column(String(50), nullable=False)
    low_confidence_limit = Column(Float, nullable=True)
    high_confidence_limit = Column(Float, nullable=True)
    total_population = Column(Integer, nullable=True)
    created_at = Column(DateTime, nullable=False, default=_utc_now)

    __table_args__ = (
        UniqueConstraint(
            "fips_code", "year", "measure", "data_value_type",
            name="uq_cdc_health_outcome_key",
        ),
        Index("ix_cdc_health_state_measure", "state_fips", "measure", "year"),
    )


class EpaEnvironmentalJustice(Base):
    """Environmental justice screening from EPA EJScreen."""
    __tablename__ = "epa_environmental_justice"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    tract_fips = Column(String(11), nullable=False, index=True)
    state_fips = Column(String(2), nullable=False, index=True)
    state_name = Column(String(50), nullable=False)
    year = Column(Integer, nullable=False)
    indicator = Column(String(200), nullable=False)
    raw_value = Column(Float, nullable=True)
    percentile_state = Column(Float, nullable=True)
    percentile_national = Column(Float, nullable=True)
    demographic_index = Column(Float, nullable=True)
    population = Column(Integer, nullable=True)
    minority_pct = Column(Float, nullable=True)
    low_income_pct = Column(Float, nullable=True)
    created_at = Column(DateTime, nullable=False, default=_utc_now)

    __table_args__ = (
        UniqueConstraint(
            "tract_fips", "year", "indicator",
            name="uq_epa_ej_key",
        ),
        Index("ix_epa_ej_state_indicator", "state_fips", "indicator", "year"),
    )


class FbiCrimeStat(Base):
    """Crime statistics from FBI Crime Data Explorer."""
    __tablename__ = "fbi_crime_stats"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    state_abbrev = Column(String(2), nullable=False, index=True)
    state_name = Column(String(50), nullable=False)
    offense = Column(String(200), nullable=False)
    category = Column(String(100), nullable=False)
    race = Column(String(50), nullable=False)
    ethnicity = Column(String(50), nullable=True)
    year = Column(Integer, nullable=False)
    value = Column(Float, nullable=False)
    population = Column(Integer, nullable=True)
    created_at = Column(DateTime, nullable=False, default=_utc_now)

    __table_args__ = (
        UniqueConstraint(
            "state_abbrev", "offense", "race", "year", "category",
            name="uq_fbi_crime_key",
        ),
        Index("ix_fbi_crime_state_race_year", "state_abbrev", "race", "year"),
    )


class BlsLaborStatistic(Base):
    """Labor statistics from BLS."""
    __tablename__ = "bls_labor_statistics"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    series_id = Column(String(50), nullable=False)
    state_fips = Column(String(2), nullable=True)
    state_name = Column(String(50), nullable=True)
    metric = Column(String(200), nullable=False)
    race = Column(String(50), nullable=False)
    year = Column(Integer, nullable=False)
    period = Column(String(10), nullable=False)
    value = Column(Float, nullable=False)
    footnotes = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=_utc_now)

    __table_args__ = (
        UniqueConstraint(
            "series_id", "year", "period",
            name="uq_bls_labor_key",
        ),
        Index("ix_bls_labor_metric_race_year", "metric", "race", "year"),
    )


class HudFairHousing(Base):
    """Fair housing data from HUD."""
    __tablename__ = "hud_fair_housing"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    fips_code = Column(String(11), nullable=False, index=True)
    geography_type = Column(String(10), nullable=False)
    geography_name = Column(Text, nullable=False)
    state_fips = Column(String(2), nullable=False, index=True)
    year = Column(Integer, nullable=False)
    indicator = Column(String(200), nullable=False)
    category = Column(String(100), nullable=True)
    value = Column(Float, nullable=False)
    race_group_a = Column(String(50), nullable=True)
    race_group_b = Column(String(50), nullable=True)
    created_at = Column(DateTime, nullable=False, default=_utc_now)

    __table_args__ = (
        UniqueConstraint(
            "fips_code", "year", "indicator", "race_group_a", "race_group_b",
            name="uq_hud_fair_housing_key",
        ),
        Index("ix_hud_fh_state_indicator", "state_fips", "indicator", "year"),
    )


class UsdaFoodAccess(Base):
    """Food access data from USDA."""
    __tablename__ = "usda_food_access"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    tract_fips = Column(String(11), nullable=False, index=True)
    state_fips = Column(String(2), nullable=False, index=True)
    county_fips = Column(String(5), nullable=True)
    state_name = Column(String(50), nullable=True)
    county_name = Column(String(100), nullable=True)
    year = Column(Integer, nullable=False)
    indicator = Column(String(200), nullable=False)
    value = Column(Float, nullable=False)
    urban_rural = Column(String(10), nullable=True)
    population = Column(Integer, nullable=True)
    poverty_rate = Column(Float, nullable=True)
    median_income = Column(Float, nullable=True)
    created_at = Column(DateTime, nullable=False, default=_utc_now)

    __table_args__ = (
        UniqueConstraint(
            "tract_fips", "year", "indicator",
            name="uq_usda_food_access_key",
        ),
        Index("ix_usda_fa_state_indicator", "state_fips", "indicator", "year"),
    )


class DoeCivilRights(Base):
    """Civil rights data from DOE CRDC."""
    __tablename__ = "doe_civil_rights"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    district_id = Column(String(20), nullable=False, index=True)
    district_name = Column(Text, nullable=False)
    state = Column(String(2), nullable=False, index=True)
    state_name = Column(String(50), nullable=False)
    school_year = Column(String(9), nullable=False)
    metric = Column(String(200), nullable=False)
    category = Column(String(100), nullable=True)
    race = Column(String(50), nullable=False)
    value = Column(Float, nullable=False)
    total_enrollment = Column(Integer, nullable=True)
    created_at = Column(DateTime, nullable=False, default=_utc_now)

    __table_args__ = (
        UniqueConstraint(
            "district_id", "school_year", "metric", "race",
            name="uq_doe_civil_rights_key",
        ),
        Index("ix_doe_cr_state_metric_race", "state", "metric", "race"),
    )


class PoliceViolenceIncident(Base):
    """Police violence incidents from Mapping Police Violence."""
    __tablename__ = "police_violence_incidents"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    incident_id = Column(String(100), nullable=False, unique=True)
    date = Column(Date, nullable=False)
    year = Column(Integer, nullable=False, index=True)
    state = Column(String(2), nullable=False, index=True)
    city = Column(String(200), nullable=True)
    county = Column(String(200), nullable=True)
    race = Column(String(50), nullable=True)
    age = Column(Integer, nullable=True)
    gender = Column(String(20), nullable=True)
    armed_status = Column(String(100), nullable=True)
    cause_of_death = Column(String(200), nullable=True)
    circumstances = Column(Text, nullable=True)
    criminal_charges = Column(String(200), nullable=True)
    agency = Column(String(200), nullable=True)
    source_url = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=_utc_now)

    __table_args__ = (
        Index("ix_pv_state_race_year", "state", "race", "year"),
    )
```

**Step 2: Run a quick import check**

Run: `cd /Users/william-meroxa/Development/d4bl_ai_agent && source .venv/bin/activate && python -c "from d4bl.infra.database import CdcHealthOutcome, PoliceViolenceIncident; print('OK')"`
Expected: `OK`

**Step 3: Commit**

```bash
git add src/d4bl/infra/database.py
git commit -m "feat: add 8 new SQLAlchemy models for data source expansion"
```

---

### Task 2: Create Supabase migration for the 8 new tables

**Files:**
- Create: `supabase/migrations/20260310000001_add_open_data_tables.sql`

**Step 1: Write the migration**

```sql
-- CDC Health Outcomes (CDC PLACES)
CREATE TABLE IF NOT EXISTS cdc_health_outcomes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    fips_code VARCHAR(11) NOT NULL,
    geography_type VARCHAR(10) NOT NULL,
    geography_name TEXT NOT NULL,
    state_fips VARCHAR(2) NOT NULL,
    year INTEGER NOT NULL,
    measure VARCHAR(200) NOT NULL,
    category VARCHAR(100),
    data_value FLOAT NOT NULL,
    data_value_type VARCHAR(50) NOT NULL,
    low_confidence_limit FLOAT,
    high_confidence_limit FLOAT,
    total_population INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_cdc_health_outcome_key
    ON cdc_health_outcomes(fips_code, year, measure, data_value_type);
CREATE INDEX IF NOT EXISTS ix_cdc_health_state_measure
    ON cdc_health_outcomes(state_fips, measure, year);

-- EPA Environmental Justice (EJScreen)
CREATE TABLE IF NOT EXISTS epa_environmental_justice (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tract_fips VARCHAR(11) NOT NULL,
    state_fips VARCHAR(2) NOT NULL,
    state_name VARCHAR(50) NOT NULL,
    year INTEGER NOT NULL,
    indicator VARCHAR(200) NOT NULL,
    raw_value FLOAT,
    percentile_state FLOAT,
    percentile_national FLOAT,
    demographic_index FLOAT,
    population INTEGER,
    minority_pct FLOAT,
    low_income_pct FLOAT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_epa_ej_key
    ON epa_environmental_justice(tract_fips, year, indicator);
CREATE INDEX IF NOT EXISTS ix_epa_ej_state_indicator
    ON epa_environmental_justice(state_fips, indicator, year);

-- FBI Crime Stats
CREATE TABLE IF NOT EXISTS fbi_crime_stats (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    state_abbrev VARCHAR(2) NOT NULL,
    state_name VARCHAR(50) NOT NULL,
    offense VARCHAR(200) NOT NULL,
    category VARCHAR(100) NOT NULL,
    race VARCHAR(50) NOT NULL,
    ethnicity VARCHAR(50),
    year INTEGER NOT NULL,
    value FLOAT NOT NULL,
    population INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_fbi_crime_key
    ON fbi_crime_stats(state_abbrev, offense, race, year, category);
CREATE INDEX IF NOT EXISTS ix_fbi_crime_state_race_year
    ON fbi_crime_stats(state_abbrev, race, year);

-- BLS Labor Statistics
CREATE TABLE IF NOT EXISTS bls_labor_statistics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    series_id VARCHAR(50) NOT NULL,
    state_fips VARCHAR(2),
    state_name VARCHAR(50),
    metric VARCHAR(200) NOT NULL,
    race VARCHAR(50) NOT NULL,
    year INTEGER NOT NULL,
    period VARCHAR(10) NOT NULL,
    value FLOAT NOT NULL,
    footnotes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_bls_labor_key
    ON bls_labor_statistics(series_id, year, period);
CREATE INDEX IF NOT EXISTS ix_bls_labor_metric_race_year
    ON bls_labor_statistics(metric, race, year);

-- HUD Fair Housing
CREATE TABLE IF NOT EXISTS hud_fair_housing (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    fips_code VARCHAR(11) NOT NULL,
    geography_type VARCHAR(10) NOT NULL,
    geography_name TEXT NOT NULL,
    state_fips VARCHAR(2) NOT NULL,
    year INTEGER NOT NULL,
    indicator VARCHAR(200) NOT NULL,
    category VARCHAR(100),
    value FLOAT NOT NULL,
    race_group_a VARCHAR(50),
    race_group_b VARCHAR(50),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_hud_fair_housing_key
    ON hud_fair_housing(fips_code, year, indicator, race_group_a, race_group_b);
CREATE INDEX IF NOT EXISTS ix_hud_fh_state_indicator
    ON hud_fair_housing(state_fips, indicator, year);

-- USDA Food Access
CREATE TABLE IF NOT EXISTS usda_food_access (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tract_fips VARCHAR(11) NOT NULL,
    state_fips VARCHAR(2) NOT NULL,
    county_fips VARCHAR(5),
    state_name VARCHAR(50),
    county_name VARCHAR(100),
    year INTEGER NOT NULL,
    indicator VARCHAR(200) NOT NULL,
    value FLOAT NOT NULL,
    urban_rural VARCHAR(10),
    population INTEGER,
    poverty_rate FLOAT,
    median_income FLOAT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_usda_food_access_key
    ON usda_food_access(tract_fips, year, indicator);
CREATE INDEX IF NOT EXISTS ix_usda_fa_state_indicator
    ON usda_food_access(state_fips, indicator, year);

-- DOE Civil Rights (CRDC)
CREATE TABLE IF NOT EXISTS doe_civil_rights (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    district_id VARCHAR(20) NOT NULL,
    district_name TEXT NOT NULL,
    state VARCHAR(2) NOT NULL,
    state_name VARCHAR(50) NOT NULL,
    school_year VARCHAR(9) NOT NULL,
    metric VARCHAR(200) NOT NULL,
    category VARCHAR(100),
    race VARCHAR(50) NOT NULL,
    value FLOAT NOT NULL,
    total_enrollment INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_doe_civil_rights_key
    ON doe_civil_rights(district_id, school_year, metric, race);
CREATE INDEX IF NOT EXISTS ix_doe_cr_state_metric_race
    ON doe_civil_rights(state, metric, race);

-- Police Violence Incidents
CREATE TABLE IF NOT EXISTS police_violence_incidents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_id VARCHAR(100) NOT NULL UNIQUE,
    date DATE NOT NULL,
    year INTEGER NOT NULL,
    state VARCHAR(2) NOT NULL,
    city VARCHAR(200),
    county VARCHAR(200),
    race VARCHAR(50),
    age INTEGER,
    gender VARCHAR(20),
    armed_status VARCHAR(100),
    cause_of_death VARCHAR(200),
    circumstances TEXT,
    criminal_charges VARCHAR(200),
    agency VARCHAR(200),
    source_url TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_pv_state_race_year
    ON police_violence_incidents(state, race, year);

-- Enable RLS on all new tables (read-only for authenticated users)
DO $$
DECLARE
    tbl TEXT;
BEGIN
    FOR tbl IN
        SELECT unnest(ARRAY[
            'cdc_health_outcomes',
            'epa_environmental_justice',
            'fbi_crime_stats',
            'bls_labor_statistics',
            'hud_fair_housing',
            'usda_food_access',
            'doe_civil_rights',
            'police_violence_incidents'
        ])
    LOOP
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', tbl);

        EXECUTE format(
            'CREATE POLICY "Authenticated users can read %1$s" ON %1$I FOR SELECT USING (auth.role() = ''authenticated'')',
            tbl
        );

        EXECUTE format(
            'CREATE POLICY "Admins can manage %1$s" ON %1$I FOR ALL USING (EXISTS (SELECT 1 FROM profiles WHERE profiles.id = auth.uid() AND profiles.role = ''admin'')) WITH CHECK (EXISTS (SELECT 1 FROM profiles WHERE profiles.id = auth.uid() AND profiles.role = ''admin''))',
            tbl
        );
    END LOOP;
END $$;
```

**Step 2: Commit**

```bash
git add supabase/migrations/20260310000001_add_open_data_tables.sql
git commit -m "feat: add migration for 8 new open data tables"
```

---

## Sprint 2: Dagster Assets — Auth-Free Sources (CDC, EPA, HUD, USDA, DOE, MPV)

Each task follows the same pattern. The asset file structure:
1. Constants (API URLs, state FIPS maps, etc.)
2. Helper functions (parsing, rate computation)
3. `_flush_langfuse()` helper (copied from census_acs pattern)
4. The `@asset` function

After each asset, update the `__init__.py` imports and add a test file.

### Task 3: CDC PLACES health outcomes asset

**Files:**
- Create: `dagster/d4bl_pipelines/assets/apis/cdc_places.py`
- Modify: `dagster/d4bl_pipelines/assets/apis/__init__.py`
- Modify: `dagster/d4bl_pipelines/assets/__init__.py`
- Create: `dagster/tests/test_cdc_places_asset.py`

**Step 1: Write the test file**

```python
# dagster/tests/test_cdc_places_asset.py
from d4bl_pipelines.assets.apis.cdc_places import (
    CDC_MEASURES,
    cdc_places_health,
)


def test_cdc_places_asset_exists():
    """The cdc_places_health asset should be importable."""
    assert cdc_places_health is not None


def test_cdc_places_asset_has_metadata():
    """Asset should have group and description metadata."""
    spec = cdc_places_health.specs_by_key
    key = next(iter(spec))
    assert key.path[-1] == "cdc_places_health"


def test_cdc_places_asset_group_name():
    """Asset should belong to the 'apis' group."""
    spec = cdc_places_health.specs_by_key
    key = next(iter(spec))
    assert spec[key].group_name == "apis"


def test_cdc_measures_non_empty():
    """CDC_MEASURES should have health equity measures."""
    assert len(CDC_MEASURES) >= 5
    assert "DIABETES" in CDC_MEASURES or "diabetes" in [m.lower() for m in CDC_MEASURES]
```

**Step 2: Run test to verify it fails**

Run: `cd dagster && python -m pytest tests/test_cdc_places_asset.py -v`
Expected: FAIL (ImportError)

**Step 3: Write the asset**

```python
# dagster/d4bl_pipelines/assets/apis/cdc_places.py
"""CDC PLACES health outcomes ingestion asset.

Fetches health outcome and prevention measures by county/state
from the CDC PLACES SODA API. No authentication required.
"""

import hashlib
import json
import os
import uuid

import aiohttp

from dagster import (
    AssetExecutionContext,
    MaterializeResult,
    MetadataValue,
    asset,
)

# SODA API endpoint for CDC PLACES county-level data
CDC_PLACES_URL = "https://data.cdc.gov/resource/swc5-untb.json"

# Health equity measures to fetch
CDC_MEASURES = [
    "DIABETES",
    "BPHIGH",       # High blood pressure
    "CASTHMA",      # Current asthma
    "CHD",          # Coronary heart disease
    "MHLTH",        # Mental health not good
    "OBESITY",      # Obesity
    "CSMOKING",     # Current smoking
    "ACCESS2",      # No health insurance (18-64)
    "CHECKUP",      # Annual checkup
    "DEPRESSION",   # Depression
]

# Human-readable measure names
MEASURE_NAMES = {
    "DIABETES": "diabetes",
    "BPHIGH": "high_blood_pressure",
    "CASTHMA": "current_asthma",
    "CHD": "coronary_heart_disease",
    "MHLTH": "poor_mental_health",
    "OBESITY": "obesity",
    "CSMOKING": "current_smoking",
    "ACCESS2": "lack_health_insurance",
    "CHECKUP": "annual_checkup",
    "DEPRESSION": "depression",
}

MEASURE_CATEGORIES = {
    "DIABETES": "health_outcomes",
    "BPHIGH": "health_outcomes",
    "CASTHMA": "health_outcomes",
    "CHD": "health_outcomes",
    "MHLTH": "health_outcomes",
    "OBESITY": "health_risk_behaviors",
    "CSMOKING": "health_risk_behaviors",
    "ACCESS2": "health_status",
    "CHECKUP": "prevention",
    "DEPRESSION": "health_outcomes",
}


def _flush_langfuse(langfuse, trace, records_ingested=0, extra_metadata=None):
    """Best-effort Langfuse trace finalization."""
    try:
        if trace:
            metadata = {"records_ingested": records_ingested}
            if extra_metadata:
                metadata.update(extra_metadata)
            trace.update(metadata=metadata)
        if langfuse:
            langfuse.flush()
    except Exception:
        pass


@asset(
    group_name="apis",
    description=(
        "Health outcomes and prevention measures by county from CDC PLACES. "
        "Includes diabetes, blood pressure, asthma, mental health, and more."
    ),
    metadata={
        "source": "CDC PLACES (SODA API)",
        "methodology": "D4BL equity-focused health data collection",
    },
    required_resource_keys={"db_url", "langfuse"},
)
async def cdc_places_health(
    context: AssetExecutionContext,
) -> MaterializeResult:
    """Fetch CDC PLACES data and upsert into cdc_health_outcomes table."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    db_url = context.resources.db_url
    year = int(os.environ.get("CDC_PLACES_YEAR", "2023"))

    # --- Langfuse tracing ---
    langfuse = context.resources.langfuse
    trace = None
    try:
        if langfuse:
            trace = langfuse.trace(
                name="dagster:cdc_places_health",
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
    states_seen = set()
    measures_seen = set()

    context.log.info(f"Fetching CDC PLACES data for year={year}")

    try:
        async with aiohttp.ClientSession() as http_session:
            for measure in CDC_MEASURES:
                offset = 0
                limit = 5000
                while True:
                    params = {
                        "$where": f"year={year} AND measureid='{measure}'",
                        "$limit": str(limit),
                        "$offset": str(offset),
                        "$select": (
                            "year,stateabbr,statedesc,locationname,"
                            "countyname,countyfips,measureid,measure,"
                            "data_value,data_value_type,low_confidence_limit,"
                            "high_confidence_limit,totalpopulation,category"
                        ),
                    }
                    timeout = aiohttp.ClientTimeout(total=60)
                    async with http_session.get(
                        CDC_PLACES_URL, params=params, timeout=timeout
                    ) as resp:
                        resp.raise_for_status()
                        rows = await resp.json()

                    if not rows:
                        break

                    async with async_session() as session:
                        for row in rows:
                            fips = row.get("countyfips")
                            data_val = row.get("data_value")
                            if not fips or data_val is None:
                                continue
                            try:
                                value = float(data_val)
                            except (ValueError, TypeError):
                                continue

                            state_abbr = row.get("stateabbr", "")
                            states_seen.add(state_abbr)
                            measures_seen.add(measure)

                            record_id = uuid.uuid5(
                                uuid.NAMESPACE_URL,
                                f"cdc:{fips}:{year}:{measure}:"
                                f"{row.get('data_value_type', 'crude')}",
                            )

                            dvt = row.get(
                                "data_value_type", "Crude prevalence"
                            )

                            low_cl = None
                            high_cl = None
                            try:
                                low_cl = float(
                                    row.get("low_confidence_limit", "")
                                )
                            except (ValueError, TypeError):
                                pass
                            try:
                                high_cl = float(
                                    row.get("high_confidence_limit", "")
                                )
                            except (ValueError, TypeError):
                                pass

                            pop = None
                            try:
                                pop = int(
                                    row.get("totalpopulation", "")
                                )
                            except (ValueError, TypeError):
                                pass

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
                                    (CAST(:id AS UUID), :fips, 'county',
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
                            await session.execute(
                                upsert_sql,
                                {
                                    "id": str(record_id),
                                    "fips": fips,
                                    "geo_name": row.get(
                                        "locationname",
                                        row.get("countyname", ""),
                                    ),
                                    "state_fips": state_abbr,
                                    "year": year,
                                    "measure": MEASURE_NAMES.get(
                                        measure, measure.lower()
                                    ),
                                    "category": MEASURE_CATEGORIES.get(
                                        measure, "other"
                                    ),
                                    "value": value,
                                    "dvt": dvt,
                                    "low_cl": low_cl,
                                    "high_cl": high_cl,
                                    "pop": pop,
                                },
                            )
                            records_ingested += 1

                        await session.commit()

                    context.log.info(
                        f"  {measure}: fetched {len(rows)} rows "
                        f"(offset={offset})"
                    )
                    if len(rows) < limit:
                        break
                    offset += limit
    finally:
        await engine.dispose()

    bias_flags = []
    if len(measures_seen) < len(CDC_MEASURES):
        missing = set(CDC_MEASURES) - measures_seen
        bias_flags.append(f"missing_measures: {sorted(missing)}")
    bias_flags.append(
        "limitation: county-level only, no race disaggregation in PLACES"
    )

    _flush_langfuse(langfuse, trace, records_ingested)

    context.log.info(
        f"Ingested {records_ingested} CDC PLACES records "
        f"across {len(states_seen)} states"
    )

    return MaterializeResult(
        metadata={
            "records_ingested": records_ingested,
            "year": year,
            "states_covered": len(states_seen),
            "measures_covered": sorted(measures_seen),
            "source_url": CDC_PLACES_URL,
            "bias_flags": MetadataValue.json_serializable(bias_flags),
        }
    )
```

**Step 4: Update `dagster/d4bl_pipelines/assets/apis/__init__.py`**

```python
from d4bl_pipelines.assets.apis.cdc_places import cdc_places_health
from d4bl_pipelines.assets.apis.census_acs import census_acs_indicators
from d4bl_pipelines.assets.apis.openstates import openstates_bills

__all__ = ["census_acs_indicators", "cdc_places_health", "openstates_bills"]
```

**Step 5: Update `dagster/d4bl_pipelines/assets/__init__.py`**

```python
from d4bl_pipelines.assets.apis import (
    cdc_places_health,
    census_acs_indicators,
    openstates_bills,
)

__all__ = ["cdc_places_health", "census_acs_indicators", "openstates_bills"]
```

**Step 6: Run tests**

Run: `cd dagster && python -m pytest tests/test_cdc_places_asset.py -v`
Expected: PASS (all 4 tests)

**Step 7: Commit**

```bash
git add dagster/d4bl_pipelines/assets/apis/cdc_places.py \
        dagster/d4bl_pipelines/assets/apis/__init__.py \
        dagster/d4bl_pipelines/assets/__init__.py \
        dagster/tests/test_cdc_places_asset.py
git commit -m "feat: add CDC PLACES health outcomes Dagster asset"
```

---

### Task 4: EPA EJScreen environmental justice asset

**Files:**
- Create: `dagster/d4bl_pipelines/assets/apis/epa_ejscreen.py`
- Modify: `dagster/d4bl_pipelines/assets/apis/__init__.py`
- Modify: `dagster/d4bl_pipelines/assets/__init__.py`
- Create: `dagster/tests/test_epa_ejscreen_asset.py`

**Step 1: Write the test file**

```python
# dagster/tests/test_epa_ejscreen_asset.py
from d4bl_pipelines.assets.apis.epa_ejscreen import (
    EJ_INDICATORS,
    epa_ejscreen,
)


def test_epa_ejscreen_asset_exists():
    assert epa_ejscreen is not None


def test_epa_ejscreen_asset_has_metadata():
    spec = epa_ejscreen.specs_by_key
    key = next(iter(spec))
    assert key.path[-1] == "epa_ejscreen"


def test_epa_ejscreen_asset_group_name():
    spec = epa_ejscreen.specs_by_key
    key = next(iter(spec))
    assert spec[key].group_name == "apis"


def test_ej_indicators_non_empty():
    assert len(EJ_INDICATORS) >= 5
```

**Step 2: Run test to verify it fails**

Run: `cd dagster && python -m pytest tests/test_epa_ejscreen_asset.py -v`
Expected: FAIL

**Step 3: Write the asset**

```python
# dagster/d4bl_pipelines/assets/apis/epa_ejscreen.py
"""EPA EJScreen environmental justice ingestion asset.

Fetches environmental justice screening data by state from the
EPA EJScreen API. No authentication required.

Note: EJScreen data is fetched at state summary level.
Tract-level data can be added as follow-up work.
"""

import hashlib
import json
import os
import uuid

import aiohttp

from dagster import (
    AssetExecutionContext,
    MaterializeResult,
    MetadataValue,
    asset,
)

# EPA EJScreen ArcGIS REST endpoint for state-level summaries
EPA_EJSCREEN_URL = (
    "https://ejscreen.epa.gov/mapper/ejscreenRESTbroker.aspx"
)

# Key EJ indicators to track
EJ_INDICATORS = [
    "PM25",                  # Particulate Matter 2.5
    "OZONE",                 # Ozone
    "DSLPM",                 # Diesel particulate matter
    "CANCER",                # Air toxics cancer risk
    "RESP",                  # Air toxics respiratory HI
    "PTRAF",                 # Traffic proximity
    "PNPL",                  # Superfund proximity
    "PRMP",                  # RMP facility proximity
    "PTSDF",                 # Hazardous waste proximity
    "PWDIS",                 # Wastewater discharge
    "PRE1960PCT",            # Pre-1960 housing (lead paint)
    "UNDER5PCT",             # Under age 5
    "OVER64PCT",             # Over age 64
    "MINORPCT",              # People of color
    "LOWINCPCT",             # Low income
    "LINGISOPCT",            # Linguistic isolation
    "LESSHSPCT",             # Less than high school education
    "UNEMPPCT",              # Unemployment rate
]

# State FIPS codes for iteration
STATE_FIPS = {
    "01": "Alabama", "02": "Alaska", "04": "Arizona",
    "05": "Arkansas", "06": "California", "08": "Colorado",
    "09": "Connecticut", "10": "Delaware",
    "11": "District of Columbia", "12": "Florida",
    "13": "Georgia", "15": "Hawaii", "16": "Idaho",
    "17": "Illinois", "18": "Indiana", "19": "Iowa",
    "20": "Kansas", "21": "Kentucky", "22": "Louisiana",
    "23": "Maine", "24": "Maryland", "25": "Massachusetts",
    "26": "Michigan", "27": "Minnesota", "28": "Mississippi",
    "29": "Missouri", "30": "Montana", "31": "Nebraska",
    "32": "Nevada", "33": "New Hampshire", "34": "New Jersey",
    "35": "New Mexico", "36": "New York",
    "37": "North Carolina", "38": "North Dakota",
    "39": "Ohio", "40": "Oklahoma", "41": "Oregon",
    "42": "Pennsylvania", "44": "Rhode Island",
    "45": "South Carolina", "46": "South Dakota",
    "47": "Tennessee", "48": "Texas", "49": "Utah",
    "50": "Vermont", "51": "Virginia", "53": "Washington",
    "54": "West Virginia", "55": "Wisconsin", "56": "Wyoming",
}


def _flush_langfuse(langfuse, trace, records_ingested=0, extra_metadata=None):
    """Best-effort Langfuse trace finalization."""
    try:
        if trace:
            metadata = {"records_ingested": records_ingested}
            if extra_metadata:
                metadata.update(extra_metadata)
            trace.update(metadata=metadata)
        if langfuse:
            langfuse.flush()
    except Exception:
        pass


@asset(
    group_name="apis",
    description=(
        "Environmental justice screening indicators by state from EPA EJScreen. "
        "Includes pollution, proximity, and demographic indicators."
    ),
    metadata={
        "source": "EPA EJScreen",
        "methodology": "D4BL environmental justice data collection",
    },
    required_resource_keys={"db_url", "langfuse"},
)
async def epa_ejscreen(
    context: AssetExecutionContext,
) -> MaterializeResult:
    """Fetch EPA EJScreen state-level data and upsert into epa_environmental_justice."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    db_url = context.resources.db_url
    year = int(os.environ.get("EPA_EJSCREEN_YEAR", "2024"))

    langfuse = context.resources.langfuse
    trace = None
    try:
        if langfuse:
            trace = langfuse.trace(
                name="dagster:epa_ejscreen",
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
    states_covered = set()

    context.log.info(f"Fetching EPA EJScreen data for year={year}")

    try:
        async with aiohttp.ClientSession() as http_session:
            for fips, state_name in STATE_FIPS.items():
                params = {
                    "namestr": "",
                    "geometry": "",
                    "distance": "",
                    "unit": "9035",
                    "aession": "",
                    "f": "json",
                    "areaid": fips,
                    "areatype": "state",
                }
                timeout = aiohttp.ClientTimeout(total=60)
                try:
                    async with http_session.get(
                        EPA_EJSCREEN_URL, params=params, timeout=timeout
                    ) as resp:
                        if resp.status != 200:
                            context.log.warning(
                                f"EPA EJScreen returned {resp.status} "
                                f"for state {fips} ({state_name})"
                            )
                            continue
                        data = await resp.json(content_type=None)
                except Exception as fetch_exc:
                    context.log.warning(
                        f"Failed to fetch EJScreen for {fips}: {fetch_exc}"
                    )
                    continue

                # Parse the response - EJScreen returns nested data
                raw_data = data if isinstance(data, dict) else {}

                async with async_session() as session:
                    for indicator in EJ_INDICATORS:
                        indicator_lower = indicator.lower()
                        # Try multiple key patterns
                        raw_val = (
                            raw_data.get(indicator)
                            or raw_data.get(indicator_lower)
                            or raw_data.get(f"RAW_{indicator}")
                        )
                        pctile = (
                            raw_data.get(f"P_{indicator}")
                            or raw_data.get(f"PCTILE_{indicator}")
                        )

                        # Skip if no data at all
                        if raw_val is None and pctile is None:
                            continue

                        try:
                            raw_float = float(raw_val) if raw_val is not None else None
                        except (ValueError, TypeError):
                            raw_float = None
                        try:
                            pctile_float = float(pctile) if pctile is not None else None
                        except (ValueError, TypeError):
                            pctile_float = None

                        if raw_float is None and pctile_float is None:
                            continue

                        states_covered.add(fips)

                        record_id = uuid.uuid5(
                            uuid.NAMESPACE_URL,
                            f"epa:{fips}:{year}:{indicator}",
                        )

                        minority = raw_data.get("MINORPCT") or raw_data.get("minorpct")
                        lowinc = raw_data.get("LOWINCPCT") or raw_data.get("lowincpct")
                        pop = raw_data.get("ACSTOTPOP") or raw_data.get("acstotpop")

                        upsert_sql = text("""
                            INSERT INTO epa_environmental_justice
                                (id, tract_fips, state_fips, state_name,
                                 year, indicator, raw_value,
                                 percentile_state, percentile_national,
                                 population, minority_pct, low_income_pct)
                            VALUES
                                (CAST(:id AS UUID), :tract_fips,
                                 :state_fips, :state_name, :year,
                                 :indicator, :raw_value,
                                 :pctile_state, :pctile_national,
                                 :pop, :minority, :lowinc)
                            ON CONFLICT (tract_fips, year, indicator)
                            DO UPDATE SET
                                raw_value = :raw_value,
                                percentile_state = :pctile_state,
                                percentile_national = :pctile_national,
                                population = :pop,
                                minority_pct = :minority,
                                low_income_pct = :lowinc
                        """)
                        await session.execute(
                            upsert_sql,
                            {
                                "id": str(record_id),
                                "tract_fips": fips,
                                "state_fips": fips,
                                "state_name": state_name,
                                "year": year,
                                "indicator": indicator_lower,
                                "raw_value": raw_float,
                                "pctile_state": pctile_float,
                                "pctile_national": pctile_float,
                                "pop": int(pop) if pop else None,
                                "minority": float(minority) if minority else None,
                                "lowinc": float(lowinc) if lowinc else None,
                            },
                        )
                        records_ingested += 1

                    await session.commit()

                context.log.info(
                    f"  State {fips} ({state_name}): processed"
                )
    finally:
        await engine.dispose()

    bias_flags = [
        "limitation: state-level aggregates only, tract data in follow-up",
        "single_source: all data from EPA EJScreen",
    ]
    if len(states_covered) < len(STATE_FIPS):
        missing = set(STATE_FIPS.keys()) - states_covered
        bias_flags.append(
            f"missing_states: {len(missing)} states had no data"
        )

    _flush_langfuse(langfuse, trace, records_ingested)

    return MaterializeResult(
        metadata={
            "records_ingested": records_ingested,
            "year": year,
            "states_covered": len(states_covered),
            "indicators": sorted(EJ_INDICATORS),
            "source_url": EPA_EJSCREEN_URL,
            "bias_flags": MetadataValue.json_serializable(bias_flags),
        }
    )
```

**Step 4: Update `__init__.py` files to add `epa_ejscreen`**

Add to `dagster/d4bl_pipelines/assets/apis/__init__.py`:
```python
from d4bl_pipelines.assets.apis.epa_ejscreen import epa_ejscreen
```
Add `"epa_ejscreen"` to `__all__`.

Add to `dagster/d4bl_pipelines/assets/__init__.py`:
```python
from d4bl_pipelines.assets.apis import epa_ejscreen
```
Add `"epa_ejscreen"` to `__all__`.

**Step 5: Run tests**

Run: `cd dagster && python -m pytest tests/test_epa_ejscreen_asset.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add dagster/d4bl_pipelines/assets/apis/epa_ejscreen.py \
        dagster/d4bl_pipelines/assets/apis/__init__.py \
        dagster/d4bl_pipelines/assets/__init__.py \
        dagster/tests/test_epa_ejscreen_asset.py
git commit -m "feat: add EPA EJScreen environmental justice Dagster asset"
```

---

### Task 5: HUD Fair Housing asset

**Files:**
- Create: `dagster/d4bl_pipelines/assets/apis/hud_fair_housing.py`
- Create: `dagster/tests/test_hud_fair_housing_asset.py`
- Modify: `dagster/d4bl_pipelines/assets/apis/__init__.py`
- Modify: `dagster/d4bl_pipelines/assets/__init__.py`

Follow the exact same pattern as Tasks 3-4. Key specifics:

- **API URL:** `https://www.huduser.gov/hudapi/public/fmr/statedata`
- **Asset name:** `hud_fair_housing`
- **Table:** `hud_fair_housing`
- **Key indicators:** Fair Market Rent by bedroom count, used as housing affordability proxy
- **Unique constraint:** `(fips_code, year, indicator, race_group_a, race_group_b)`
- **Test assertions:** Asset exists, group name is `apis`, description mentions "fair housing"
- **No auth required**

The asset should iterate over states, fetch FMR (Fair Market Rent) data, and upsert into the `hud_fair_housing` table. Include bias flag noting HUD data doesn't directly disaggregate by race.

**Commit message:** `feat: add HUD Fair Housing Dagster asset`

---

### Task 6: USDA Food Access Research Atlas asset

**Files:**
- Create: `dagster/d4bl_pipelines/assets/apis/usda_food_access.py`
- Create: `dagster/tests/test_usda_food_access_asset.py`
- Modify: `dagster/d4bl_pipelines/assets/apis/__init__.py`
- Modify: `dagster/d4bl_pipelines/assets/__init__.py`

Key specifics:

- **API URL:** `https://services1.arcgis.com/RLQu0rK7h4kbsBq5/arcgis/rest/services/Food_Access_Research_Atlas/FeatureServer/0/query`
- **Asset name:** `usda_food_access`
- **Table:** `usda_food_access`
- **Key indicators:** `lapop1`, `lapop10`, `lapop20` (low access population at 1, 10, 20 mile thresholds), `TractSNAP`, `PovertyRate`, `MedianFamilyIncome`
- **Unique constraint:** `(tract_fips, year, indicator)`
- **Pagination:** ArcGIS uses `resultOffset` + `resultRecordCount` (max 2000 per page)
- **No auth required**
- **Bias flag:** Data is tract-level but not race-disaggregated; food desert definitions vary

**Commit message:** `feat: add USDA Food Access Research Atlas Dagster asset`

---

### Task 7: DOE Civil Rights Data Collection asset

**Files:**
- Create: `dagster/d4bl_pipelines/assets/apis/doe_civil_rights.py`
- Create: `dagster/tests/test_doe_civil_rights_asset.py`
- Modify: `dagster/d4bl_pipelines/assets/apis/__init__.py`
- Modify: `dagster/d4bl_pipelines/assets/__init__.py`

Key specifics:

- **Data source:** CRDC bulk CSV download from `https://ocrdata.ed.gov/assets/downloads/`
- **Asset name:** `doe_civil_rights`
- **Table:** `doe_civil_rights`
- **Key metrics:** Suspensions (in-school, out-of-school, expulsions), AP enrollment, chronic absenteeism — all disaggregated by race
- **Unique constraint:** `(district_id, school_year, metric, race)`
- **Race categories:** White, Black, Hispanic, Asian, AIAN, NHPI, Two or more races
- **No auth required** (bulk CSV download)
- **Implementation note:** Download CSV, parse with Python `csv` module (no pandas dependency needed), upsert rows
- **Bias flag:** CRDC data is biennial (every 2 years), most recent is 2020-2021

**Commit message:** `feat: add DOE Civil Rights Data Collection Dagster asset`

---

### Task 8: Mapping Police Violence asset

**Files:**
- Create: `dagster/d4bl_pipelines/assets/apis/mapping_police_violence.py`
- Create: `dagster/tests/test_mapping_police_violence_asset.py`
- Modify: `dagster/d4bl_pipelines/assets/apis/__init__.py`
- Modify: `dagster/d4bl_pipelines/assets/__init__.py`

Key specifics:

- **Data source:** CSV download from Mapping Police Violence dataset
- **Asset name:** `mapping_police_violence`
- **Table:** `police_violence_incidents`
- **Key fields:** date, state, city, race, age, gender, armed_status, cause_of_death, agency
- **Unique constraint:** `(incident_id)` — derive from date+name+city hash if no ID in source
- **No auth required** (public CSV)
- **Race categories from source:** White, Black, Hispanic, Asian, Native American, Pacific Islander, Unknown
- **Bias flag:** Self-reported data, may not capture all incidents; media-sourced

**Commit message:** `feat: add Mapping Police Violence Dagster asset`

---

## Sprint 3: Dagster Assets — API-Key Sources (FBI, BLS)

### Task 9: FBI Crime Data Explorer asset

**Files:**
- Create: `dagster/d4bl_pipelines/assets/apis/fbi_ucr.py`
- Create: `dagster/tests/test_fbi_ucr_asset.py`
- Modify: `dagster/d4bl_pipelines/assets/apis/__init__.py`
- Modify: `dagster/d4bl_pipelines/assets/__init__.py`

Key specifics:

- **API URL:** `https://api.usa.gov/crime/fbi/cde/`
- **Asset name:** `fbi_ucr_crime`
- **Table:** `fbi_crime_stats`
- **Auth:** `FBI_API_KEY` env var — **required, skip gracefully if missing**
- **Endpoints:**
  - `/arrest/states/offense/{state}/{offense}/race` — arrests by race
  - `/hate-crime/state/{state}` — hate crime incidents
- **Unique constraint:** `(state_abbrev, offense, race, year, category)`
- **Graceful skip pattern:**
  ```python
  api_key = os.environ.get("FBI_API_KEY")
  if not api_key:
      context.log.warning("FBI_API_KEY not set - skipping fbi_ucr_crime")
      return MaterializeResult(metadata={"status": "skipped", "reason": "missing_api_key"})
  ```
- **Test:** Include `test_fbi_asset_skips_without_key` — mock the env var and verify skip behavior
- **Bias flag:** FBI data is voluntarily reported by agencies; significant underreporting

**Commit message:** `feat: add FBI Crime Data Explorer Dagster asset`

---

### Task 10: BLS Labor Statistics asset

**Files:**
- Create: `dagster/d4bl_pipelines/assets/apis/bls_labor.py`
- Create: `dagster/tests/test_bls_labor_asset.py`
- Modify: `dagster/d4bl_pipelines/assets/apis/__init__.py`
- Modify: `dagster/d4bl_pipelines/assets/__init__.py`

Key specifics:

- **API URL:** `https://api.bls.gov/publicAPI/v2/timeseries/data/`
- **Asset name:** `bls_labor_stats`
- **Table:** `bls_labor_statistics`
- **Auth:** `BLS_API_KEY` env var — **optional, log warning but continue without it** (lower rate limits without key: 25 req/day vs 500)
- **Method:** POST with JSON body containing series IDs
- **Key series:**
  - `LNS14000003` — Unemployment rate, Black or African American
  - `LNS14000006` — Unemployment rate, White
  - `LNS14000009` — Unemployment rate, Hispanic or Latino
  - `LNS14000000` — Unemployment rate, Total
  - `LEU0252881500` — Median weekly earnings, Black
  - `LEU0252883600` — Median weekly earnings, White
  - `LEU0252884500` — Median weekly earnings, Hispanic
- **Unique constraint:** `(series_id, year, period)`
- **Pagination:** BLS limits to 50 series per request, 20 years per request
- **Bias flag:** National-level only for race-disaggregated data; state-level not race-disaggregated

**Commit message:** `feat: add BLS Labor Statistics Dagster asset`

---

## Sprint 4: Integration + Final Wiring

### Task 11: Final `__init__.py` cleanup and full test run

**Files:**
- Modify: `dagster/d4bl_pipelines/assets/apis/__init__.py`
- Modify: `dagster/d4bl_pipelines/assets/__init__.py`

**Step 1: Verify final `__init__.py` has all 10 assets**

`dagster/d4bl_pipelines/assets/apis/__init__.py` should have:
```python
from d4bl_pipelines.assets.apis.bls_labor import bls_labor_stats
from d4bl_pipelines.assets.apis.cdc_places import cdc_places_health
from d4bl_pipelines.assets.apis.census_acs import census_acs_indicators
from d4bl_pipelines.assets.apis.doe_civil_rights import doe_civil_rights
from d4bl_pipelines.assets.apis.epa_ejscreen import epa_ejscreen
from d4bl_pipelines.assets.apis.fbi_ucr import fbi_ucr_crime
from d4bl_pipelines.assets.apis.hud_fair_housing import hud_fair_housing
from d4bl_pipelines.assets.apis.mapping_police_violence import mapping_police_violence
from d4bl_pipelines.assets.apis.openstates import openstates_bills
from d4bl_pipelines.assets.apis.usda_food_access import usda_food_access

__all__ = [
    "bls_labor_stats",
    "cdc_places_health",
    "census_acs_indicators",
    "doe_civil_rights",
    "epa_ejscreen",
    "fbi_ucr_crime",
    "hud_fair_housing",
    "mapping_police_violence",
    "openstates_bills",
    "usda_food_access",
]
```

**Step 2: Run all Dagster tests**

Run: `cd dagster && python -m pytest tests/ -v`
Expected: All tests PASS

**Step 3: Verify Dagster loads all assets**

Run: `cd dagster && POSTGRES_HOST=localhost POSTGRES_PORT=54322 python -c "from d4bl_pipelines import defs; print(f'Assets: {len(list(defs.get_asset_graph().all_asset_keys))}')"`
Expected: `Assets: 10` (2 existing + 8 new)

**Step 4: Commit**

```bash
git add dagster/d4bl_pipelines/assets/apis/__init__.py \
        dagster/d4bl_pipelines/assets/__init__.py
git commit -m "feat: wire all 10 data source assets into Dagster definitions"
```

---

### Task 12: Apply migration to deployed Supabase

**Step 1: Apply migration via Supabase MCP or psql**

Use the Supabase MCP tool to run the migration SQL, or:
```bash
psql "postgresql://postgres:<password>@db.<project>.supabase.co:5432/postgres" \
    -f supabase/migrations/20260310000001_add_open_data_tables.sql
```

**Step 2: Verify tables exist**

```sql
SELECT table_name FROM information_schema.tables
WHERE table_schema = 'public'
AND table_name IN (
    'cdc_health_outcomes', 'epa_environmental_justice',
    'fbi_crime_stats', 'bls_labor_statistics',
    'hud_fair_housing', 'usda_food_access',
    'doe_civil_rights', 'police_violence_incidents'
);
```
Expected: 8 rows

**Step 3: Commit (no code change, just verify)**

---

### Task 13: Create GitHub issues for follow-up work

Create these GitHub issues:

1. **"Add authentication to Dagster UI on Fly.io"** — Currently the Dagster webserver at d4bl-dagster-web.fly.dev is publicly accessible with no auth gate. Add Fly.io proxy auth or basic auth middleware.

2. **"Add explore page visualizations for new data sources"** — Wire cdc_health_outcomes, epa_environmental_justice, fbi_crime_stats, bls_labor_statistics, hud_fair_housing, usda_food_access, doe_civil_rights, and police_violence_incidents into the frontend explore page with charts and maps.

3. **"Configure cron schedules for data source refresh"** — Set up Dagster schedules for periodic refresh of all 10 data sources (Census ACS annually, CDC quarterly, BLS monthly, etc.)

4. **"Expand data sources to county/tract granularity"** — Several sources (EPA EJScreen, USDA Food Access) support sub-state granularity. Currently ingesting state-level only.

5. **"Add race disaggregation to CDC PLACES via ACS overlay"** — CDC PLACES doesn't disaggregate by race. Cross-reference with Census ACS demographic data by county to compute race-weighted health outcome estimates.

```bash
gh issue create --title "..." --body "..." --label "enhancement"
```

---

## Environment Variables Reference

| Variable | Required | Default | Used By |
|----------|----------|---------|---------|
| `CDC_PLACES_YEAR` | No | `2023` | cdc_places_health |
| `EPA_EJSCREEN_YEAR` | No | `2024` | epa_ejscreen |
| `FBI_API_KEY` | Yes (for FBI) | — | fbi_ucr_crime |
| `BLS_API_KEY` | No | — | bls_labor_stats |
| `POSTGRES_HOST` | Yes | `localhost` | All assets |
| `POSTGRES_PORT` | Yes | `5432` | All assets |
| `POSTGRES_USER` | Yes | `postgres` | All assets |
| `POSTGRES_PASSWORD` | Yes | `postgres` | All assets |
| `POSTGRES_DB` | Yes | `postgres` | All assets |
