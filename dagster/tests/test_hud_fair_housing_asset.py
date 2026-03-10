from d4bl_pipelines.assets.apis.hud_fair_housing import (
    HUD_INDICATORS,
    hud_fair_housing,
)


def test_hud_fair_housing_asset_exists():
    assert hud_fair_housing is not None


def test_hud_fair_housing_asset_has_metadata():
    spec = hud_fair_housing.specs_by_key
    key = next(iter(spec))
    assert key.path[-1] == "hud_fair_housing"


def test_hud_fair_housing_asset_group_name():
    spec = hud_fair_housing.specs_by_key
    key = next(iter(spec))
    assert spec[key].group_name == "apis"


def test_hud_indicators_non_empty():
    assert len(HUD_INDICATORS) >= 3
