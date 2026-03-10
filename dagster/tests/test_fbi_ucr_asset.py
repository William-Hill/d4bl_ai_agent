from d4bl_pipelines.assets.apis.fbi_ucr import (
    FBI_OFFENSES,
    fbi_ucr_crime,
)


def test_fbi_ucr_asset_exists():
    assert fbi_ucr_crime is not None


def test_fbi_ucr_asset_has_metadata():
    spec = fbi_ucr_crime.specs_by_key
    key = next(iter(spec))
    assert key.path[-1] == "fbi_ucr_crime"


def test_fbi_ucr_asset_group_name():
    spec = fbi_ucr_crime.specs_by_key
    key = next(iter(spec))
    assert spec[key].group_name == "apis"


def test_fbi_offenses_non_empty():
    assert len(FBI_OFFENSES) >= 5
