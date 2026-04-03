"""Tests for StateSummary model and aggregation functions."""

import pytest
from sqlalchemy import inspect

from d4bl.infra.state_summary import StateSummary

# ---------------------------------------------------------------------------
# Model structure tests
# ---------------------------------------------------------------------------


class TestStateSummaryModel:
    """Verify the SQLAlchemy model has the expected schema."""

    def test_has_all_required_columns(self):
        mapper = inspect(StateSummary)
        column_names = {col.key for col in mapper.column_attrs}
        expected = {
            "id",
            "source",
            "state_fips",
            "state_name",
            "metric",
            "race",
            "year",
            "value",
            "sample_size",
        }
        assert expected == column_names

    def test_tablename(self):
        assert StateSummary.__tablename__ == "state_summary"

    def test_unique_constraint_exists(self):
        constraints = StateSummary.__table__.constraints
        unique_names = {
            c.name
            for c in constraints
            if hasattr(c, "columns") and c.name and c.name.startswith("uq_")
        }
        assert "uq_state_summary_source_state_metric_race_year" in unique_names

    def test_unique_constraint_columns(self):
        """The unique constraint covers the right columns."""
        for c in StateSummary.__table__.constraints:
            if getattr(c, "name", None) == ("uq_state_summary_source_state_metric_race_year"):
                col_names = {col.name for col in c.columns}
                assert col_names == {
                    "source",
                    "state_fips",
                    "metric",
                    "race",
                    "year",
                }
                return
        pytest.fail("Unique constraint not found")

    def test_race_default_is_total(self):
        col = StateSummary.__table__.c.race
        assert col.default.arg == "total"

    def test_sample_size_nullable(self):
        col = StateSummary.__table__.c.sample_size
        assert col.nullable is True

    def test_value_not_nullable(self):
        col = StateSummary.__table__.c.value
        assert col.nullable is False


# ---------------------------------------------------------------------------
# Aggregation function tests
# ---------------------------------------------------------------------------


class TestAggregateEpa:
    """Test population-weighted EPA aggregation."""

    def test_weighted_average_two_tracts(self):
        from scripts.ingestion.aggregate_state_summaries import aggregate_epa

        rows = [
            {
                "state_fips": "01",
                "state_name": "Alabama",
                "indicator": "PM2.5",
                "year": 2023,
                "raw_value": 80.0,
                "population": 1000,
            },
            {
                "state_fips": "01",
                "state_name": "Alabama",
                "indicator": "PM2.5",
                "year": 2023,
                "raw_value": 40.0,
                "population": 3000,
            },
        ]
        result = aggregate_epa(rows)
        assert len(result) == 1
        r = result[0]
        assert r["source"] == "epa"
        assert r["state_fips"] == "01"
        assert r["state_name"] == "Alabama"
        assert r["metric"] == "PM2.5"
        assert r["race"] == "total"
        assert r["year"] == 2023
        # weighted avg = (80*1000 + 40*3000) / (1000+3000) = 200000/4000 = 50
        assert r["value"] == pytest.approx(50.0)
        assert r["sample_size"] == 4000

    def test_multiple_states(self):
        from scripts.ingestion.aggregate_state_summaries import aggregate_epa

        rows = [
            {
                "state_fips": "01",
                "state_name": "Alabama",
                "indicator": "Ozone",
                "year": 2023,
                "raw_value": 10.0,
                "population": 500,
            },
            {
                "state_fips": "02",
                "state_name": "Alaska",
                "indicator": "Ozone",
                "year": 2023,
                "raw_value": 20.0,
                "population": 300,
            },
        ]
        result = aggregate_epa(rows)
        assert len(result) == 2
        by_state = {r["state_fips"]: r for r in result}
        assert by_state["01"]["value"] == pytest.approx(10.0)
        assert by_state["02"]["value"] == pytest.approx(20.0)

    def test_empty_rows(self):
        from scripts.ingestion.aggregate_state_summaries import aggregate_epa

        assert aggregate_epa([]) == []


class TestAggregateUsda:
    """Test population-weighted USDA aggregation."""

    def test_weighted_average(self):
        from scripts.ingestion.aggregate_state_summaries import aggregate_usda

        rows = [
            {
                "state_fips": "06",
                "state_name": "California",
                "indicator": "low_access_1mi",
                "year": 2019,
                "value": 0.3,
                "population": 2000,
            },
            {
                "state_fips": "06",
                "state_name": "California",
                "indicator": "low_access_1mi",
                "year": 2019,
                "value": 0.7,
                "population": 2000,
            },
        ]
        result = aggregate_usda(rows)
        assert len(result) == 1
        assert result[0]["value"] == pytest.approx(0.5)
        assert result[0]["sample_size"] == 4000


class TestAggregateCensusDemographics:
    """Test Census population summation."""

    def test_sums_populations(self):
        from scripts.ingestion.aggregate_state_summaries import (
            aggregate_census_demographics,
        )

        rows = [
            {
                "state_fips": "01",
                "state_name": "Alabama",
                "race": "total",
                "year": 2020,
                "population": 3000,
            },
            {
                "state_fips": "01",
                "state_name": "Alabama",
                "race": "total",
                "year": 2020,
                "population": 2000,
            },
            {
                "state_fips": "01",
                "state_name": "Alabama",
                "race": "black",
                "year": 2020,
                "population": 1500,
            },
        ]
        result = aggregate_census_demographics(rows)
        by_race = {r["race"]: r for r in result}

        assert by_race["total"]["value"] == 5000.0
        assert by_race["total"]["sample_size"] == 5000
        assert by_race["black"]["value"] == 1500.0
        # sample_size for non-total race should be state total
        assert by_race["black"]["sample_size"] == 5000

    def test_source_field(self):
        from scripts.ingestion.aggregate_state_summaries import (
            aggregate_census_demographics,
        )

        rows = [
            {
                "state_fips": "01",
                "state_name": "Alabama",
                "race": "total",
                "year": 2020,
                "population": 100,
            },
        ]
        result = aggregate_census_demographics(rows)
        assert result[0]["source"] == "census-demographics"
        assert result[0]["metric"] == "population"


class TestAggregateDoe:
    """Test enrollment-weighted DOE aggregation."""

    def test_extracts_year_from_school_year(self):
        from scripts.ingestion.aggregate_state_summaries import aggregate_doe

        rows = [
            {
                "state": "CA",
                "state_name": "California",
                "metric": "suspensions",
                "race": "black",
                "school_year": "2020-2021",
                "value": 5.0,
                "total_enrollment": 1000,
            },
        ]
        result = aggregate_doe(rows)
        assert result[0]["year"] == 2020

    def test_enrollment_weighted(self):
        from scripts.ingestion.aggregate_state_summaries import aggregate_doe

        rows = [
            {
                "state": "CA",
                "state_name": "California",
                "metric": "suspensions",
                "race": "total",
                "school_year": "2020-2021",
                "value": 10.0,
                "total_enrollment": 1000,
            },
            {
                "state": "CA",
                "state_name": "California",
                "metric": "suspensions",
                "race": "total",
                "school_year": "2020-2021",
                "value": 20.0,
                "total_enrollment": 3000,
            },
        ]
        result = aggregate_doe(rows)
        assert len(result) == 1
        # (10*1000 + 20*3000) / 4000 = 70000/4000 = 17.5
        assert result[0]["value"] == pytest.approx(17.5)
        assert result[0]["sample_size"] == 4000
        assert result[0]["source"] == "doe"

    def test_state_fips_is_numeric_code_not_abbreviation(self):
        """state_fips must be a zero-padded numeric FIPS code, not a state abbreviation."""
        from scripts.ingestion.aggregate_state_summaries import aggregate_doe

        rows = [
            {
                "state": "CA",
                "state_name": "California",
                "metric": "suspensions",
                "race": "total",
                "school_year": "2020-2021",
                "value": 5.0,
                "total_enrollment": 1000,
            },
            {
                "state": "TX",
                "state_name": "Texas",
                "metric": "suspensions",
                "race": "total",
                "school_year": "2020-2021",
                "value": 3.0,
                "total_enrollment": 2000,
            },
        ]
        result = aggregate_doe(rows)
        by_name = {r["state_name"]: r for r in result}

        assert by_name["California"]["state_fips"] == "06", (
            "Expected FIPS '06' for California, got abbreviation or wrong code"
        )
        assert by_name["Texas"]["state_fips"] == "48", (
            "Expected FIPS '48' for Texas, got abbreviation or wrong code"
        )
        # Ensure no raw abbreviations leaked through
        for r in result:
            assert r["state_fips"].isdigit(), (
                f"state_fips {r['state_fips']!r} is not a numeric FIPS code"
            )


class TestSourceNameMap:
    """Verify the source name mapping used by run_aggregation."""

    def test_census_decennial_maps_correctly(self):
        from scripts.ingestion.aggregate_state_summaries import _SOURCE_NAME_MAP

        assert _SOURCE_NAME_MAP["census_decennial"] == "census-demographics"

    def test_all_expected_sources(self):
        from scripts.ingestion.aggregate_state_summaries import _SOURCE_NAME_MAP

        assert set(_SOURCE_NAME_MAP.keys()) == {
            "epa",
            "usda",
            "census_decennial",
            "doe",
        }