"""Tests for datasource upload parser + validation."""

import io

import pytest

from d4bl.services.datasource_processing.validation import (
    coerce_numeric,
    coerce_year,
    derive_state_fips,
    validate_metric_name,
)


class TestValidateMetricName:
    def test_valid_snake_case(self):
        assert validate_metric_name("eviction_filing_rate") == "eviction_filing_rate"

    def test_valid_with_digits(self):
        assert validate_metric_name("poverty_rate_2023") == "poverty_rate_2023"

    @pytest.mark.parametrize("bad", ["", "UPPER", "has space", "with-dash", "a" * 65, "!bang"])
    def test_rejects(self, bad):
        with pytest.raises(ValueError):
            validate_metric_name(bad)


class TestDeriveStateFips:
    def test_state_fips(self):
        assert derive_state_fips("13") == "13"

    def test_county_fips(self):
        assert derive_state_fips("13121") == "13"

    def test_tract_fips(self):
        assert derive_state_fips("13121020100") == "13"

    def test_strips_whitespace(self):
        assert derive_state_fips(" 13121 ") == "13"

    def test_accepts_int_like(self):
        # Single-digit states (e.g. "6" for CA) get zero-padded.
        assert derive_state_fips("6") == "06"

    def test_rejects_non_numeric(self):
        with pytest.raises(ValueError):
            derive_state_fips("CA")

    def test_rejects_empty(self):
        with pytest.raises(ValueError):
            derive_state_fips("")


class TestCoerceNumeric:
    def test_plain_float(self):
        assert coerce_numeric("14.3") == 14.3

    def test_plain_int(self):
        assert coerce_numeric("42") == 42.0

    def test_with_percent(self):
        assert coerce_numeric("14.3%") == 14.3

    def test_with_commas(self):
        assert coerce_numeric("1,234.5") == 1234.5

    def test_with_whitespace(self):
        assert coerce_numeric("  14.3  ") == 14.3

    @pytest.mark.parametrize("bad", ["", "NaN", "abc", "--", "14.3.0"])
    def test_rejects(self, bad):
        with pytest.raises(ValueError):
            coerce_numeric(bad)


class TestCoerceYear:
    def test_valid_year(self):
        assert coerce_year("2023") == 2023

    def test_int_year(self):
        assert coerce_year(2023) == 2023

    @pytest.mark.parametrize("bad", ["", "20", "abc", "1899", "3000"])
    def test_rejects(self, bad):
        with pytest.raises(ValueError):
            coerce_year(bad)
