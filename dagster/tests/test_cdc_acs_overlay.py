from d4bl_pipelines.assets.apis.cdc_acs_overlay import (
    RACES,
    compute_race_estimates,
    cdc_acs_race_overlay,
)


def test_overlay_asset_exists():
    assert cdc_acs_race_overlay is not None


def test_overlay_asset_group_name():
    spec = cdc_acs_race_overlay.specs_by_key
    key = next(iter(spec))
    assert spec[key].group_name == "apis"


def test_races_includes_expected():
    assert "black" in RACES
    assert "white" in RACES
    assert "hispanic" in RACES


def test_compute_race_estimates_basic():
    cdc_row = {
        "fips_code": "17031",
        "geography_type": "county",
        "geography_name": "Cook County",
        "state_fips": "17",
        "year": 2023,
        "measure": "diabetes",
        "data_value": 12.0,
        "low_confidence_limit": 10.0,
        "high_confidence_limit": 14.0,
    }
    acs_pops = {"total": 5000000, "black": 1200000, "white": 2000000, "hispanic": 1300000}
    results = compute_race_estimates(cdc_row, acs_pops)

    assert len(results) == 3
    black_result = next(r for r in results if r["race"] == "black")
    assert black_result["health_rate"] == 12.0
    assert abs(black_result["race_population_share"] - 0.24) < 0.001
    assert abs(black_result["estimated_value"] - 2.88) < 0.01
    assert black_result["total_population"] == 5000000
    assert abs(black_result["confidence_low"] - 2.4) < 0.01    # 10.0 * 0.24
    assert abs(black_result["confidence_high"] - 3.36) < 0.01  # 14.0 * 0.24


def test_compute_race_estimates_zero_total_pop():
    cdc_row = {
        "fips_code": "99999", "geography_type": "county",
        "geography_name": "Empty", "state_fips": "99", "year": 2023,
        "measure": "diabetes", "data_value": 10.0,
        "low_confidence_limit": None, "high_confidence_limit": None,
    }
    assert compute_race_estimates(cdc_row, {"total": 0, "black": 0}) == []


def test_compute_race_estimates_missing_race():
    cdc_row = {
        "fips_code": "17031", "geography_type": "county",
        "geography_name": "Cook", "state_fips": "17", "year": 2023,
        "measure": "obesity", "data_value": 30.0,
        "low_confidence_limit": 28.0, "high_confidence_limit": 32.0,
    }
    results = compute_race_estimates(cdc_row, {"total": 1000, "black": 300})
    assert len(results) == 1
    assert results[0]["race"] == "black"
