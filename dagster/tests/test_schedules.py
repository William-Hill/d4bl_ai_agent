"""Unit tests for dynamic schedule generation."""

from d4bl_pipelines.schedules import (
    _slugify,
    build_monitor_schedules,
    build_source_schedules,
    build_static_schedules,
    STATIC_SCHEDULES,
)

from dagster import DefaultScheduleStatus

# ---------------------------------------------------------------------------
# _slugify
# ---------------------------------------------------------------------------

def test_slugify_basic():
    assert _slugify("Census ACS") == "census_acs"


def test_slugify_special_chars():
    assert _slugify("My-Source (v2)") == "my_source_v2"


def test_slugify_strips_underscores():
    assert _slugify("  hello  ") == "hello"


# ---------------------------------------------------------------------------
# build_source_schedules
# ---------------------------------------------------------------------------

def test_build_source_schedules_creates_schedule():
    sources = [
        {
            "name": "Census ACS",
            "default_schedule": "0 6 * * *",
            "enabled": True,
        },
    ]
    schedules = build_source_schedules(sources)
    assert len(schedules) == 1

    sched = schedules[0]
    assert sched.name == "schedule_census_acs"
    assert sched.cron_schedule == "0 6 * * *"
    assert sched.default_status == DefaultScheduleStatus.RUNNING


def test_build_source_schedules_skips_null_schedule():
    sources = [
        {"name": "No Schedule", "default_schedule": None, "enabled": True},
    ]
    assert build_source_schedules(sources) == []


def test_build_source_schedules_skips_missing_schedule_key():
    sources = [
        {"name": "Missing Key", "enabled": True},
    ]
    assert build_source_schedules(sources) == []


def test_build_source_schedules_skips_disabled():
    sources = [
        {
            "name": "Disabled Source",
            "default_schedule": "0 6 * * *",
            "enabled": False,
        },
    ]
    assert build_source_schedules(sources) == []


def test_build_source_schedules_empty_input():
    assert build_source_schedules([]) == []


def test_build_source_schedules_multiple():
    sources = [
        {
            "name": "Source A",
            "default_schedule": "0 6 * * *",
            "enabled": True,
        },
        {
            "name": "Source B",
            "default_schedule": "0 12 * * 1",
            "enabled": True,
        },
        {
            "name": "Source C",
            "default_schedule": None,
            "enabled": True,
        },
    ]
    schedules = build_source_schedules(sources)
    assert len(schedules) == 2
    names = {s.name for s in schedules}
    assert names == {"schedule_source_a", "schedule_source_b"}


def test_build_source_schedules_cron_passthrough():
    cron = "*/15 * * * *"
    sources = [
        {"name": "Fast", "default_schedule": cron, "enabled": True},
    ]
    schedules = build_source_schedules(sources)
    assert schedules[0].cron_schedule == cron


def test_build_source_schedules_enabled_defaults_true():
    """If enabled key is missing, source should be included."""
    sources = [
        {"name": "Default Enabled", "default_schedule": "0 6 * * *"},
    ]
    schedules = build_source_schedules(sources)
    assert len(schedules) == 1


# ---------------------------------------------------------------------------
# build_monitor_schedules
# ---------------------------------------------------------------------------

def test_build_monitor_schedules_creates_schedule():
    monitors = [
        {
            "name": "Racial Equity",
            "schedule": "0 8 * * *",
            "enabled": True,
        },
    ]
    schedules = build_monitor_schedules(monitors)
    assert len(schedules) == 1

    sched = schedules[0]
    assert sched.name == "monitor_racial_equity"
    assert sched.cron_schedule == "0 8 * * *"
    assert sched.default_status == DefaultScheduleStatus.RUNNING


def test_build_monitor_schedules_target_includes_keyword_prefix():
    monitors = [
        {
            "name": "Police Accountability",
            "schedule": "0 0 * * *",
            "enabled": True,
        },
    ]
    schedules = build_monitor_schedules(monitors)
    # Target should be AssetSelection for keyword_search_<slug>
    assert schedules[0].name == "monitor_police_accountability"


def test_build_monitor_schedules_skips_null_schedule():
    monitors = [
        {"name": "No Cron", "schedule": None, "enabled": True},
    ]
    assert build_monitor_schedules(monitors) == []


def test_build_monitor_schedules_skips_disabled():
    monitors = [
        {
            "name": "Off",
            "schedule": "0 0 * * *",
            "enabled": False,
        },
    ]
    assert build_monitor_schedules(monitors) == []


def test_build_monitor_schedules_empty_input():
    assert build_monitor_schedules([]) == []


def test_build_monitor_schedules_enabled_defaults_true():
    monitors = [
        {"name": "Implicit Enabled", "schedule": "0 9 * * *"},
    ]
    schedules = build_monitor_schedules(monitors)
    assert len(schedules) == 1


# ---------------------------------------------------------------------------
# build_static_schedules
# ---------------------------------------------------------------------------


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
    expected = {
        "refresh_census_acs_indicators": "0 0 1 1 *",
        "refresh_cdc_places_health": "0 0 1 */3 *",
        "refresh_bls_labor_stats": "0 0 1 * *",
        "refresh_fbi_ucr_crime": "0 0 1 1 *",
        "refresh_epa_ejscreen": "0 0 1 1 *",
        "refresh_hud_fair_housing": "0 0 1 1 *",
        "refresh_usda_food_access": "0 0 1 1 *",
        "refresh_doe_civil_rights": "0 0 1 1 *",
        "refresh_mapping_police_violence": "0 0 1 * *",
        "refresh_openstates_bills": "0 6 * * 1-5",
    }
    schedules = build_static_schedules()
    assert {s.name: s.cron_schedule for s in schedules} == expected
