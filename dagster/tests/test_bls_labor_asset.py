from d4bl_pipelines.assets.apis.bls_labor import (
    BLS_SERIES,
    bls_labor_stats,
)


def test_bls_labor_stats_asset_exists():
    assert bls_labor_stats is not None


def test_bls_labor_stats_asset_has_metadata():
    spec = bls_labor_stats.specs_by_key
    key = next(iter(spec))
    assert key.path[-1] == "bls_labor_stats"


def test_bls_labor_stats_asset_group_name():
    spec = bls_labor_stats.specs_by_key
    key = next(iter(spec))
    assert spec[key].group_name == "apis"


def test_bls_series_non_empty():
    assert len(BLS_SERIES) >= 4
