"""Tests for JWT authentication and role-checking dependencies."""
from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import jwt
import pytest
from fastapi import HTTPException

from d4bl.app.auth import CurrentUser, get_current_user, require_admin

# Test JWT secret
TEST_SECRET = "test-secret-key-for-unit-tests"
TEST_USER_ID = str(uuid4())
TEST_EMAIL = "user@example.com"


def _make_token(sub: str = TEST_USER_ID, email: str = TEST_EMAIL, exp_offset: int = 3600) -> str:
    """Create a signed JWT for testing."""
    payload = {
        "sub": sub,
        "email": email,
        "exp": int(time.time()) + exp_offset,
        "aud": "authenticated",
    }
    return jwt.encode(payload, TEST_SECRET, algorithm="HS256")


def _make_request(token: str | None = None) -> MagicMock:
    """Create a mock FastAPI Request with optional Authorization header."""
    request = MagicMock()
    if token:
        request.headers = {"authorization": f"Bearer {token}"}
    else:
        request.headers = {}
    return request


@pytest.fixture
def mock_db():
    return AsyncMock()


@pytest.fixture(autouse=True)
def _patch_settings():
    """Patch settings to use test JWT secret."""
    mock_settings = MagicMock()
    mock_settings.supabase_jwt_secret = TEST_SECRET
    with patch("d4bl.app.auth.get_settings", return_value=mock_settings):
        yield


@pytest.mark.asyncio
async def test_get_current_user_valid_token(mock_db):
    """Valid JWT returns a CurrentUser."""
    token = _make_token()
    request = _make_request(token)

    with patch("d4bl.app.auth._fetch_user_role", new_callable=AsyncMock, return_value="user"):
        user = await get_current_user(request, mock_db)

    assert isinstance(user, CurrentUser)
    assert str(user.id) == TEST_USER_ID
    assert user.email == TEST_EMAIL
    assert user.role == "user"


@pytest.mark.asyncio
async def test_get_current_user_missing_header(mock_db):
    """Missing Authorization header raises 401."""
    request = _make_request(None)
    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(request, mock_db)
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user_expired_token(mock_db):
    """Expired JWT raises 401."""
    token = _make_token(exp_offset=-3600)
    request = _make_request(token)
    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(request, mock_db)
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_require_admin_with_admin_user():
    """require_admin returns user if role is admin."""
    user = CurrentUser(id=uuid4(), email="admin@test.com", role="admin")
    result = await require_admin(user)
    assert result.role == "admin"


@pytest.mark.asyncio
async def test_require_admin_with_regular_user():
    """require_admin raises 403 for non-admin users."""
    user = CurrentUser(id=uuid4(), email="user@test.com", role="user")
    with pytest.raises(HTTPException) as exc_info:
        await require_admin(user)
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_get_current_user_missing_sub(mock_db):
    """Token without sub claim raises 401."""
    payload = {"email": "test@test.com", "exp": int(time.time()) + 3600, "aud": "authenticated"}
    token = jwt.encode(payload, TEST_SECRET, algorithm="HS256")
    request = _make_request(token)
    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(request, mock_db)
    assert exc_info.value.status_code == 401
