"""Unit tests for file upload assets and sensor."""

import csv
import json
import os
from pathlib import Path

import pytest
from d4bl_pipelines.assets.files.file_upload import (
    ALLOWED_EXTENSIONS,
    _file_extension,
    _latest_file,
    _parse_file,
    build_file_upload_assets,
)
from d4bl_pipelines.sensors import file_upload_sensor

# ── helpers ──────────────────────────────────────────────────


def _write_csv(path: Path, rows: list[dict]) -> Path:
    filepath = path / "test.csv"
    with open(filepath, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    return filepath


def _write_json(path: Path, data: list[dict]) -> Path:
    filepath = path / "test.json"
    with open(filepath, "w") as f:
        json.dump(data, f)
    return filepath


# ── _file_extension ──────────────────────────────────────────


class TestFileExtension:
    def test_csv(self):
        assert _file_extension("data.csv") == "csv"

    def test_xlsx(self):
        assert _file_extension("report.XLSX") == "xlsx"

    def test_json(self):
        assert _file_extension("payload.JSON") == "json"

    def test_no_extension(self):
        assert _file_extension("README") == ""

    def test_dotfile(self):
        assert _file_extension(".hidden") == ""


# ── _parse_file ──────────────────────────────────────────────


class TestParseFile:
    def test_parse_csv(self, tmp_path):
        rows = [{"name": "Alice", "age": "30"},
                {"name": "Bob", "age": "25"}]
        filepath = _write_csv(tmp_path, rows)
        parsed, fmt = _parse_file(filepath)
        assert fmt == "csv"
        assert len(parsed) == 2
        assert parsed[0]["name"] == "Alice"

    def test_parse_json_list(self, tmp_path):
        data = [{"x": 1}, {"x": 2}]
        filepath = _write_json(tmp_path, data)
        parsed, fmt = _parse_file(filepath)
        assert fmt == "json"
        assert len(parsed) == 2
        assert parsed[0]["x"] == 1

    def test_parse_json_with_data_key(self, tmp_path):
        filepath = tmp_path / "wrapped.json"
        filepath.write_text(json.dumps({"data": [{"a": 1}]}))
        parsed, fmt = _parse_file(filepath)
        assert fmt == "json"
        assert len(parsed) == 1

    def test_parse_json_single_object(self, tmp_path):
        filepath = tmp_path / "single.json"
        filepath.write_text(json.dumps({"key": "val"}))
        parsed, fmt = _parse_file(filepath)
        assert fmt == "json"
        assert len(parsed) == 1
        assert parsed[0]["key"] == "val"

    def test_parse_unsupported_format(self, tmp_path):
        filepath = tmp_path / "data.xml"
        filepath.write_text("<root/>")
        with pytest.raises(ValueError, match="Unsupported"):
            _parse_file(filepath)


# ── _latest_file ─────────────────────────────────────────────


class TestLatestFile:
    def test_returns_none_when_dir_missing(self, tmp_path):
        assert _latest_file(tmp_path / "nonexistent") is None

    def test_returns_none_when_empty(self, tmp_path):
        assert _latest_file(tmp_path) is None

    def test_returns_most_recent(self, tmp_path):
        old = tmp_path / "old.csv"
        old.write_text("a,b\n1,2")
        new = tmp_path / "new.csv"
        new.write_text("x,y\n3,4")
        # Ensure different mtime
        os.utime(old, (1000, 1000))
        os.utime(new, (2000, 2000))
        result = _latest_file(tmp_path)
        assert result is not None
        assert result.name == "new.csv"

    def test_ignores_unsupported_extensions(self, tmp_path):
        txt = tmp_path / "notes.txt"
        txt.write_text("hello")
        assert _latest_file(tmp_path) is None


# ── build_file_upload_assets ─────────────────────────────────


class TestBuildFileUploadAssets:
    def test_returns_empty_for_non_file_upload(self):
        sources = [
            {"id": "abc", "name": "Census", "source_type": "api"}
        ]
        assert build_file_upload_assets(sources) == []

    def test_returns_asset_for_file_upload_source(self):
        sources = [
            {
                "id": "test-src-1",
                "name": "Test Upload",
                "source_type": "file_upload",
                "config": {},
            }
        ]
        assets = build_file_upload_assets(sources)
        assert len(assets) == 1

    def test_multiple_sources(self):
        sources = [
            {
                "id": "src-a",
                "name": "A",
                "source_type": "file_upload",
            },
            {
                "id": "src-b",
                "name": "B",
                "source_type": "file_upload",
            },
            {
                "id": "src-c",
                "name": "C",
                "source_type": "api",
            },
        ]
        assets = build_file_upload_assets(sources)
        assert len(assets) == 2

    def test_asset_has_correct_group(self):
        sources = [
            {
                "id": "grp-test",
                "name": "G",
                "source_type": "file_upload",
            }
        ]
        assets = build_file_upload_assets(sources)
        # Dagster asset group is stored in spec
        spec = assets[0].specs_by_key
        for spec_obj in spec.values():
            assert spec_obj.group_name == "files"


# ── file_upload_sensor import ────────────────────────────────


class TestSensorImport:
    def test_sensor_is_importable(self):
        assert file_upload_sensor is not None

    def test_sensor_has_name(self):
        assert file_upload_sensor.name == "file_upload_sensor"


# ── file type validation constants ───────────────────────────


class TestAllowedExtensions:
    def test_csv_allowed(self):
        assert "csv" in ALLOWED_EXTENSIONS

    def test_xlsx_allowed(self):
        assert "xlsx" in ALLOWED_EXTENSIONS

    def test_json_allowed(self):
        assert "json" in ALLOWED_EXTENSIONS

    def test_txt_not_allowed(self):
        assert "txt" not in ALLOWED_EXTENSIONS

    def test_xml_not_allowed(self):
        assert "xml" not in ALLOWED_EXTENSIONS
