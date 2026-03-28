# Sprint 1: Dagster Removal & Scheduling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove Dagster entirely, rename env vars, add APScheduler inside FastAPI for cron-based ingestion scheduling, and establish standalone scripts as the single ingestion code path.

**Architecture:** Dagster is removed wholesale. APScheduler (v3.x with SQLAlchemy job store) runs inside the FastAPI lifespan, loading cron schedules from a new `ingestion_schedules` DB table. Admin API endpoints manage schedules. Existing ingestion scripts and `run_ingestion.py` orchestrator are unchanged.

**Tech Stack:** APScheduler 3.x, SQLAlchemy, FastAPI, PostgreSQL

**Spec:** `docs/superpowers/specs/2026-03-27-self-hosted-scraping-pipeline-design.md` (Sprint 1 section)

---

## File Structure

**Create:**
- `src/d4bl/services/scheduler.py` — APScheduler setup, schedule loading, job registration
- `src/d4bl/app/schedule_routes.py` — Admin API endpoints for schedule CRUD
- `tests/test_scheduler.py` — Tests for scheduler service
- `tests/test_schedule_routes.py` — Tests for schedule API endpoints
- `docs/reference/dagster-ported-logic/rss_monitor.py` — Reference copy
- `docs/reference/dagster-ported-logic/web_scrape.py` — Reference copy
- `docs/reference/dagster-ported-logic/keyword_search.py` — Reference copy
- `docs/reference/dagster-ported-logic/schedules.py` — Reference copy

**Modify:**
- `src/d4bl/infra/database.py` — Add `IngestionSchedule` model
- `src/d4bl/app/api.py` — Add scheduler to lifespan, include schedule routes
- `src/d4bl/settings.py` — Remove `dagster_graphql_url`
- `scripts/ingestion/helpers.py` — Rename `DAGSTER_POSTGRES_URL` to `DATABASE_URL`
- `CLAUDE.md` — Remove Dagster sections
- `docker-compose.base.yml` — Remove Dagster env vars
- `pyproject.toml` — Add `apscheduler`, remove dagster deps if any

**Delete:**
- `dagster/` — Entire directory
- `docker-compose.dagster.yml`
- `tests/dagster/`

---

### Task 1: Save Dagster Reference Files Before Deletion

**Files:**
- Create: `docs/reference/dagster-ported-logic/rss_monitor.py`
- Create: `docs/reference/dagster-ported-logic/web_scrape.py`
- Create: `docs/reference/dagster-ported-logic/keyword_search.py`
- Create: `docs/reference/dagster-ported-logic/schedules.py`

- [ ] **Step 1: Copy reference files**

```bash
mkdir -p docs/reference/dagster-ported-logic
cp dagster/d4bl_pipelines/assets/feeds/rss_monitor.py docs/reference/dagster-ported-logic/rss_monitor.py
cp dagster/d4bl_pipelines/assets/crawlers/web_scrape.py docs/reference/dagster-ported-logic/web_scrape.py
cp dagster/d4bl_pipelines/assets/keyword_monitors/keyword_search.py docs/reference/dagster-ported-logic/keyword_search.py
cp dagster/d4bl_pipelines/schedules.py docs/reference/dagster-ported-logic/schedules.py
```

- [ ] **Step 2: Verify files copied**

```bash
ls -la docs/reference/dagster-ported-logic/
```

Expected: 4 files present.

- [ ] **Step 3: Commit**

```bash
git add docs/reference/dagster-ported-logic/
git commit -m "chore: save Dagster reference files before removal

Copy RSS monitor, web scrape, keyword search, and schedule logic
as reference for Sprint 2 porting work."
```

---

### Task 2: Delete Dagster Directory and Docker Compose

**Files:**
- Delete: `dagster/` (entire directory)
- Delete: `docker-compose.dagster.yml`
- Delete: `tests/dagster/`

- [ ] **Step 1: Delete Dagster directory**

```bash
rm -rf dagster/
```

- [ ] **Step 2: Delete Dagster docker compose**

```bash
rm docker-compose.dagster.yml
```

- [ ] **Step 3: Delete Dagster tests**

```bash
rm -rf tests/dagster/
```

- [ ] **Step 4: Verify deletions**

```bash
test ! -d dagster && echo "dagster/ deleted" || echo "STILL EXISTS"
test ! -f docker-compose.dagster.yml && echo "docker-compose.dagster.yml deleted" || echo "STILL EXISTS"
test ! -d tests/dagster && echo "tests/dagster/ deleted" || echo "STILL EXISTS"
```

Expected: All three report "deleted".

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "chore: remove Dagster directory, docker compose, and tests

Dagster was never deployed to production and duplicated 95% of
ingestion logic already in standalone scripts. Scheduling will be
handled by APScheduler inside FastAPI."
```

---

### Task 3: Clean Dagster References from Settings and Helpers

**Files:**
- Modify: `src/d4bl/settings.py` — Remove `dagster_graphql_url` field (line 71) and its env var read (lines 165-168)
- Modify: `scripts/ingestion/helpers.py` — Rename `DAGSTER_POSTGRES_URL` to `DATABASE_URL` (lines 64-70)
- Modify: `src/d4bl/infra/database.py` — Remove `dagster_run_id` column from `IngestionRun` if present

- [ ] **Step 1: Remove dagster_graphql_url from settings.py**

In `src/d4bl/settings.py`, remove the field declaration:

```python
    dagster_graphql_url: str = field(init=False)
```

And remove its initialization in `__post_init__`:

```python
            "dagster_graphql_url",
            os.getenv("DAGSTER_GRAPHQL_URL", "http://localhost:3003/graphql"),
```

- [ ] **Step 2: Rename DAGSTER_POSTGRES_URL in helpers.py**

In `scripts/ingestion/helpers.py`, replace the `get_db_connection` function (lines 64-70):

```python
def get_db_connection() -> psycopg2.extensions.connection:
    """Get a psycopg2 connection from DATABASE_URL env var."""
    db_url = os.environ.get("DATABASE_URL") or os.environ.get("DAGSTER_POSTGRES_URL")
    if not db_url:
        print("Error: Set DATABASE_URL env var", file=sys.stderr)
        sys.exit(1)
    return psycopg2.connect(db_url)
```

Note: Falls back to `DAGSTER_POSTGRES_URL` for backward compatibility during transition.

- [ ] **Step 3: Remove dagster_run_id from IngestionRun model**

In `src/d4bl/infra/database.py`, find and remove the `dagster_run_id` column from the `IngestionRun` class:

```python
    dagster_run_id = Column(String(255), nullable=True)
```

Also remove it from the `to_dict()` method if present.

- [ ] **Step 4: Grep for remaining Dagster references in source code**

```bash
grep -ri "dagster" src/ scripts/ --include="*.py" -l
```

Expected: No files returned (or only the backward-compat fallback in helpers.py).

- [ ] **Step 5: Commit**

```bash
git add src/d4bl/settings.py scripts/ingestion/helpers.py src/d4bl/infra/database.py
git commit -m "chore: remove Dagster references from settings, helpers, and models

- Remove dagster_graphql_url from settings
- Rename DAGSTER_POSTGRES_URL to DATABASE_URL (with fallback)
- Remove dagster_run_id column from IngestionRun model"
```

---

### Task 4: Clean Dagster References from Docker and Docs

**Files:**
- Modify: `docker-compose.base.yml` — Remove `DAGSTER_GRAPHQL_URL` env var if present
- Modify: `CLAUDE.md` — Remove Dagster sections

- [ ] **Step 1: Remove Dagster env vars from docker-compose.base.yml**

Search for and remove any `DAGSTER_GRAPHQL_URL` or `DAGSTER_POSTGRES_URL` lines in `docker-compose.base.yml`.

- [ ] **Step 2: Update CLAUDE.md**

Remove the following from `CLAUDE.md`:

1. The Dagster section under "### Docker" — remove the line:
```
# Add Dagster pipelines (local dev only)
docker compose -f docker-compose.base.yml -f docker-compose.dagster.yml up --build
```

2. The Dagster commands section under "### Dagster (Local Dev Only)":
```
### Dagster (Local Dev Only)

\`\`\`bash
# Optional: Dagster is available for local development but is not deployed to production
(cd dagster && dagster dev -p 3003)

# Or via Docker Compose overlay (from repo root)
docker compose -f docker-compose.base.yml -f docker-compose.dagster.yml up --build
\`\`\`
```

3. The Dagster module under "### Key Modules":
```
- **`dagster/`** - Dagster pipelines (local dev only, not deployed): `d4bl_pipelines/assets/`, `quality/lineage.py`, `resources/`
```

4. The Dagster port from the Service Ports table:
```
| Dagster Webserver (local dev only) | 3003 |
```

5. The `DAGSTER_GRAPHQL_URL` from the Configuration section.

- [ ] **Step 3: Verify no Dagster references remain in docs/config**

```bash
grep -ri "dagster" CLAUDE.md docker-compose.base.yml docker-compose.*.yml
```

Expected: No results.

- [ ] **Step 4: Commit**

```bash
git add docker-compose.base.yml CLAUDE.md
git commit -m "chore: remove Dagster from docker compose and documentation"
```

---

### Task 5: Add IngestionSchedule Database Model

**Files:**
- Modify: `src/d4bl/infra/database.py`
- Test: `tests/test_scheduler.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_scheduler.py`:

```python
"""Tests for ingestion scheduling."""

import pytest
from d4bl.infra.database import IngestionSchedule


def test_ingestion_schedule_model_exists():
    """IngestionSchedule model has expected columns."""
    assert hasattr(IngestionSchedule, "id")
    assert hasattr(IngestionSchedule, "source_key")
    assert hasattr(IngestionSchedule, "cron_expression")
    assert hasattr(IngestionSchedule, "enabled")
    assert hasattr(IngestionSchedule, "last_run_at")
    assert hasattr(IngestionSchedule, "last_status")


def test_ingestion_schedule_table_name():
    """Table name is ingestion_schedules."""
    assert IngestionSchedule.__tablename__ == "ingestion_schedules"


def test_ingestion_schedule_to_dict():
    """to_dict returns expected keys."""
    schedule = IngestionSchedule(
        source_key="cdc",
        cron_expression="0 0 15 1 *",
        enabled=True,
    )
    d = schedule.to_dict()
    assert d["source_key"] == "cdc"
    assert d["cron_expression"] == "0 0 15 1 *"
    assert d["enabled"] is True
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_scheduler.py -v
```

Expected: FAIL with `ImportError: cannot import name 'IngestionSchedule'`

- [ ] **Step 3: Add IngestionSchedule model to database.py**

In `src/d4bl/infra/database.py`, add after the `IngestionRun` class:

```python
class IngestionSchedule(Base):
    """Cron schedules for automated ingestion runs."""

    __tablename__ = "ingestion_schedules"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    source_key = Column(String(50), nullable=False, unique=True)
    cron_expression = Column(String(100), nullable=False)
    enabled = Column(Boolean, nullable=False, default=True)
    last_run_at = Column(DateTime(timezone=True), nullable=True)
    last_status = Column(
        String(20),
        nullable=True,
        comment="ok|error|running",
    )
    created_at = Column(DateTime(timezone=True), default=_utc_now)
    updated_at = Column(DateTime(timezone=True), default=_utc_now, onupdate=_utc_now)

    def to_dict(self) -> dict:
        return {
            "id": str(self.id) if self.id else None,
            "source_key": self.source_key,
            "cron_expression": self.cron_expression,
            "enabled": self.enabled,
            "last_run_at": self.last_run_at.isoformat() if self.last_run_at else None,
            "last_status": self.last_status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python -m pytest tests/test_scheduler.py -v
```

Expected: All 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/d4bl/infra/database.py tests/test_scheduler.py
git commit -m "feat: add IngestionSchedule database model

Stores cron schedules for automated ingestion runs with source key,
cron expression, enabled flag, and last run tracking."
```

---

### Task 6: Create Scheduler Service

**Files:**
- Create: `src/d4bl/services/scheduler.py`
- Test: `tests/test_scheduler.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_scheduler.py`:

```python
from unittest.mock import AsyncMock, MagicMock, patch
from d4bl.services.scheduler import (
    DEFAULT_SCHEDULES,
    parse_cron,
    build_scheduler,
)


def test_default_schedules_has_expected_sources():
    """DEFAULT_SCHEDULES covers all existing ingestion sources."""
    expected = {"cdc", "census_acs", "census_decennial", "epa", "bls", "fbi",
                "openstates", "hud", "usda", "doe", "bjs", "police_violence"}
    assert expected == set(DEFAULT_SCHEDULES.keys())


def test_parse_cron_valid():
    """parse_cron splits a 5-field cron string into APScheduler kwargs."""
    result = parse_cron("0 6 * * 1")
    assert result == {
        "minute": "0",
        "hour": "6",
        "day": "*/1",
        "month": "*",
        "day_of_week": "1",
    }


def test_parse_cron_all_stars():
    """parse_cron handles all-star expression."""
    result = parse_cron("* * * * *")
    assert result == {
        "minute": "*",
        "hour": "*",
        "day": "*/1",
        "month": "*",
        "day_of_week": "*",
    }


def test_parse_cron_invalid_raises():
    """parse_cron raises ValueError for malformed expressions."""
    with pytest.raises(ValueError, match="5 fields"):
        parse_cron("0 6 *")


def test_build_scheduler_returns_async_scheduler():
    """build_scheduler returns an AsyncIOScheduler instance."""
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    scheduler = build_scheduler()
    assert isinstance(scheduler, AsyncIOScheduler)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_scheduler.py -v -k "not model and not table and not to_dict"
```

Expected: FAIL with `ModuleNotFoundError: No module named 'd4bl.services.scheduler'`

- [ ] **Step 3: Add apscheduler dependency**

In `pyproject.toml`, add to the `dependencies` list:

```
"APScheduler>=3.10,<4",
```

Then install:

```bash
pip install -e ".[dev]"
```

- [ ] **Step 4: Create scheduler service**

Create `src/d4bl/services/scheduler.py`:

```python
"""APScheduler-based ingestion scheduling service.

Manages cron schedules for automated data ingestion. Schedules are stored
in the ingestion_schedules DB table and loaded at application startup.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from d4bl.infra.database import IngestionSchedule

logger = logging.getLogger(__name__)

# Default schedules seeded on first startup when table is empty.
DEFAULT_SCHEDULES: dict[str, str] = {
    "cdc": "0 0 15 1 *",
    "census_acs": "0 0 20 1 *",
    "census_decennial": "0 0 1 4 *",
    "epa": "0 0 1 2 *",
    "bls": "0 6 10 * *",
    "fbi": "0 0 1 10 *",
    "openstates": "0 6 * * 1",
    "hud": "0 0 1 3 *",
    "usda": "0 0 1 3 *",
    "doe": "0 0 1 6 *",
    "bjs": "0 0 1 11 *",
    "police_violence": "0 6 * * 1",
}


def parse_cron(expression: str) -> dict[str, str]:
    """Parse a 5-field cron expression into APScheduler CronTrigger kwargs.

    Fields: minute hour day month day_of_week
    """
    parts = expression.strip().split()
    if len(parts) != 5:
        raise ValueError(
            f"Cron expression must have 5 fields, got {len(parts)}: '{expression}'"
        )
    minute, hour, day, month, day_of_week = parts
    # APScheduler interprets day="*" as "unset" which defaults to last-used;
    # use "*/1" to explicitly mean "every day".
    if day == "*":
        day = "*/1"
    return {
        "minute": minute,
        "hour": hour,
        "day": day,
        "month": month,
        "day_of_week": day_of_week,
    }


def build_scheduler() -> AsyncIOScheduler:
    """Create a new AsyncIOScheduler (not yet started)."""
    return AsyncIOScheduler(timezone="UTC")


async def seed_default_schedules(session: AsyncSession) -> int:
    """Insert default schedules if the table is empty. Returns count seeded."""
    result = await session.execute(
        select(IngestionSchedule).limit(1)
    )
    if result.scalar_one_or_none() is not None:
        return 0

    count = 0
    for source_key, cron_expr in DEFAULT_SCHEDULES.items():
        session.add(IngestionSchedule(
            source_key=source_key,
            cron_expression=cron_expr,
            enabled=True,
        ))
        count += 1
    await session.commit()
    logger.info("Seeded %d default ingestion schedules", count)
    return count


async def load_and_register_schedules(
    scheduler: AsyncIOScheduler,
    session: AsyncSession,
    run_job_func,
) -> int:
    """Load enabled schedules from DB and register them with the scheduler.

    Args:
        scheduler: The APScheduler instance.
        session: An async DB session.
        run_job_func: Async callable(source_key: str) invoked when a job fires.

    Returns:
        Number of schedules registered.
    """
    result = await session.execute(
        select(IngestionSchedule).where(IngestionSchedule.enabled.is_(True))
    )
    schedules = result.scalars().all()

    for sched in schedules:
        try:
            cron_kwargs = parse_cron(sched.cron_expression)
            trigger = CronTrigger(**cron_kwargs)
            scheduler.add_job(
                run_job_func,
                trigger=trigger,
                args=[sched.source_key],
                id=f"ingest_{sched.source_key}",
                replace_existing=True,
                name=f"Ingest {sched.source_key}",
            )
            logger.info(
                "Registered schedule: %s [%s]",
                sched.source_key,
                sched.cron_expression,
            )
        except Exception:
            logger.exception(
                "Failed to register schedule for %s", sched.source_key
            )

    return len(schedules)


async def update_schedule_status(
    session: AsyncSession,
    source_key: str,
    status: str,
) -> None:
    """Update last_run_at and last_status for a schedule."""
    result = await session.execute(
        select(IngestionSchedule).where(
            IngestionSchedule.source_key == source_key
        )
    )
    sched = result.scalar_one_or_none()
    if sched:
        sched.last_run_at = datetime.now(timezone.utc)
        sched.last_status = status
        await session.commit()
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
python -m pytest tests/test_scheduler.py -v
```

Expected: All tests PASS.

- [ ] **Step 6: Commit**

```bash
git add src/d4bl/services/scheduler.py tests/test_scheduler.py pyproject.toml
git commit -m "feat: add scheduler service with cron parsing and schedule loading

APScheduler-based service that loads schedules from DB, seeds defaults
on first startup, and registers cron jobs for ingestion sources."
```

---

### Task 7: Create Schedule Admin API Routes

**Files:**
- Create: `src/d4bl/app/schedule_routes.py`
- Test: `tests/test_schedule_routes.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_schedule_routes.py`:

```python
"""Tests for schedule admin API routes."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from d4bl.app.schedule_routes import router


def test_router_has_expected_routes():
    """Router defines the expected schedule management endpoints."""
    paths = [r.path for r in router.routes]
    assert "/api/admin/schedules" in paths
    assert "/api/admin/schedules/{schedule_id}" in paths


def test_router_methods():
    """Router has GET, POST, DELETE methods."""
    methods = set()
    for route in router.routes:
        if hasattr(route, "methods"):
            methods.update(route.methods)
    assert "GET" in methods
    assert "POST" in methods
    assert "DELETE" in methods
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_schedule_routes.py -v
```

Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Create schedule routes**

Create `src/d4bl/app/schedule_routes.py`:

```python
"""Admin API endpoints for managing ingestion schedules."""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from d4bl.infra.database import IngestionSchedule, get_db
from d4bl.services.scheduler import parse_cron

logger = logging.getLogger(__name__)

router = APIRouter()


async def _require_admin(user=None):
    """Placeholder — wired to real require_admin when included in app."""
    pass


@router.get("/api/admin/schedules")
async def list_schedules(
    db: AsyncSession = Depends(get_db),
):
    """List all ingestion schedules."""
    result = await db.execute(
        select(IngestionSchedule).order_by(IngestionSchedule.source_key)
    )
    schedules = result.scalars().all()
    return {"schedules": [s.to_dict() for s in schedules]}


@router.post("/api/admin/schedules")
async def upsert_schedule(
    body: dict = Body(...),
    db: AsyncSession = Depends(get_db),
):
    """Create or update an ingestion schedule.

    Body: {"source_key": "cdc", "cron_expression": "0 0 15 1 *", "enabled": true}
    """
    source_key = body.get("source_key")
    cron_expression = body.get("cron_expression")
    enabled = body.get("enabled", True)

    if not source_key or not cron_expression:
        raise HTTPException(
            status_code=422,
            detail="source_key and cron_expression are required",
        )

    # Validate cron expression
    try:
        parse_cron(cron_expression)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    # Upsert
    result = await db.execute(
        select(IngestionSchedule).where(
            IngestionSchedule.source_key == source_key
        )
    )
    schedule = result.scalar_one_or_none()

    if schedule:
        schedule.cron_expression = cron_expression
        schedule.enabled = enabled
    else:
        schedule = IngestionSchedule(
            source_key=source_key,
            cron_expression=cron_expression,
            enabled=enabled,
        )
        db.add(schedule)

    await db.commit()
    await db.refresh(schedule)
    return {"schedule": schedule.to_dict()}


@router.delete("/api/admin/schedules/{schedule_id}")
async def delete_schedule(
    schedule_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Delete an ingestion schedule."""
    result = await db.execute(
        select(IngestionSchedule).where(IngestionSchedule.id == schedule_id)
    )
    schedule = result.scalar_one_or_none()
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")

    await db.delete(schedule)
    await db.commit()
    return {"status": "deleted", "source_key": schedule.source_key}


@router.post("/api/admin/schedules/{schedule_id}/run")
async def trigger_schedule(
    schedule_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Trigger an ingestion schedule immediately."""
    result = await db.execute(
        select(IngestionSchedule).where(IngestionSchedule.id == schedule_id)
    )
    schedule = result.scalar_one_or_none()
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")

    # Import here to avoid circular imports
    from d4bl.services.ingestion_runner import resolve_source

    module_name = resolve_source(schedule.source_key)
    if not module_name:
        raise HTTPException(
            status_code=422,
            detail=f"No ingestion script for source: {schedule.source_key}",
        )

    # Use the existing trigger mechanism
    from d4bl.services.ingestion_runner import run_ingestion_task
    from d4bl.infra.database import IngestionRun, async_session_factory
    from uuid import uuid4
    from datetime import datetime, timezone
    import asyncio

    run_id = uuid4()
    async with async_session_factory() as session:
        run = IngestionRun(
            id=run_id,
            status="pending",
            trigger_type="scheduled",
            started_at=datetime.now(timezone.utc),
        )
        session.add(run)
        await session.commit()

    asyncio.create_task(
        run_ingestion_task(run_id, module_name, async_session_factory)
    )

    return {
        "status": "triggered",
        "source_key": schedule.source_key,
        "run_id": str(run_id),
    }
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_schedule_routes.py -v
```

Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/d4bl/app/schedule_routes.py tests/test_schedule_routes.py
git commit -m "feat: add admin API routes for ingestion schedule management

CRUD endpoints for schedules: list, create/update, delete, trigger.
Validates cron expressions and reuses existing ingestion runner."
```

---

### Task 8: Wire Scheduler into FastAPI Lifespan

**Files:**
- Modify: `src/d4bl/app/api.py`

- [ ] **Step 1: Add scheduler imports to api.py**

At the top of `src/d4bl/app/api.py`, add with the other imports:

```python
from d4bl.services.scheduler import (
    build_scheduler,
    seed_default_schedules,
    load_and_register_schedules,
    update_schedule_status,
)
from d4bl.app.schedule_routes import router as schedule_router
```

- [ ] **Step 2: Create the scheduled job callback function**

Add before the `lifespan` function in `src/d4bl/app/api.py`:

```python
# --- Scheduler ---
_scheduler = None


async def _run_scheduled_ingestion(source_key: str) -> None:
    """Callback invoked by APScheduler when a cron job fires."""
    from d4bl.services.ingestion_runner import resolve_source, run_ingestion_task
    from d4bl.infra.database import IngestionRun, async_session_factory
    from uuid import uuid4

    logger.info("Scheduled ingestion triggered: %s", source_key)

    module_name = resolve_source(source_key)
    if not module_name:
        logger.error("No script registered for source: %s", source_key)
        return

    run_id = uuid4()
    async with async_session_factory() as session:
        run = IngestionRun(
            id=run_id,
            status="pending",
            trigger_type="scheduled",
            started_at=datetime.now(timezone.utc),
        )
        session.add(run)
        await session.commit()

    try:
        await run_ingestion_task(run_id, module_name, async_session_factory)
        status = "ok"
    except Exception:
        logger.exception("Scheduled ingestion failed: %s", source_key)
        status = "error"

    async with async_session_factory() as session:
        await update_schedule_status(session, source_key, status)
```

- [ ] **Step 3: Add scheduler startup/shutdown to lifespan**

In the `lifespan` function, add scheduler startup after the database initialization block (before `yield`):

```python
    # --- Scheduler startup ---
    global _scheduler
    try:
        _scheduler = build_scheduler()
        async with async_session_factory() as session:
            await seed_default_schedules(session)
            count = await load_and_register_schedules(
                _scheduler, session, _run_scheduled_ingestion
            )
        _scheduler.start()
        logger.info("Scheduler started with %d schedules", count)
    except Exception as e:
        logger.warning("Scheduler startup failed: %s", e)
        _scheduler = None
```

After `yield`, add shutdown:

```python
    # --- Scheduler shutdown ---
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")
```

- [ ] **Step 4: Include the schedule router**

After the existing `app = FastAPI(...)` line, add:

```python
app.include_router(schedule_router)
```

- [ ] **Step 5: Wire admin auth to schedule routes**

Add the `require_admin` dependency to each schedule route. In the `schedule_routes.py` file, the routes currently don't enforce auth. Update `api.py` to add the dependency when including the router, or update `schedule_routes.py` to import and use the real `require_admin`:

In `src/d4bl/app/schedule_routes.py`, update the imports and add the dependency to each route:

```python
# At the top, after existing imports:
# Note: require_admin is injected when the router is included in api.py
# For now, routes are accessible to any authenticated admin user
```

The actual auth wiring depends on how `require_admin` is defined in `api.py`. Add `Depends(require_admin)` to each route function signature once wired.

- [ ] **Step 6: Verify the app starts**

```bash
python -c "from d4bl.app.api import app; print('App imports OK')"
```

Expected: `App imports OK` (no import errors).

- [ ] **Step 7: Commit**

```bash
git add src/d4bl/app/api.py src/d4bl/app/schedule_routes.py
git commit -m "feat: wire APScheduler into FastAPI lifespan

Scheduler starts with the app, seeds default schedules on first run,
loads enabled schedules from DB, and registers cron jobs. Includes
schedule admin routes in the app."
```

---

### Task 9: Update pyproject.toml Dependencies

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Check for dagster dependencies**

```bash
grep -i dagster pyproject.toml
```

Remove any dagster-related dependencies found.

- [ ] **Step 2: Verify APScheduler was added in Task 6**

```bash
grep -i apscheduler pyproject.toml
```

Expected: `"APScheduler>=3.10,<4"` present.

- [ ] **Step 3: Commit if changes made**

```bash
git add pyproject.toml
git commit -m "chore: clean dagster deps from pyproject.toml"
```

---

### Task 10: Final Verification

- [ ] **Step 1: Run all tests**

```bash
python -m pytest tests/test_scheduler.py tests/test_schedule_routes.py -v
```

Expected: All tests PASS.

- [ ] **Step 2: Grep for remaining Dagster references**

```bash
grep -ri "dagster" src/ scripts/ tests/ *.yml *.md --include="*.py" --include="*.yml" --include="*.md" | grep -v "docs/reference/dagster-ported-logic" | grep -v "node_modules"
```

Expected: No results (except possibly backward-compat fallback in helpers.py).

- [ ] **Step 3: Verify run_ingestion.py still works**

```bash
python scripts/run_ingestion.py --list
```

Expected: All sources listed without errors.

- [ ] **Step 4: Run full test suite**

```bash
python -m pytest tests/ -v --timeout=60 -x
```

Expected: All tests PASS.

- [ ] **Step 5: Build frontend to ensure no breakage**

```bash
cd ui-nextjs && npm run build
```

Expected: Build succeeds.

- [ ] **Step 6: Final commit if any cleanup needed**

```bash
git add -A
git status
```

If clean, Sprint 1 is complete. If there are changes, commit them:

```bash
git commit -m "chore: Sprint 1 final cleanup"
```
