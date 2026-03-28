# Ingestion Trigger Rewire Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Dagster-based ingestion trigger with direct in-process script execution so the existing `/data/` UI works without Dagster.

**Architecture:** The API trigger endpoint will create a pending `IngestionRun` row, then fire an `asyncio.create_task` that runs the ingestion script via `asyncio.to_thread` (since scripts are synchronous). The background task manages its own DB session and updates the run row on completion/failure. A shared `SCRIPT_REGISTRY` dict maps source slugs to script module names.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy async, asyncio, importlib

**Spec:** `docs/superpowers/specs/2026-03-15-ingestion-trigger-rewire-design.md`

---

## File Structure

| Action | File | Responsibility |
|--------|------|---------------|
| Create | `src/d4bl/services/ingestion_runner.py` | Script registry, resolve_source, async background task |
| Create | `tests/test_ingestion_runner.py` | Unit tests for the runner |
| Modify | `src/d4bl/app/data_routes.py` | Rewire trigger, rewrite status, remove Dagster endpoints |
| Modify | `src/d4bl/app/schemas.py` | Update TriggerResponse, RunStatusResponse; delete ReloadResponse |
| Modify | `ui-nextjs/app/data/sources/[id]/page.tsx` | Update trigger result display to use `ingestion_run_id` |
| Modify | `scripts/run_ingestion.py` | Import from shared registry |
| Modify | `tests/test_e2e_ingestion.py:183-221` | Rewrite trigger test to mock new imports |
| Delete | `src/d4bl/services/dagster_client.py` | No longer needed |
| Delete | `tests/test_dagster_client.py` | Tests for removed module |

---

## Chunk 1: Ingestion Runner Service

### Task 1: Create `ingestion_runner.py` with registry and resolve_source

**Files:**
- Create: `src/d4bl/services/ingestion_runner.py`
- Test: `tests/test_ingestion_runner.py`

- [ ] **Step 1: Write the failing test for resolve_source**

```python
# tests/test_ingestion_runner.py
"""Tests for the ingestion runner service."""

import pytest

from d4bl.services.ingestion_runner import SCRIPT_REGISTRY, resolve_source


class TestScriptRegistry:
    def test_registry_has_all_sources_with_aliases(self):
        # 13 canonical sources + 12 aliases = 25 entries
        assert len(SCRIPT_REGISTRY) == 25
        # All values should be valid module names
        modules = set(SCRIPT_REGISTRY.values())
        assert len(modules) == 13

    def test_registry_contains_key_sources(self):
        assert "cdc" in SCRIPT_REGISTRY
        assert "census" in SCRIPT_REGISTRY
        assert "epa" in SCRIPT_REGISTRY
        assert "bjs" in SCRIPT_REGISTRY

    def test_registry_aliases_resolve_same_module(self):
        assert SCRIPT_REGISTRY["census"] == SCRIPT_REGISTRY["census_acs"]
        assert SCRIPT_REGISTRY["cdc"] == SCRIPT_REGISTRY["cdc_places"]


class TestResolveSource:
    def test_exact_match(self):
        assert resolve_source("cdc") == "ingest_cdc_places"

    def test_slugified_match(self):
        assert resolve_source("CDC") == "ingest_cdc_places"
        assert resolve_source("Census ACS") == "ingest_census_acs"

    def test_unknown_source(self):
        assert resolve_source("nonexistent") is None

    def test_empty_string(self):
        assert resolve_source("") is None

    def test_special_characters_stripped(self):
        assert resolve_source("CDC!@#") == "ingest_cdc_places"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_ingestion_runner.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'd4bl.services.ingestion_runner'`

- [ ] **Step 3: Write the ingestion_runner module with registry and resolve_source**

```python
# src/d4bl/services/ingestion_runner.py
"""Ingestion runner — executes ingestion scripts as async background tasks.

Replaces the Dagster-based trigger with direct in-process script execution.
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Script registry — single source of truth for source slug → module mapping.
# The module names correspond to files under scripts/ingestion/.
# ---------------------------------------------------------------------------

SCRIPT_REGISTRY: dict[str, str] = {
    "cdc": "ingest_cdc_places",
    "cdc_places": "ingest_cdc_places",
    "cdc_mortality": "ingest_cdc_mortality",
    "census": "ingest_census_acs",
    "census_acs": "ingest_census_acs",
    "census_decennial": "ingest_census_demographics",
    "census_demographics": "ingest_census_demographics",
    "epa": "ingest_epa_ejscreen",
    "epa_ejscreen": "ingest_epa_ejscreen",
    "fbi": "ingest_fbi_ucr",
    "fbi_ucr": "ingest_fbi_ucr",
    "bls": "ingest_bls_labor",
    "bls_labor": "ingest_bls_labor",
    "hud": "ingest_hud_housing",
    "hud_housing": "ingest_hud_housing",
    "usda": "ingest_usda_food",
    "usda_food": "ingest_usda_food",
    "doe": "ingest_doe_education",
    "doe_education": "ingest_doe_education",
    "police": "ingest_police_violence",
    "police_violence": "ingest_police_violence",
    "openstates": "ingest_openstates",
    "bjs": "ingest_bjs_incarceration",
    "bjs_incarceration": "ingest_bjs_incarceration",
}


def slugify(name: str) -> str:
    """Convert a source name to a registry-compatible slug."""
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "_", slug)
    return slug.strip("_")


def resolve_source(name: str) -> str | None:
    """Look up a DataSource name in the registry, returning the module name or None."""
    if not name:
        return None
    slug = slugify(name)
    return SCRIPT_REGISTRY.get(slug)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_ingestion_runner.py -v`
Expected: All 10 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/d4bl/services/ingestion_runner.py tests/test_ingestion_runner.py
git commit -m "feat: add ingestion runner with script registry and resolve_source"
```

### Task 2: Add run_ingestion_task background function

**Files:**
- Modify: `src/d4bl/services/ingestion_runner.py`
- Test: `tests/test_ingestion_runner.py`

- [ ] **Step 1: Write the failing tests for run_ingestion_task**

Append to `tests/test_ingestion_runner.py`:

```python
import asyncio
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from d4bl.services.ingestion_runner import run_ingestion_task


def _make_mock_session_factory(run_row):
    """Create a mock async session factory that returns a session with the given run."""
    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = run_row
    session.execute = AsyncMock(return_value=result_mock)
    session.commit = AsyncMock()

    # Make session work as async context manager
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)

    factory = MagicMock(return_value=session)
    return factory, session


class TestRunIngestionTask:
    @pytest.mark.asyncio
    async def test_successful_run(self):
        """Script main() returns record count → run marked completed."""
        run = MagicMock()
        run.id = uuid.uuid4()
        run.status = "pending"
        run.records_ingested = None
        run.completed_at = None
        run.error_detail = None

        factory, session = _make_mock_session_factory(run)

        mock_module = MagicMock()
        mock_module.main.return_value = 42

        with patch(
            "d4bl.services.ingestion_runner._import_script",
            return_value=mock_module,
        ):
            await run_ingestion_task(run.id, "ingest_test", factory)

        assert run.status == "completed"
        assert run.records_ingested == 42
        assert run.completed_at is not None
        assert run.error_detail is None
        assert session.commit.await_count >= 2  # running + completed

    @pytest.mark.asyncio
    async def test_failed_run(self):
        """Script main() raises → run marked failed with error detail."""
        run = MagicMock()
        run.id = uuid.uuid4()
        run.status = "pending"
        run.records_ingested = None
        run.completed_at = None
        run.error_detail = None

        factory, session = _make_mock_session_factory(run)

        mock_module = MagicMock()
        mock_module.main.side_effect = RuntimeError("API timeout")

        with patch(
            "d4bl.services.ingestion_runner._import_script",
            return_value=mock_module,
        ):
            await run_ingestion_task(run.id, "ingest_test", factory)

        assert run.status == "failed"
        assert "API timeout" in run.error_detail
        assert run.completed_at is not None

    @pytest.mark.asyncio
    async def test_none_return_treated_as_zero(self):
        """Script main() returns None → records_ingested set to 0."""
        run = MagicMock()
        run.id = uuid.uuid4()
        run.status = "pending"
        run.records_ingested = None
        run.completed_at = None
        run.error_detail = None

        factory, session = _make_mock_session_factory(run)

        mock_module = MagicMock()
        mock_module.main.return_value = None

        with patch(
            "d4bl.services.ingestion_runner._import_script",
            return_value=mock_module,
        ):
            await run_ingestion_task(run.id, "ingest_test", factory)

        assert run.status == "completed"
        assert run.records_ingested == 0

    @pytest.mark.asyncio
    async def test_run_not_found_logs_and_returns(self):
        """If the IngestionRun row is not found, task exits gracefully."""
        factory, session = _make_mock_session_factory(None)  # no run found

        # Should not raise
        await run_ingestion_task(uuid.uuid4(), "ingest_test", factory)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_ingestion_runner.py::TestRunIngestionTask -v`
Expected: FAIL with `ImportError: cannot import name 'run_ingestion_task'`

- [ ] **Step 3: Implement run_ingestion_task**

Add to `src/d4bl/services/ingestion_runner.py`:

```python
import asyncio
import importlib
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from sqlalchemy import select

logger = logging.getLogger(__name__)

# Ensure scripts/ is on sys.path for `import ingestion.ingest_xxx`
_SCRIPTS_DIR = str(Path(__file__).resolve().parents[3] / "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)


def _import_script(module_name: str):
    """Import an ingestion script module by name."""
    return importlib.import_module(f"ingestion.{module_name}")


async def run_ingestion_task(
    run_id: UUID,
    module_name: str,
    session_factory,
) -> None:
    """Background task: run an ingestion script and update the IngestionRun row.

    Args:
        run_id: The IngestionRun.id to update.
        module_name: The script module name (e.g. "ingest_cdc_places").
        session_factory: Callable that returns an async session context manager
                         (typically ``async_session_maker`` from database.py).
    """
    from d4bl.infra.database import IngestionRun

    async with session_factory() as session:
        # Load the run row
        result = await session.execute(
            select(IngestionRun).where(IngestionRun.id == run_id)
        )
        run = result.scalar_one_or_none()
        if run is None:
            logger.error("IngestionRun %s not found, aborting task", run_id)
            return

        # Mark as running
        run.status = "running"
        await session.commit()

        try:
            module = _import_script(module_name)
            records = await asyncio.to_thread(module.main)
            run.status = "completed"
            run.records_ingested = records if records is not None else 0
        except Exception as exc:
            logger.exception(
                "Ingestion script %s failed for run %s", module_name, run_id
            )
            run.status = "failed"
            run.error_detail = str(exc)

        run.completed_at = datetime.now(timezone.utc)
        await session.commit()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_ingestion_runner.py -v`
Expected: All 14 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/d4bl/services/ingestion_runner.py tests/test_ingestion_runner.py
git commit -m "feat: add run_ingestion_task async background function"
```

---

## Chunk 2: Schema Updates and API Rewire

### Task 3: Update Pydantic schemas

**Files:**
- Modify: `src/d4bl/app/schemas.py:264-291`

- [ ] **Step 1: Update TriggerResponse — remove run_id, keep ingestion_run_id**

In `src/d4bl/app/schemas.py`, replace lines 264-291:

```python
# --- Ingestion trigger models ---


class TriggerResponse(BaseModel):
    """Returned when an ingestion run is triggered for a data source."""

    ingestion_run_id: str
    status: str  # "triggered"


class RunStatusResponse(BaseModel):
    """Status of the latest ingestion run for a source."""

    ingestion_run_id: str
    status: str
    started_at: str | None = None
    completed_at: str | None = None
    records_ingested: int | None = None
    error_detail: str | None = None
```

This removes `ReloadResponse` entirely, removes `run_id`/`dagster_run_id`/`dagster_status` from the models, and uses local DB fields instead.

- [ ] **Step 2: Verify schemas module imports cleanly**

Run: `python -c "from d4bl.app.schemas import TriggerResponse, RunStatusResponse; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add src/d4bl/app/schemas.py
git commit -m "refactor: remove Dagster fields from TriggerResponse and RunStatusResponse"
```

### Task 4: Rewire data_routes.py — trigger, status, cleanup

**Files:**
- Modify: `src/d4bl/app/data_routes.py`

- [ ] **Step 1: Update imports**

Replace lines 1-42 of `data_routes.py`. Key changes:
- Remove `DagsterClient`, `DagsterClientError` import (line 40)
- Remove `ReloadResponse` from schema imports (line 29)
- Remove `aiohttp` import (line 10, only used by connection test — check if still needed)
- Add `from d4bl.services.ingestion_runner import resolve_source, run_ingestion_task`
- Add `from d4bl.infra.database import async_session_maker`
- Add `import asyncio`

Updated import block:

```python
"""Data ingestion management endpoints — admin only."""

import asyncio
import logging
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath

import aiohttp
from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from d4bl.app.auth import CurrentUser, require_admin
from d4bl.app.schemas import (
    ConnectionTestResponse,
    DataOverviewResponse,
    DataSourceCreate,
    DataSourceResponse,
    DataSourceUpdate,
    IngestionRunResponse,
    KeywordMonitorCreate,
    KeywordMonitorResponse,
    KeywordMonitorUpdate,
    LineageGraphNode,
    LineageGraphResponse,
    LineageRecordResponse,
    RunStatusResponse,
    TriggerResponse,
)
from d4bl.infra.database import (
    DataLineage,
    DataSource,
    IngestionRun,
    KeywordMonitor,
    async_session_maker,
    get_db,
)
from d4bl.services.ingestion_runner import (
    slugify,
    resolve_source,
    run_ingestion_task,
)
```

Note: `slugify` is imported from `ingestion_runner` instead of duplicating it. It's still used by `get_lineage_graph` for `LineageGraphNode.asset_key`.

- [ ] **Step 2: Rewrite trigger_source endpoint (lines 334-384)**

Replace the entire Dagster integration section (lines 323-384) with:

```python
# ---------------------------------------------------------------------------
# Ingestion trigger
# ---------------------------------------------------------------------------


@router.post(
    "/sources/{source_id}/trigger",
    response_model=TriggerResponse,
    status_code=202,
)
async def trigger_source(
    source_id: uuid.UUID,
    user: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Trigger an ingestion run for a data source."""
    result = await db.execute(
        select(DataSource).where(DataSource.id == source_id)
    )
    source = result.scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    # Resolve the script module
    module_name = resolve_source(source.name)
    if not module_name:
        raise HTTPException(
            status_code=400,
            detail=f"No ingestion script registered for source '{source.name}'",
        )

    # Concurrency guard: reject if a run is already pending/running
    existing = await db.execute(
        select(IngestionRun).where(
            IngestionRun.data_source_id == source_id,
            IngestionRun.status.in_(["pending", "running"]),
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=409,
            detail="An ingestion run is already in progress for this source",
        )

    # Create pending run
    run = IngestionRun(
        data_source_id=source.id,
        status="pending",
        trigger_type="manual",
        triggered_by=user.id,
        started_at=datetime.now(timezone.utc),
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)

    # Fire background task
    asyncio.create_task(
        run_ingestion_task(run.id, module_name, async_session_maker)
    )

    return TriggerResponse(
        ingestion_run_id=str(run.id),
        status="triggered",
    )
```

- [ ] **Step 3: Rewrite source_run_status endpoint (lines 387-437)**

Replace with:

```python
@router.get(
    "/sources/{source_id}/status",
    response_model=RunStatusResponse,
)
async def source_run_status(
    source_id: uuid.UUID,
    user: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get the status of the latest ingestion run for a data source."""
    src_result = await db.execute(
        select(DataSource).where(DataSource.id == source_id)
    )
    if not src_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Source not found")

    last_run = await _last_run_for_source(db, source_id)
    if not last_run:
        raise HTTPException(
            status_code=404, detail="No runs found for this source"
        )

    return RunStatusResponse(
        ingestion_run_id=str(last_run.id),
        status=last_run.status,
        started_at=last_run.started_at.isoformat() if last_run.started_at else None,
        completed_at=last_run.completed_at.isoformat() if last_run.completed_at else None,
        records_ingested=last_run.records_ingested,
        error_detail=last_run.error_detail,
    )
```

- [ ] **Step 4: Remove reload_dagster endpoint (lines 440-452)**

Delete the entire `reload_dagster` function and its decorator.

- [ ] **Step 5: Update upload_file docstring (line 284)**

Change line 284 from:
```
    for later processing by the Dagster file_upload asset.
```
to:
```
    for later processing by the file upload ingestion pipeline.
```

- [ ] **Step 6: Verify module imports cleanly**

Run: `python -c "from d4bl.app.data_routes import router; print('OK')"`
Expected: `OK`

- [ ] **Step 7: Commit**

```bash
git add src/d4bl/app/data_routes.py
git commit -m "feat: rewire trigger endpoint to use direct script execution"
```

---

## Chunk 3: Frontend Fix, CLI Update, and Cleanup

### Task 5: Update frontend trigger result display

**Files:**
- Modify: `ui-nextjs/app/data/sources/[id]/page.tsx:89`

- [ ] **Step 1: Update trigger result to use ingestion_run_id**

The frontend at line 89 reads `data.run_id` from the trigger response. Since we removed `run_id` from `TriggerResponse`, update to use `ingestion_run_id`:

Change line 89 from:
```typescript
      setTriggerResult(`Run triggered: ${data.run_id}`);
```
to:
```typescript
      setTriggerResult(`Run triggered: ${data.ingestion_run_id}`);
```

- [ ] **Step 2: Commit**

```bash
git add ui-nextjs/app/data/sources/[id]/page.tsx
git commit -m "fix: update trigger result to use ingestion_run_id"
```

### Task 6: Update CLI runner to use shared registry

**Files:**
- Modify: `scripts/run_ingestion.py:25-39`

- [ ] **Step 1: Replace inline SOURCES dict with import from ingestion_runner**

Replace lines 19-39 of `scripts/run_ingestion.py`. The tricky part: `run_ingestion.py` lives in `scripts/` while `ingestion_runner.py` lives in `src/d4bl/services/`. We need to add `src/` to `sys.path`.

Replace lines 19-39 with:

```python
# Ensure the scripts/ directory is on sys.path so that
# `import ingestion.ingest_xxx` (with relative helpers) works.
_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

# Also ensure src/ is on sys.path so we can import the shared registry.
_SRC_DIR = os.path.join(os.path.dirname(_SCRIPTS_DIR), "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from d4bl.services.ingestion_runner import SCRIPT_REGISTRY  # noqa: E402

SOURCES = SCRIPT_REGISTRY
```

- [ ] **Step 2: Verify CLI still works**

Run: `python scripts/run_ingestion.py --list`
Expected: Prints all 13 sources (same as before)

- [ ] **Step 3: Commit**

```bash
git add scripts/run_ingestion.py
git commit -m "refactor: use shared SCRIPT_REGISTRY in CLI runner"
```

### Task 7: Rewrite e2e trigger test

**Files:**
- Modify: `tests/test_e2e_ingestion.py:183-221`

- [ ] **Step 1: Rewrite test_trigger_run to mock new imports**

The existing test mocks `DagsterClient`. Replace with mocking `resolve_source`, `run_ingestion_task`, and `async_session_maker`.

Replace the `test_trigger_run` method (lines 183-221) with:

```python
    @pytest.mark.asyncio
    async def test_trigger_run(self, e2e_app):
        """Step 2: Trigger an ingestion run for a data source."""
        app, mock_session = e2e_app
        source = _make_source()
        run = _make_run(status="pending")

        # First execute returns source, second returns no existing run
        source_result = MagicMock()
        source_result.scalar_one_or_none = MagicMock(return_value=source)
        no_run_result = MagicMock()
        no_run_result.scalar_one_or_none = MagicMock(return_value=None)
        mock_session.execute = AsyncMock(
            side_effect=[source_result, no_run_result]
        )
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()

        with patch(
            "d4bl.app.data_routes.resolve_source",
            return_value="ingest_census_acs",
        ), patch(
            "d4bl.app.data_routes.run_ingestion_task",
            new_callable=AsyncMock,
        ), patch(
            "d4bl.app.data_routes.IngestionRun",
            return_value=run,
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                resp = await client.post(
                    f"/api/data/sources/{SOURCE_ID}/trigger"
                )

        assert resp.status_code == 202
        body = resp.json()
        assert body["status"] == "triggered"
        assert "ingestion_run_id" in body
```

- [ ] **Step 2: Update _make_run helper to remove dagster_run_id default**

At line 73, change `run.dagster_run_id = "dagster-abc-123"` to `run.dagster_run_id = None` and update the corresponding `to_dict` return value at line 85.

- [ ] **Step 3: Run the e2e tests**

Run: `python -m pytest tests/test_e2e_ingestion.py -v`
Expected: All tests pass

- [ ] **Step 4: Commit**

```bash
git add tests/test_e2e_ingestion.py
git commit -m "test: rewrite e2e trigger test for direct script execution"
```

### Task 8: Delete Dagster client and its tests

**Files:**
- Delete: `src/d4bl/services/dagster_client.py`
- Delete: `tests/test_dagster_client.py`

- [ ] **Step 1: Delete the files**

```bash
git rm src/d4bl/services/dagster_client.py tests/test_dagster_client.py
```

- [ ] **Step 2: Verify no remaining Dagster references**

Run: `grep -ri "dagster" src/ tests/ --include="*.py" | grep -v "__pycache__" | grep -v "settings.py" | grep -v "dagster_run_id"`
Expected: No matches. Remaining `dagster` references are expected in `settings.py` (dead `dagster_graphql_url` field), `database.py` and `schemas.py` (dead `dagster_run_id` column) — all are out-of-scope cleanup.

- [ ] **Step 3: Commit**

```bash
git commit -m "chore: remove Dagster client and tests"
```

### Task 9: Run full test suite

- [ ] **Step 1: Run all tests**

Run: `python -m pytest tests/ -v --tb=short`
Expected: All tests pass. No imports of `dagster_client` remain.

- [ ] **Step 2: Verify the API starts**

Run: `python -c "from d4bl.app.api import app; print('FastAPI app loaded OK')"`
Expected: `OK`

- [ ] **Step 3: Final commit if any fixes were needed**

```bash
git add -A
git commit -m "fix: resolve any remaining test/import issues from Dagster removal"
```
