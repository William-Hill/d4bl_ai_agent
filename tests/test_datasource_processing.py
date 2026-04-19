"""Tests for datasource upload parser + validation."""

import math

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

    def test_four_digit_county_fips_gets_leading_zero(self):
        # Excel may drop a leading 0 on 5-digit county FIPS (e.g. 01001 → "1001").
        assert derive_state_fips("1001") == "01"

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

    def test_native_int_float_passthrough(self):
        assert coerce_numeric(3) == 3.0
        assert coerce_numeric(2.5) == 2.5

    def test_rejects_non_finite(self):
        with pytest.raises(ValueError):
            coerce_numeric(float("inf"))
        with pytest.raises(ValueError):
            coerce_numeric(float("-inf"))
        with pytest.raises(ValueError):
            coerce_numeric(math.nan)


class TestCoerceYear:
    def test_valid_year(self):
        assert coerce_year("2023") == 2023

    def test_int_year(self):
        assert coerce_year(2023) == 2023

    def test_rejects_boolean(self):
        with pytest.raises(ValueError):
            coerce_year(True)
        with pytest.raises(ValueError):
            coerce_year(False)

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


class TestReadXlsxBytes:
    def test_basic_xlsx(self, make_xlsx_bytes):
        from d4bl.services.datasource_processing.parser import read_xlsx_bytes

        raw = make_xlsx_bytes(
            ["county_fips", "rate"],
            [["13121", 14.3], ["13089", 9.1]],
        )
        header, rows = read_xlsx_bytes(raw)
        assert header == ["county_fips", "rate"]
        assert rows[0]["county_fips"] == "13121"
        assert rows[0]["rate"] in ("14.3", 14.3)

    def test_skips_empty_rows(self, make_xlsx_bytes):
        from d4bl.services.datasource_processing.parser import read_xlsx_bytes

        raw = make_xlsx_bytes(
            ["county_fips", "rate"],
            [["13121", 14.3], [None, None], ["13089", 9.1]],
        )
        _header, rows = read_xlsx_bytes(raw)
        assert len(rows) == 2

    def test_empty_workbook_raises(self, make_xlsx_bytes):
        from d4bl.services.datasource_processing.parser import (
            DatasourceParseError,
            read_xlsx_bytes,
        )

        raw = make_xlsx_bytes([], [])
        with pytest.raises(DatasourceParseError):
            read_xlsx_bytes(raw)


def _make_mapping(**overrides):
    from d4bl.services.datasource_processing.parser import MappingConfig

    defaults = dict(
        geo_column="county_fips",
        metric_value_column="rate",
        metric_name="eviction_rate",
        race_column=None,
        year_column=None,
        data_year=2023,
    )
    defaults.update(overrides)
    return MappingConfig(**defaults)


class TestParseDatasourceFile:
    def test_valid_csv_without_race_or_year(self):
        from d4bl.services.datasource_processing.parser import parse_datasource_file

        raw = b"county_fips,rate\n" + b"\n".join(
            f"{13000 + i},{i * 0.5}".encode() for i in range(15)
        )
        result = parse_datasource_file(raw, ".csv", _make_mapping())
        assert result.row_count == 15
        assert result.dropped_counts == {"bad_fips": 0, "non_numeric": 0, "bad_year": 0}
        assert result.normalized_rows[0]["state_fips"] == "13"
        assert result.normalized_rows[0]["year"] == 2023
        assert result.normalized_rows[0]["race"] is None
        assert len(result.preview_rows) == min(20, result.row_count)

    def test_valid_csv_with_race_and_year(self):
        from d4bl.services.datasource_processing.parser import parse_datasource_file

        lines = ["county_fips,race,year,rate"]
        for i in range(12):
            lines.append(f"{13000 + i},Black,2023,{i * 0.5}")
        raw = "\n".join(lines).encode()
        result = parse_datasource_file(
            raw, ".csv",
            _make_mapping(race_column="race", year_column="year"),
        )
        assert all(r["race"] == "Black" for r in result.normalized_rows)
        assert all(r["year"] == 2023 for r in result.normalized_rows)

    def test_missing_declared_column_raises(self):
        from d4bl.services.datasource_processing.parser import (
            DatasourceParseError,
            parse_datasource_file,
        )

        raw = b"county_fips,rate\n13121,14.3\n"
        with pytest.raises(DatasourceParseError) as exc_info:
            parse_datasource_file(raw, ".csv", _make_mapping(race_column="ethnicity"))
        assert "missing_columns" in exc_info.value.detail
        assert "ethnicity" in exc_info.value.detail["missing_columns"]

    def test_header_only_csv_raises(self):
        from d4bl.services.datasource_processing.parser import (
            DatasourceParseError,
            parse_datasource_file,
        )

        raw = b"county_fips,rate\n"
        with pytest.raises(DatasourceParseError) as exc_info:
            parse_datasource_file(raw, ".csv", _make_mapping())
        assert exc_info.value.detail.get("reason") == "no_data_rows"

    def test_many_bad_fips_raises(self):
        from d4bl.services.datasource_processing.parser import (
            DatasourceParseError,
            parse_datasource_file,
        )

        lines = ["county_fips,rate"]
        # 3 good, 10 bad → >10% bad
        for i in range(3):
            lines.append(f"{13000 + i},{i}")
        for i in range(10):
            lines.append(f"X{i},{i}")
        raw = "\n".join(lines).encode()
        with pytest.raises(DatasourceParseError) as exc_info:
            parse_datasource_file(raw, ".csv", _make_mapping())
        assert exc_info.value.detail["dropped"]["reason"] == "bad_fips"

    def test_few_bad_fips_drops_silently(self):
        from d4bl.services.datasource_processing.parser import parse_datasource_file

        lines = ["county_fips,rate"]
        for i in range(20):
            lines.append(f"{13000 + i},{i}")
        lines.append("XX,99")  # 1 bad out of 21 → <10%
        raw = "\n".join(lines).encode()
        result = parse_datasource_file(raw, ".csv", _make_mapping())
        assert result.row_count == 20
        assert result.dropped_counts["bad_fips"] == 1

    def test_many_non_numeric_values_raises(self):
        from d4bl.services.datasource_processing.parser import (
            DatasourceParseError,
            parse_datasource_file,
        )

        lines = ["county_fips,rate"]
        for i in range(5):
            lines.append(f"{13000 + i},{i}")
        for i in range(10):
            lines.append(f"{13100 + i},NaN")
        raw = "\n".join(lines).encode()
        with pytest.raises(DatasourceParseError) as exc_info:
            parse_datasource_file(raw, ".csv", _make_mapping())
        assert exc_info.value.detail["dropped"]["reason"] == "non_numeric"

    def test_too_few_valid_rows_raises(self):
        from d4bl.services.datasource_processing.parser import (
            DatasourceParseError,
            parse_datasource_file,
        )

        raw = b"county_fips,rate\n13121,14.3\n13089,9.1\n"
        with pytest.raises(DatasourceParseError) as exc_info:
            parse_datasource_file(raw, ".csv", _make_mapping())
        assert exc_info.value.detail["reason"] == "too_few_rows"

    def test_percent_and_comma_values_coerce(self):
        from d4bl.services.datasource_processing.parser import parse_datasource_file

        lines = ["county_fips,rate"]
        for i in range(12):
            lines.append(f"{13000 + i},\"1,234.{i}%\"")
        raw = "\n".join(lines).encode()
        result = parse_datasource_file(raw, ".csv", _make_mapping())
        assert result.normalized_rows[0]["value"] > 1000

    def test_unsupported_extension_raises(self):
        from d4bl.services.datasource_processing.parser import (
            DatasourceParseError,
            parse_datasource_file,
        )

        with pytest.raises(DatasourceParseError):
            parse_datasource_file(b"...", ".txt", _make_mapping())

    def test_xlsx_input(self, make_xlsx_bytes):
        from d4bl.services.datasource_processing.parser import parse_datasource_file

        header = ["county_fips", "rate"]
        rows = [[f"{13000 + i}", i * 0.5] for i in range(15)]
        raw = make_xlsx_bytes(header, rows)
        result = parse_datasource_file(raw, ".xlsx", _make_mapping())
        assert result.row_count == 15
