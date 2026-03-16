"""Shared test fixtures for D4BL tests."""

from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from d4bl.app.auth import CurrentUser, get_current_user

TEST_USER_ID = "00000000-0000-0000-0000-000000000001"
TEST_ADMIN_ID = "00000000-0000-0000-0000-000000000002"

MOCK_USER = CurrentUser(
    id=UUID(TEST_USER_ID), email="user@test.com", role="user"
)
MOCK_ADMIN = CurrentUser(
    id=UUID(TEST_ADMIN_ID), email="admin@test.com", role="admin"
)


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


@pytest.fixture(autouse=True)
def _clear_explore_cache():
    """Clear the explore endpoint cache and reset freshness throttle before each test."""
    import d4bl.app.api as _api_mod
    from d4bl.app.cache import explore_cache

    explore_cache.clear()
    _api_mod._last_freshness_check = 0.0
    yield
    explore_cache.clear()
    _api_mod._last_freshness_check = 0.0


@pytest.fixture
def override_auth():
    """Override get_current_user dependency to bypass JWT auth in tests.

    Yields the app so tests can add further overrides before making requests.
    Saves and restores the full override map on teardown to avoid leaks.
    """
    from d4bl.app.api import app

    original_overrides = app.dependency_overrides.copy()
    app.dependency_overrides[get_current_user] = lambda: MOCK_USER
    try:
        yield app
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(original_overrides)


@pytest.fixture
def override_admin_auth():
    """Override get_current_user with an admin user for tests.

    Saves and restores the full override map on teardown to avoid leaks.
    """
    from d4bl.app.api import app

    original_overrides = app.dependency_overrides.copy()
    app.dependency_overrides[get_current_user] = lambda: MOCK_ADMIN
    try:
        yield app
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(original_overrides)
