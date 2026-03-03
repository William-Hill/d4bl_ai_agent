"""Tests for app-level helper functions."""
import pytest
from fastapi import HTTPException

from d4bl.app.api import parse_job_uuid


class TestParseJobUuid:
    def test_valid_uuid(self):
        result = parse_job_uuid("550e8400-e29b-41d4-a716-446655440000")
        assert str(result) == "550e8400-e29b-41d4-a716-446655440000"

    def test_invalid_uuid_raises_http_400(self):
        with pytest.raises(HTTPException) as exc_info:
            parse_job_uuid("not-a-uuid")
        assert exc_info.value.status_code == 400
        assert "Invalid job ID format" in exc_info.value.detail

    def test_empty_string_raises_http_400(self):
        with pytest.raises(HTTPException) as exc_info:
            parse_job_uuid("")
        assert exc_info.value.status_code == 400
