from d4bl_pipelines.assets.apis.census_acs import (
    census_acs_indicators,
)


def test_census_acs_asset_exists():
    """The census_acs_indicators asset should be importable."""
    assert census_acs_indicators is not None


def test_census_acs_asset_has_metadata():
    """Asset should have group and description metadata."""
    spec = census_acs_indicators.specs_by_key
    key = next(iter(spec))
    assert key.path[-1] == "census_acs_indicators"
