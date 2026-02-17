"""Shared test fixtures for D4BL tests."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture
def mock_db_session():
    """Mock async database session."""
    session = AsyncMock(spec=AsyncSession)
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.close = AsyncMock()
    return session


@pytest.fixture
def sample_job_id():
    """Return a consistent UUID for testing."""
    return uuid4()


@pytest.fixture
def sample_embedding():
    """Return a fake 1024-dimensional embedding vector."""
    return [0.1] * 1024


@pytest.fixture
def sample_crawl_results():
    """Sample crawl results matching the format from crawl_tools."""
    return {
        "query": "Mississippi NIL policy",
        "urls_crawled": ["https://example.com/nil-policy"],
        "results": [
            {
                "url": "https://example.com/nil-policy",
                "extracted_content": "Mississippi passed NIL legislation in 2021 allowing college athletes to profit from their name, image, and likeness.",
                "title": "Mississippi NIL Policy Overview",
                "description": "Overview of NIL policies in Mississippi",
            },
            {
                "url": "https://example.com/nil-impact",
                "extracted_content": "The impact of NIL on Black athletes in Mississippi has been significant, with disparities in endorsement opportunities.",
                "title": "NIL Impact on Black Athletes",
                "description": "Analysis of NIL policy impact",
            },
        ],
        "source_urls": [
            "https://example.com/nil-policy",
            "https://example.com/nil-impact",
        ],
        "success": True,
    }


@pytest.fixture
def mock_ollama_embedding(sample_embedding):
    """Mock Ollama embedding API response."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"embedding": sample_embedding}
    return mock_response
