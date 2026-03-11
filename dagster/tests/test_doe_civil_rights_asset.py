from d4bl_pipelines.assets.apis.doe_civil_rights import (
    CRDC_METRICS,
    doe_civil_rights,
)


def test_doe_civil_rights_asset_exists():
    assert doe_civil_rights is not None


def test_doe_civil_rights_asset_has_metadata():
    spec = doe_civil_rights.specs_by_key
    key = next(iter(spec))
    assert key.path[-1] == "doe_civil_rights"


def test_doe_civil_rights_asset_group_name():
    spec = doe_civil_rights.specs_by_key
    key = next(iter(spec))
    assert spec[key].group_name == "apis"


def test_crdc_metrics_non_empty():
    assert len(CRDC_METRICS) >= 3
