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
