# Configure Cron Schedules for Data Source Refresh — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add static Dagster cron schedules for the 10 hardcoded API assets so they refresh at appropriate cadences.

**Architecture:** Add a `STATIC_SCHEDULES` dict and `build_static_schedules()` function in `schedules.py`. Wire the output into the `Definitions` object in `__init__.py`. Default status is `STOPPED` so users opt in via Dagster UI.

**Tech Stack:** Dagster (ScheduleDefinition, AssetSelection, DefaultScheduleStatus), pytest

**Closes:** #73

---

### Task 1: Write tests for `build_static_schedules`

**Files:**
- Modify: `dagster/tests/test_schedules.py`

**Step 1: Write the failing tests**

Add to the end of `dagster/tests/test_schedules.py`:

```python
# ---------------------------------------------------------------------------
# build_static_schedules
# ---------------------------------------------------------------------------

from d4bl_pipelines.schedules import build_static_schedules, STATIC_SCHEDULES


def test_build_static_schedules_returns_all_ten():
    schedules = build_static_schedules()
    assert len(schedules) == 10


def test_build_static_schedules_names_match_assets():
    schedules = build_static_schedules()
    names = {s.name for s in schedules}
    for asset_key in STATIC_SCHEDULES:
        assert f"refresh_{asset_key}" in names


def test_build_static_schedules_default_stopped():
    schedules = build_static_schedules()
    for sched in schedules:
        assert sched.default_status == DefaultScheduleStatus.STOPPED


def test_build_static_schedules_cron_strings_valid():
    schedules = build_static_schedules()
    for sched in schedules:
        parts = sched.cron_schedule.split()
        assert len(parts) == 5, f"Bad cron for {sched.name}: {sched.cron_schedule}"
```

**Step 2: Run tests to verify they fail**

Run: `cd dagster && python -m pytest tests/test_schedules.py -k "static" -v`
Expected: FAIL — `ImportError: cannot import name 'build_static_schedules'`

**Step 3: Commit**

```bash
git add dagster/tests/test_schedules.py
git commit -m "test: add tests for static API asset schedules (#73)"
```

---

### Task 2: Implement `STATIC_SCHEDULES` and `build_static_schedules`

**Files:**
- Modify: `dagster/d4bl_pipelines/schedules.py`

**Step 1: Add the dict and function**

Add after the existing imports and before `build_source_schedules`:

```python
STATIC_SCHEDULES: dict[str, str] = {
    "census_acs_indicators": "0 0 1 1 *",         # Annually — Jan 1
    "cdc_places_health": "0 0 1 */3 *",           # Quarterly — 1st of every 3rd month
    "bls_labor_stats": "0 0 1 * *",               # Monthly — 1st
    "fbi_ucr_crime": "0 0 1 1 *",                 # Annually — Jan 1
    "epa_ejscreen": "0 0 1 1 *",                  # Annually — Jan 1
    "hud_fair_housing": "0 0 1 1 *",              # Annually — Jan 1
    "usda_food_access": "0 0 1 1 *",              # Annually — Jan 1
    "doe_civil_rights": "0 0 1 1 *",              # Annually — Jan 1 (biennial n/a in cron)
    "mapping_police_violence": "0 0 1 * *",        # Monthly — 1st
    "openstates_bills": "0 6 * * 1-5",            # Weekdays — 6 AM
}


def build_static_schedules() -> list[ScheduleDefinition]:
    """Build schedules for the 10 hardcoded API assets."""
    return [
        ScheduleDefinition(
            name=f"refresh_{asset_key}",
            cron_schedule=cron,
            target=AssetSelection.assets(asset_key),
            default_status=DefaultScheduleStatus.STOPPED,
        )
        for asset_key, cron in STATIC_SCHEDULES.items()
    ]
```

**Step 2: Run tests to verify they pass**

Run: `cd dagster && python -m pytest tests/test_schedules.py -v`
Expected: ALL PASS

**Step 3: Commit**

```bash
git add dagster/d4bl_pipelines/schedules.py
git commit -m "feat: add static cron schedules for 10 API assets (#73)"
```

---

### Task 3: Wire static schedules into Definitions

**Files:**
- Modify: `dagster/d4bl_pipelines/__init__.py`

**Step 1: Update `__init__.py`**

Change the import line:
```python
from d4bl_pipelines.schedules import load_schedules_from_db
```
to:
```python
from d4bl_pipelines.schedules import build_static_schedules, load_schedules_from_db
```

Change the schedules block from:
```python
try:
    schedules = load_schedules_from_db(get_db_url())
except Exception:
    logger.warning(
        "Failed to load schedules from DB; starting with none",
        exc_info=True,
    )
    schedules = []
```
to:
```python
static_schedules = build_static_schedules()

try:
    db_schedules = load_schedules_from_db(get_db_url())
except Exception:
    logger.warning(
        "Failed to load schedules from DB; starting with none",
        exc_info=True,
    )
    db_schedules = []

schedules = static_schedules + db_schedules
```

**Step 2: Run full test suite**

Run: `cd dagster && python -m pytest tests/ -v`
Expected: ALL PASS

**Step 3: Commit**

```bash
git add dagster/d4bl_pipelines/__init__.py
git commit -m "feat: wire static schedules into Dagster Definitions (#73)"
```
