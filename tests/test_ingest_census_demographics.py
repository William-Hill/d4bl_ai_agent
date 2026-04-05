"""Tests for Census Decennial demographics ingestion."""

import pytest

pytest.importorskip("psycopg2", reason="psycopg2 not installed in CI")

from scripts.ingestion.ingest_census_demographics import _build_records, _pct


def test_pct_normal():
    assert _pct(250, 1000) == 25.0


def test_pct_zero_total():
    assert _pct(250, 0) is None


def test_pct_none_values():
    assert _pct(None, 1000) is None


def test_build_records_county():
    headers = [
        "NAME",
        "P1_001N",
        "P1_003N",
        "P1_004N",
        "P1_005N",
        "P1_006N",
        "P1_007N",
        "P1_008N",
        "P1_009N",
        "P2_002N",
        "state",
        "county",
    ]
    rows = [
        [
            "Example County, Alabama",
            "1000",
            "600",
            "200",
            "10",
            "50",
            "5",
            "35",
            "100",
            "80",
            "01",
            "001",
        ],
    ]
    records = _build_records(headers, rows, "county", 2020)

    # 9 race categories per geography row (total + 8 races)
    assert len(records) == 9

    # Check the total record
    total = [r for r in records if r["race"] == "total"][0]
    assert total["geo_id"] == "01001"
    assert total["geo_type"] == "county"
    assert total["state_fips"] == "01"
    assert total["state_name"] == "Alabama"
    assert total["population"] == 1000
    assert total["pct_of_total"] == 100.0
    assert total["year"] == 2020

    # Check a specific race
    black = [r for r in records if r["race"] == "Black"][0]
    assert black["population"] == 200
    assert black["pct_of_total"] == 20.0


def test_build_records_tract():
    headers = [
        "NAME",
        "P1_001N",
        "P1_003N",
        "P1_004N",
        "P1_005N",
        "P1_006N",
        "P1_007N",
        "P1_008N",
        "P1_009N",
        "P2_002N",
        "state",
        "county",
        "tract",
    ]
    rows = [
        [
            "Tract 1, County, State",
            "500",
            "300",
            "100",
            "5",
            "25",
            "2",
            "18",
            "50",
            "40",
            "01",
            "001",
            "000100",
        ],
    ]
    records = _build_records(headers, rows, "tract", 2020)

    assert len(records) == 9
    total = [r for r in records if r["race"] == "total"][0]
    assert total["geo_id"] == "01001000100"
    assert total["geo_type"] == "tract"


def test_build_records_skips_invalid_population():
    headers = [
        "NAME",
        "P1_001N",
        "P1_003N",
        "P1_004N",
        "P1_005N",
        "P1_006N",
        "P1_007N",
        "P1_008N",
        "P1_009N",
        "P2_002N",
        "state",
        "county",
    ]
    rows = [
        ["Bad County", "N/A", "N/A", "N/A", "N/A", "N/A", "N/A", "N/A", "N/A", "N/A", "01", "001"],
    ]
    records = _build_records(headers, rows, "county", 2020)
    assert len(records) == 0
