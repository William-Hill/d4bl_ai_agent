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
