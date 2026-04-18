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


class TestMappingConfig:
    def test_required_fields_only(self):
        from d4bl.services.datasource_processing.parser import MappingConfig

        m = MappingConfig(
            geo_column="county_fips",
            metric_value_column="rate",
            metric_name="eviction_rate",
        )
        assert m.race_column is None
        assert m.year_column is None

    def test_metric_name_validated_in_post_init(self):
        from d4bl.services.datasource_processing.parser import MappingConfig

        with pytest.raises(ValueError):
            MappingConfig(
                geo_column="county_fips",
                metric_value_column="rate",
                metric_name="Bad Name",
            )


class TestDatasourceParseError:
    def test_has_structured_detail(self):
        from d4bl.services.datasource_processing.parser import DatasourceParseError

        err = DatasourceParseError(
            "missing columns",
            detail={"missing_columns": ["race"]},
        )
        assert err.detail == {"missing_columns": ["race"]}
        assert "missing columns" in str(err)


class TestReadCsvBytes:
    def test_basic_csv(self):
        from d4bl.services.datasource_processing.parser import read_csv_bytes

        raw = b"county_fips,rate\n13121,14.3\n13089,9.1\n"
        header, rows = read_csv_bytes(raw)
        assert header == ["county_fips", "rate"]
        assert rows == [{"county_fips": "13121", "rate": "14.3"},
                        {"county_fips": "13089", "rate": "9.1"}]

    def test_utf8_with_bom(self):
        from d4bl.services.datasource_processing.parser import read_csv_bytes

        raw = "\ufeffcounty_fips,rate\n13121,14.3\n".encode("utf-8")
        header, _rows = read_csv_bytes(raw)
        # BOM must not contaminate the first header name.
        assert header == ["county_fips", "rate"]

    def test_trims_header_whitespace(self):
        from d4bl.services.datasource_processing.parser import read_csv_bytes

        raw = b" county_fips , rate \n13121, 14.3\n"
        header, rows = read_csv_bytes(raw)
        assert header == ["county_fips", "rate"]
        assert rows[0]["county_fips"] == "13121"
        # Cell whitespace preserved so the value-column coercion can strip it.
        assert rows[0]["rate"] == " 14.3"

    def test_empty_csv_raises(self):
        from d4bl.services.datasource_processing.parser import (
            DatasourceParseError,
            read_csv_bytes,
        )

        with pytest.raises(DatasourceParseError):
            read_csv_bytes(b"")
