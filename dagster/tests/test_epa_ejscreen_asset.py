from d4bl_pipelines.assets.apis.epa_ejscreen import (
    EJ_INDICATORS,
    epa_ejscreen,
    aggregate_block_groups_to_tracts,
    CSV_INDICATOR_COLUMNS,
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


def _make_csv_rows():
    """Build sample block-group rows for two block groups in one tract."""
    return [
        {
            "ID": "060010201001",  # tract 06001020100, bg 1
            "ST_ABBREV": "CA",
            "ACSTOTPOP": "1000",
            "MINORPCT": "0.40",
            "LOWINCPCT": "0.30",
            "PM25": "10.0",
            "OZONE": "0.04",
            "DSLPM": "0.5",
            "CANCER": "30",
            "RESP": "0.5",
            "PTRAF": "200",
            "PNPL": "0.1",
            "PRMP": "0.2",
            "PTSDF": "0.3",
            "PWDIS": "0.4",
            "PRE1960PCT": "0.20",
            "UNDER5PCT": "0.05",
            "OVER64PCT": "0.12",
            "LINGISOPCT": "0.03",
            "LESSHSPCT": "0.10",
            "UNEMPPCT": "0.06",
            "P_PM25": "60",
            "P_OZONE": "50",
            "P_DSLPM": "55",
            "P_CANCER": "70",
            "P_RESP": "45",
            "P_PTRAF": "80",
            "P_PNPL": "30",
            "P_PRMP": "40",
            "P_PTSDF": "35",
            "P_PWDIS": "25",
            "P_PRE1960PCT": "65",
            "P_UNDER5PCT": "50",
            "P_OVER64PCT": "55",
            "P_MINORPCT": "40",
            "P_LOWINCPCT": "30",
            "P_LINGISOPCT": "20",
            "P_LESSHSPCT": "35",
            "P_UNEMPPCT": "25",
        },
        {
            "ID": "060010201002",  # tract 06001020100, bg 2
            "ST_ABBREV": "CA",
            "ACSTOTPOP": "3000",
            "MINORPCT": "0.60",
            "LOWINCPCT": "0.50",
            "PM25": "12.0",
            "OZONE": "0.06",
            "DSLPM": "0.7",
            "CANCER": "40",
            "RESP": "0.7",
            "PTRAF": "300",
            "PNPL": "0.3",
            "PRMP": "0.4",
            "PTSDF": "0.5",
            "PWDIS": "0.6",
            "PRE1960PCT": "0.30",
            "UNDER5PCT": "0.07",
            "OVER64PCT": "0.15",
            "LINGISOPCT": "0.05",
            "LESSHSPCT": "0.15",
            "UNEMPPCT": "0.08",
            "P_PM25": "70",
            "P_OZONE": "60",
            "P_DSLPM": "65",
            "P_CANCER": "80",
            "P_RESP": "55",
            "P_PTRAF": "90",
            "P_PNPL": "40",
            "P_PRMP": "50",
            "P_PTSDF": "45",
            "P_PWDIS": "35",
            "P_PRE1960PCT": "75",
            "P_UNDER5PCT": "60",
            "P_OVER64PCT": "65",
            "P_MINORPCT": "60",
            "P_LOWINCPCT": "50",
            "P_LINGISOPCT": "30",
            "P_LESSHSPCT": "45",
            "P_UNEMPPCT": "35",
        },
    ]


def test_aggregate_block_groups_basic():
    """Two block groups in the same tract should be population-weighted averaged."""
    rows = _make_csv_rows()
    result = aggregate_block_groups_to_tracts(rows)
    assert "06001020100" in result
    tract = result["06001020100"]
    assert tract["population"] == 4000
    assert tract["state_fips"] == "06"
    assert tract["state_abbrev"] == "CA"
    # PM25: (10*1000 + 12*3000) / 4000 = 11.5
    assert abs(tract["indicators"]["pm25"]["raw_value"] - 11.5) < 0.01
    # P_PM25: (60*1000 + 70*3000) / 4000 = 67.5
    assert abs(tract["indicators"]["pm25"]["percentile_national"] - 67.5) < 0.01


def test_aggregate_block_groups_minority_pct():
    """Minority pct should be population-weighted."""
    rows = _make_csv_rows()
    result = aggregate_block_groups_to_tracts(rows)
    tract = result["06001020100"]
    # (0.40*1000 + 0.60*3000) / 4000 = 0.55
    assert abs(tract["minority_pct"] - 0.55) < 0.01


def test_aggregate_skips_missing_population():
    """Block groups with missing population should be skipped."""
    rows = [
        {
            "ID": "060010201001",
            "ST_ABBREV": "CA",
            "ACSTOTPOP": "",
            "MINORPCT": "0.50",
            "LOWINCPCT": "0.30",
            **{ind: "1.0" for ind in CSV_INDICATOR_COLUMNS},
            **{f"P_{ind}": "50" for ind in CSV_INDICATOR_COLUMNS},
        },
    ]
    result = aggregate_block_groups_to_tracts(rows)
    assert len(result) == 0


def test_csv_indicator_columns_match_ej_indicators():
    """CSV columns should cover all the EJ_INDICATORS we track."""
    for ind in EJ_INDICATORS:
        assert ind in CSV_INDICATOR_COLUMNS
