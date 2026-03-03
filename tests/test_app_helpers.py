"""Tests for app-level helper functions."""
import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

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


class TestFetchResearchJob:
    @pytest.mark.asyncio
    async def test_returns_job_when_found(self):
        from d4bl.app.api import fetch_research_job

        mock_job = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_job
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await fetch_research_job(mock_db, uuid4())
        assert result is mock_job

    @pytest.mark.asyncio
    async def test_raises_404_when_not_found(self):
        from d4bl.app.api import fetch_research_job

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(HTTPException) as exc_info:
            await fetch_research_job(mock_db, uuid4())
        assert exc_info.value.status_code == 404
