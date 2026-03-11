from d4bl_pipelines.assets.apis.mapping_police_violence import (
    mapping_police_violence,
)


def test_mapping_police_violence_asset_exists():
    assert mapping_police_violence is not None


def test_mapping_police_violence_asset_has_metadata():
    spec = mapping_police_violence.specs_by_key
    key = next(iter(spec))
    assert key.path[-1] == "mapping_police_violence"


def test_mapping_police_violence_asset_group_name():
    spec = mapping_police_violence.specs_by_key
    key = next(iter(spec))
    assert spec[key].group_name == "apis"
