"""Tests for the Dagster auth proxy."""
from __future__ import annotations

import importlib.util
import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import jwt
import pytest
from httpx import ASGITransport, AsyncClient

TEST_SECRET = "test-secret-key"
TEST_USER_ID = str(uuid4())

# Load auth_proxy from the dagster directory without conflicting with the
# installed dagster package.
_AUTH_PROXY_PATH = Path(__file__).resolve().parent.parent.parent / "dagster" / "auth_proxy.py"


@pytest.fixture
def _auth_proxy_module():
    spec = importlib.util.spec_from_file_location("auth_proxy", _AUTH_PROXY_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["auth_proxy"] = mod
    spec.loader.exec_module(mod)
    yield mod
    sys.modules.pop("auth_proxy", None)


def _make_token(
    sub: str = TEST_USER_ID,
    email: str = "admin@test.com",
    exp_offset: int = 3600,
) -> str:
    return jwt.encode(
        {"sub": sub, "email": email, "exp": int(time.time()) + exp_offset, "aud": "authenticated"},
        TEST_SECRET,
        algorithm="HS256",
    )


@pytest.fixture
def _env(monkeypatch):
    monkeypatch.setenv("SUPABASE_JWT_SECRET", TEST_SECRET)
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "test-anon-key")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "http://localhost:3000")


@pytest.fixture
def app(_env, _auth_proxy_module):
    return _auth_proxy_module.app


@pytest.mark.asyncio
async def test_no_cookie_returns_login_page(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/")
    assert resp.status_code == 200
    assert "Sign in" in resp.text


@pytest.mark.asyncio
async def test_invalid_token_returns_login_page(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/", cookies={"dagster_token": "bad-token"})
    assert resp.status_code == 200
    assert "Sign in" in resp.text


@pytest.mark.asyncio
async def test_expired_token_returns_login_page(app):
    token = _make_token(exp_offset=-3600)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/", cookies={"dagster_token": token})
    assert resp.status_code == 200
    assert "Sign in" in resp.text


@pytest.mark.asyncio
async def test_non_admin_returns_403(app):
    token = _make_token()
    with patch("auth_proxy._check_admin", new_callable=AsyncMock, return_value=False):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/", cookies={"dagster_token": token})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_proxies_request(app):
    token = _make_token()
    with patch("auth_proxy._check_admin", new_callable=AsyncMock, return_value=True):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/server_info", cookies={"dagster_token": token})
    # 502 is expected — proxy tried to reach upstream but nothing is running
    assert resp.status_code == 502


@pytest.mark.asyncio
async def test_set_token_endpoint(app):
    token = _make_token()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", follow_redirects=False
    ) as client:
        resp = await client.post(
            "/auth/set-token",
            json={"token": token},
        )
    assert resp.status_code == 200
    assert "dagster_token" in resp.headers.get("set-cookie", "")


@pytest.mark.asyncio
async def test_set_token_cors_preflight(app):
    """OPTIONS preflight from an allowed origin returns CORS headers."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.options(
            "/auth/set-token",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
            },
        )
    assert resp.status_code == 204
    assert resp.headers["Access-Control-Allow-Origin"] == "http://localhost:3000"
    assert resp.headers["Access-Control-Allow-Credentials"] == "true"
    assert "POST" in resp.headers["Access-Control-Allow-Methods"]


@pytest.mark.asyncio
async def test_set_token_cross_origin_post(app):
    """Cross-origin POST with credentials sets cookie and returns CORS headers."""
    token = _make_token()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", follow_redirects=False
    ) as client:
        resp = await client.post(
            "/auth/set-token",
            json={"token": token},
            headers={"Origin": "http://localhost:3000"},
        )
    assert resp.status_code == 200
    assert "dagster_token" in resp.headers.get("set-cookie", "")
    assert resp.headers["Access-Control-Allow-Origin"] == "http://localhost:3000"
    assert resp.headers["Access-Control-Allow-Credentials"] == "true"


@pytest.mark.asyncio
async def test_set_token_disallowed_origin(app):
    """Cross-origin POST from an unknown origin does not get CORS headers."""
    token = _make_token()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", follow_redirects=False
    ) as client:
        resp = await client.post(
            "/auth/set-token",
            json={"token": token},
            headers={"Origin": "http://evil.example.com"},
        )
    assert resp.status_code == 200
    assert "Access-Control-Allow-Origin" not in resp.headers


@pytest.mark.asyncio
async def test_logout_clears_cookie(app):
    """Logout clears the cookie and redirects."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", follow_redirects=False
    ) as client:
        resp = await client.get("/auth/logout")
    assert resp.status_code == 307
    cookie = resp.headers.get("set-cookie", "")
    assert "dagster_token" in cookie
    # Cookie should be expired (max-age=0 or 'expires' in past)
    assert 'max-age=0' in cookie.lower() or "expires" in cookie.lower()


@pytest.mark.asyncio
async def test_healthz_unhealthy(app):
    """Healthz returns 503 when upstream Dagster is unreachable."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/healthz")
    # No Dagster webserver running in tests, so upstream is unhealthy
    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_set_token_invalid_json(app):
    """Invalid JSON body returns 400."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/auth/set-token",
            content=b"not-json",
            headers={"Content-Type": "application/json"},
        )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_set_token_missing_token(app):
    """Missing token field returns 400."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post("/auth/set-token", json={"foo": "bar"})
    assert resp.status_code == 400
