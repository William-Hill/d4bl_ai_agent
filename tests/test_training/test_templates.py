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
    def test_contains_geography_name(self):
        row = {
            "geography_name": "Alabama",
            "measure": "Current Asthma",
            "value": 10.2,
            "ci_low": 9.1,
            "ci_high": 11.3,
            "year": 2022,
        }
        passage = render_cdc_passage(row)
        assert "Alabama" in passage

    def test_contains_measure(self):
        row = {
            "geography_name": "Alabama",
            "measure": "Current Asthma",
            "value": 10.2,
            "ci_low": 9.1,
            "ci_high": 11.3,
            "year": 2022,
        }
        passage = render_cdc_passage(row)
        assert "Current Asthma" in passage

    def test_contains_percentage_value(self):
        row = {
            "geography_name": "Alabama",
            "measure": "Current Asthma",
            "value": 10.2,
            "ci_low": 9.1,
            "ci_high": 11.3,
            "year": 2022,
        }
        passage = render_cdc_passage(row)
        assert "10.2%" in passage

    def test_contains_confidence_intervals(self):
        row = {
            "geography_name": "Alabama",
            "measure": "Current Asthma",
            "value": 10.2,
            "ci_low": 9.1,
            "ci_high": 11.3,
            "year": 2022,
        }
        passage = render_cdc_passage(row)
        assert "9.1" in passage
        assert "11.3" in passage


# ---------------------------------------------------------------------------
# EPA
# ---------------------------------------------------------------------------

class TestRenderEpaPassage:
    def test_contains_state_name(self):
        row = {
            "state_fips": "06",
            "indicator": "PM25",
            "raw_value": 12.4,
            "percentile": 85.0,
            "state_percentile": 72.0,
            "minority_pct": 68.5,
            "year": 2020,
        }
        passage = render_epa_passage(row)
        assert "California" in passage

    def test_contains_pm25_display_name(self):
        row = {
            "state_fips": "06",
            "indicator": "PM25",
            "raw_value": 12.4,
            "percentile": 85.0,
            "state_percentile": 72.0,
            "minority_pct": 68.5,
            "year": 2020,
        }
        passage = render_epa_passage(row)
        assert "PM2.5" in passage

    def test_contains_raw_value(self):
        row = {
            "state_fips": "06",
            "indicator": "PM25",
            "raw_value": 12.4,
            "percentile": 85.0,
            "state_percentile": 72.0,
            "minority_pct": 68.5,
            "year": 2020,
        }
        passage = render_epa_passage(row)
        assert "12.4" in passage

    def test_contains_percentiles(self):
        row = {
            "state_fips": "06",
            "indicator": "PM25",
            "raw_value": 12.4,
            "percentile": 85.0,
            "state_percentile": 72.0,
            "minority_pct": 68.5,
            "year": 2020,
        }
        passage = render_epa_passage(row)
        assert "85" in passage
        assert "72" in passage

    def test_contains_minority_percentage(self):
        row = {
            "state_fips": "06",
            "indicator": "PM25",
            "raw_value": 12.4,
            "percentile": 85.0,
            "state_percentile": 72.0,
            "minority_pct": 68.5,
            "year": 2020,
        }
        passage = render_epa_passage(row)
        assert "68.5" in passage


# ---------------------------------------------------------------------------
# Police Violence
# ---------------------------------------------------------------------------

class TestRenderPoliceViolencePassage:
    def test_contains_city(self):
        row = {
            "city": "Denver",
            "state": "CO",
            "victim_race": "Black",
            "armed_status": "unarmed",
            "year": 2021,
        }
        passage = render_police_violence_passage(row)
        assert "Denver" in passage

    def test_state_abbreviation_expanded_to_full_name(self):
        row = {
            "city": "Denver",
            "state": "CO",
            "victim_race": "Black",
            "armed_status": "unarmed",
            "year": 2021,
        }
        passage = render_police_violence_passage(row)
        assert "Colorado" in passage
        assert " CO" not in passage  # abbreviation should not appear standalone

    def test_contains_race(self):
        row = {
            "city": "Denver",
            "state": "CO",
            "victim_race": "Black",
            "armed_status": "unarmed",
            "year": 2021,
        }
        passage = render_police_violence_passage(row)
        assert "Black" in passage

    def test_contains_armed_status(self):
        row = {
            "city": "Denver",
            "state": "CO",
            "victim_race": "Black",
            "armed_status": "unarmed",
            "year": 2021,
        }
        passage = render_police_violence_passage(row)
        assert "unarmed" in passage


# ---------------------------------------------------------------------------
# BJS
# ---------------------------------------------------------------------------

class TestRenderBjsPassage:
    def test_contains_state_name(self):
        row = {
            "state_fips": "48",
            "race": "Black",
            "value": 125000,
            "facility_type": "state_prison",
            "year": 2021,
        }
        passage = render_bjs_passage(row)
        assert "Texas" in passage

    def test_contains_race(self):
        row = {
            "state_fips": "48",
            "race": "Black",
            "value": 125000,
            "facility_type": "state_prison",
            "year": 2021,
        }
        passage = render_bjs_passage(row)
        assert "Black" in passage

    def test_value_formatted_with_commas(self):
        row = {
            "state_fips": "48",
            "race": "Black",
            "value": 125000,
            "facility_type": "state_prison",
            "year": 2021,
        }
        passage = render_bjs_passage(row)
        assert "125,000" in passage

    def test_contains_facility_type(self):
        row = {
            "state_fips": "48",
            "race": "Black",
            "value": 125000,
            "facility_type": "state_prison",
            "year": 2021,
        }
        passage = render_bjs_passage(row)
        assert "state_prison" in passage


# ---------------------------------------------------------------------------
# FBI
# ---------------------------------------------------------------------------

class TestRenderFbiPassage:
    def test_contains_state_name(self):
        row = {
            "state_fips": "36",
            "offense": "Aggravated Assault",
            "category": "violent_crime",
            "race": "White",
            "count": 5000,
            "population": 1000000,
            "year": 2021,
        }
        passage = render_fbi_passage(row)
        assert "New York" in passage

    def test_contains_offense(self):
        row = {
            "state_fips": "36",
            "offense": "Aggravated Assault",
            "category": "violent_crime",
            "race": "White",
            "count": 5000,
            "population": 1000000,
            "year": 2021,
        }
        passage = render_fbi_passage(row)
        assert "Aggravated Assault" in passage

    def test_contains_category(self):
        row = {
            "state_fips": "36",
            "offense": "Aggravated Assault",
            "category": "violent_crime",
            "race": "White",
            "count": 5000,
            "population": 1000000,
            "year": 2021,
        }
        passage = render_fbi_passage(row)
        assert "violent_crime" in passage

    def test_contains_race(self):
        row = {
            "state_fips": "36",
            "offense": "Aggravated Assault",
            "category": "violent_crime",
            "race": "White",
            "count": 5000,
            "population": 1000000,
            "year": 2021,
        }
        passage = render_fbi_passage(row)
        assert "White" in passage

    def test_per_100k_rate_calculated(self):
        row = {
            "state_fips": "36",
            "offense": "Aggravated Assault",
            "category": "violent_crime",
            "race": "White",
            "count": 5000,
            "population": 1000000,
            "year": 2021,
        }
        passage = render_fbi_passage(row)
        # 5000 / 1000000 * 100000 = 500.0 → rendered as "500.0 per 100,000 people"
        assert "500.0 per 100,000" in passage
