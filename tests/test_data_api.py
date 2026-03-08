import pytest
from httpx import ASGITransport, AsyncClient

from d4bl.app.api import app


@pytest.fixture
def mock_admin_user():
    """Mock an admin user for auth."""
    return {"sub": "test-admin-uuid", "email": "admin@test.com", "role": "admin"}


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_list_sources_requires_auth(client):
    resp = await client.get("/api/data/sources")
    assert resp.status_code == 401 or resp.status_code == 403


@pytest.mark.asyncio
async def test_create_source_schema():
    from d4bl.app.schemas import DataSourceCreate

    source = DataSourceCreate(
        name="Test API",
        source_type="api",
        config={"url": "https://example.com/api"},
    )
    assert source.name == "Test API"
    assert source.source_type == "api"


@pytest.mark.asyncio
async def test_create_source_invalid_type():
    from pydantic import ValidationError

    from d4bl.app.schemas import DataSourceCreate

    with pytest.raises(ValidationError):
        DataSourceCreate(
            name="Bad Source",
            source_type="invalid_type",
            config={},
        )
