from d4bl_pipelines.assets.apis.usda_food_access import (
    FOOD_ACCESS_INDICATORS,
    usda_food_access,
)


def test_usda_food_access_asset_exists():
    assert usda_food_access is not None


def test_usda_food_access_asset_has_metadata():
    spec = usda_food_access.specs_by_key
    key = next(iter(spec))
    assert key.path[-1] == "usda_food_access"


def test_usda_food_access_asset_group_name():
    spec = usda_food_access.specs_by_key
    key = next(iter(spec))
    assert spec[key].group_name == "apis"


def test_food_access_indicators_non_empty():
    assert len(FOOD_ACCESS_INDICATORS) >= 3
