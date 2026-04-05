"""Tests for scripts/training/templates.py — passage rendering functions."""

from __future__ import annotations

from scripts.training.templates import (
    render_bjs_passage,
    render_cdc_passage,
    render_census_passage,
    render_epa_passage,
    render_fbi_passage,
    render_police_violence_passage,
)

# ---------------------------------------------------------------------------
# Census
# ---------------------------------------------------------------------------


class TestRenderCensusPassage:
    def test_contains_geography_name(self):
        row = {
            "geography_name": "Cook County",
            "fips_code": "17031",
            "race": "black_alone",
            "metric": "median_household_income",
            "value": 45000.0,
            "margin_of_error": 1200.0,
            "year": 2021,
        }
        passage = render_census_passage(row)
        assert "Cook County" in passage

    def test_contains_fips_code(self):
        row = {
            "geography_name": "Cook County",
            "fips_code": "17031",
            "race": "black_alone",
            "metric": "median_household_income",
            "value": 45000.0,
            "margin_of_error": None,
            "year": 2021,
        }
        passage = render_census_passage(row)
        assert "17031" in passage

    def test_race_is_capitalized(self):
        row = {
            "geography_name": "Cook County",
            "fips_code": "17031",
            "race": "black_alone",
            "metric": "median_household_income",
            "value": 45000.0,
            "margin_of_error": None,
            "year": 2021,
        }
        passage = render_census_passage(row)
        assert "Black Alone" in passage

    def test_dollar_value_formatted(self):
        row = {
            "geography_name": "Cook County",
            "fips_code": "17031",
            "race": "white_alone",
            "metric": "median_household_income",
            "value": 72500.0,
            "margin_of_error": None,
            "year": 2021,
        }
        passage = render_census_passage(row)
        assert "$72,500" in passage

    def test_rate_value_formatted(self):
        row = {
            "geography_name": "Travis County",
            "fips_code": "48453",
            "race": "hispanic",
            "metric": "poverty_rate",
            "value": 14.3,
            "margin_of_error": None,
            "year": 2021,
        }
        passage = render_census_passage(row)
        assert "14.3%" in passage

    def test_margin_of_error_included(self):
        row = {
            "geography_name": "Cook County",
            "fips_code": "17031",
            "race": "black_alone",
            "metric": "median_household_income",
            "value": 45000.0,
            "margin_of_error": 1200.0,
            "year": 2021,
        }
        passage = render_census_passage(row)
        assert "1,200" in passage

    def test_empty_race_becomes_total_population(self):
        row = {
            "geography_name": "Los Angeles County",
            "fips_code": "06037",
            "race": "",
            "metric": "median_household_income",
            "value": 68000.0,
            "margin_of_error": None,
            "year": 2021,
        }
        passage = render_census_passage(row)
        assert "total population" in passage


# ---------------------------------------------------------------------------
# CDC
# ---------------------------------------------------------------------------


class TestRenderCdcPassage:
    CDC_ROW = {
        "geography_name": "Alabama",
        "fips_code": "01000",
        "measure": "Current_Asthma",
        "category": "health_outcomes",
        "data_value": 10.2,
        "data_value_type": "Crude prevalence",
        "low_confidence_limit": 9.1,
        "high_confidence_limit": 11.3,
        "total_population": 5000000,
        "year": 2022,
    }

    def test_contains_geography_name(self):
        passage = render_cdc_passage(self.CDC_ROW)
        assert "Alabama" in passage

    def test_contains_measure(self):
        passage = render_cdc_passage(self.CDC_ROW)
        assert "current asthma" in passage.lower()

    def test_contains_percentage_value(self):
        passage = render_cdc_passage(self.CDC_ROW)
        assert "10.2%" in passage

    def test_contains_confidence_intervals(self):
        passage = render_cdc_passage(self.CDC_ROW)
        assert "9.1" in passage
        assert "11.3" in passage


# ---------------------------------------------------------------------------
# EPA
# ---------------------------------------------------------------------------


class TestRenderEpaPassage:
    EPA_ROW = {
        "state_name": "California",
        "tract_fips": "06001003001",
        "indicator": "PM25",
        "raw_value": 12.4,
        "percentile_state": 72.0,
        "percentile_national": 85.0,
        "population": 4325,
        "minority_pct": 68.5,
        "low_income_pct": 42.1,
        "year": 2020,
    }

    def test_contains_state_name(self):
        passage = render_epa_passage(self.EPA_ROW)
        assert "California" in passage

    def test_contains_pm25_display_name(self):
        passage = render_epa_passage(self.EPA_ROW)
        assert "PM2.5" in passage

    def test_contains_raw_value(self):
        passage = render_epa_passage(self.EPA_ROW)
        assert "12.4" in passage

    def test_contains_percentiles(self):
        passage = render_epa_passage(self.EPA_ROW)
        assert "85" in passage
        assert "72" in passage

    def test_contains_minority_percentage(self):
        passage = render_epa_passage(self.EPA_ROW)
        assert "68.5" in passage


# ---------------------------------------------------------------------------
# Police Violence
# ---------------------------------------------------------------------------


class TestRenderPoliceViolencePassage:
    PV_ROW = {
        "city": "Denver",
        "state": "CO",
        "race": "Black",
        "age": 34,
        "gender": "Male",
        "armed_status": "unarmed",
        "cause_of_death": "Gunshot",
        "year": 2021,
        "agency": "Denver Police Department",
    }

    def test_contains_city(self):
        passage = render_police_violence_passage(self.PV_ROW)
        assert "Denver" in passage

    def test_state_abbreviation_expanded_to_full_name(self):
        passage = render_police_violence_passage(self.PV_ROW)
        assert "Colorado" in passage

    def test_contains_race(self):
        passage = render_police_violence_passage(self.PV_ROW)
        assert "Black" in passage

    def test_contains_armed_status(self):
        passage = render_police_violence_passage(self.PV_ROW)
        assert "unarmed" in passage


# ---------------------------------------------------------------------------
# BJS
# ---------------------------------------------------------------------------


class TestRenderBjsPassage:
    BJS_ROW = {
        "state_name": "Texas",
        "state_abbrev": "TX",
        "facility_type": "state_prison",
        "metric": "population",
        "race": "Black",
        "gender": "Male",
        "value": 125000,
        "year": 2021,
    }

    def test_contains_state_name(self):
        passage = render_bjs_passage(self.BJS_ROW)
        assert "Texas" in passage

    def test_contains_race(self):
        passage = render_bjs_passage(self.BJS_ROW)
        assert "Black" in passage

    def test_value_formatted_with_commas(self):
        passage = render_bjs_passage(self.BJS_ROW)
        assert "125,000" in passage

    def test_contains_facility_type(self):
        passage = render_bjs_passage(self.BJS_ROW)
        assert "state_prison" in passage


# ---------------------------------------------------------------------------
# FBI
# ---------------------------------------------------------------------------


class TestRenderFbiPassage:
    FBI_ROW = {
        "state_name": "New York",
        "offense": "Aggravated Assault",
        "category": "violent_crime",
        "race": "White",
        "value": 5000,
        "population": 1000000,
        "year": 2021,
    }

    def test_contains_state_name(self):
        passage = render_fbi_passage(self.FBI_ROW)
        assert "New York" in passage

    def test_contains_offense(self):
        passage = render_fbi_passage(self.FBI_ROW)
        assert "Aggravated Assault" in passage

    def test_contains_category(self):
        passage = render_fbi_passage(self.FBI_ROW)
        assert "violent_crime" in passage

    def test_contains_race(self):
        passage = render_fbi_passage(self.FBI_ROW)
        assert "White" in passage

    def test_per_100k_rate_calculated(self):
        passage = render_fbi_passage(self.FBI_ROW)
        assert "500.0 per 100,000" in passage
