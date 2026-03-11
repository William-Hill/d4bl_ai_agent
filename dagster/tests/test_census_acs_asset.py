import inspect

from d4bl_pipelines.assets.apis.census_acs import (
    _fetch_acs,
    census_acs_county_indicators,
    census_acs_indicators,
)
from d4bl_pipelines.schedules import STATIC_SCHEDULES


def test_census_acs_asset_exists():
    """The census_acs_indicators asset should be importable."""
    assert census_acs_indicators is not None


def test_fetch_acs_accepts_geography_param():
    """_fetch_acs should accept a geography keyword argument."""
    sig = inspect.signature(_fetch_acs)
    assert "geography" in sig.parameters
    assert sig.parameters["geography"].default == "state:*"


def test_census_acs_asset_has_metadata():
    """Asset should have group and description metadata."""
    spec = census_acs_indicators.specs_by_key
    key = next(iter(spec))
    assert key.path[-1] == "census_acs_indicators"


def test_census_acs_county_asset_exists():
    """The census_acs_county_indicators asset should be importable."""
    assert census_acs_county_indicators is not None


def test_census_acs_county_asset_has_metadata():
    """County asset should have correct group and description metadata."""
    spec = census_acs_county_indicators.specs_by_key
    key = next(iter(spec))
    assert key.path[-1] == "census_acs_county_indicators"


def test_county_schedule_registered():
    """County asset should have a static schedule."""
    assert "census_acs_county_indicators" in STATIC_SCHEDULES
