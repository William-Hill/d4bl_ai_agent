# dagster/tests/test_cdc_places_asset.py
from d4bl_pipelines.assets.apis.cdc_places import (
    CDC_MEASURES,
    CDC_PLACES_TRACT_URL,
    CDC_PLACES_URL,
    _parse_row,
    cdc_places_health,
    cdc_places_tract_health,
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


def test_cdc_places_tract_asset_exists():
    """The cdc_places_tract_health asset should be importable."""
    assert cdc_places_tract_health is not None


def test_cdc_places_tract_asset_group_name():
    """Tract asset should belong to the 'apis' group."""
    spec = cdc_places_tract_health.specs_by_key
    key = next(iter(spec))
    assert spec[key].group_name == "apis"


def test_cdc_places_tract_url_is_tract_endpoint():
    """Tract URL should point to the census tract SODA endpoint."""
    assert "cwsq-ngmh" in CDC_PLACES_TRACT_URL


def test_cdc_places_county_url_is_county_endpoint():
    """County URL should point to the county SODA endpoint."""
    assert "swc5-untb" in CDC_PLACES_URL


def test_parse_row_valid():
    """_parse_row should return a dict for a valid CDC row."""
    row = {
        "countyfips": "17031",
        "data_value": "12.5",
        "measureid": "DIABETES",
        "year": "2023",
        "data_value_type": "Crude prevalence",
        "stateabbr": "IL",
        "statedesc": "Illinois",
        "countyname": "Cook",
        "low_confidence_limit": "11.0",
        "high_confidence_limit": "14.0",
        "totalpopulation": "5200000",
        "category": "Health Outcomes",
        "measure": "Diagnosed diabetes among adults",
    }
    result = _parse_row(row, fips_field="countyfips")
    assert result is not None
    assert result["fips"] == "17031"
    assert result["value"] == 12.5
    assert result["measure"] == "diabetes"
    assert result["state_fips"] == "17"


def test_parse_row_missing_fips():
    """_parse_row should return None when FIPS is missing."""
    row = {"data_value": "12.5", "measureid": "DIABETES"}
    assert _parse_row(row, fips_field="countyfips") is None


def test_parse_row_missing_value():
    """_parse_row should return None when data_value is missing."""
    row = {"countyfips": "17031", "measureid": "DIABETES"}
    assert _parse_row(row, fips_field="countyfips") is None


def test_parse_row_invalid_value():
    """_parse_row should return None for non-numeric data_value."""
    row = {
        "countyfips": "17031",
        "data_value": "not_a_number",
        "measureid": "DIABETES",
        "year": "2023",
    }
    assert _parse_row(row, fips_field="countyfips") is None


def test_parse_row_valid_tract():
    """_parse_row should handle tract rows via locationid."""
    row = {
        "locationid": "17031010100",
        "locationname": "Census Tract 010100",
        "data_value": "12.5",
        "measureid": "DIABETES",
        "year": "2023",
        "data_value_type": "Crude prevalence",
    }
    result = _parse_row(row, fips_field="locationid")
    assert result is not None
    assert result["fips"] == "17031010100"
    assert result["geo_name"] == "Census Tract 010100"
    assert result["state_fips"] == "17"


def test_parse_row_missing_year():
    """_parse_row should return None when year is missing."""
    row = {
        "countyfips": "17031",
        "data_value": "12.5",
        "measureid": "DIABETES",
    }
    assert _parse_row(row, fips_field="countyfips") is None
