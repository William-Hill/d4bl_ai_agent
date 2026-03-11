"""Tests for the Dagster auth proxy."""
from __future__ import annotations

import time
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import importlib.util
import sys
from pathlib import Path

import jwt
import pytest
from httpx import ASGITransport, AsyncClient

TEST_SECRET = "test-secret-key"
TEST_USER_ID = str(uuid4())

# Load auth_proxy from the dagster directory without conflicting with the
# installed dagster package.
_AUTH_PROXY_PATH = Path(__file__).resolve().parent.parent / "auth_proxy.py"


def _load_auth_proxy():
    spec = importlib.util.spec_from_file_location("auth_proxy", _AUTH_PROXY_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["auth_proxy"] = mod
    spec.loader.exec_module(mod)
    return mod


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


@pytest.fixture
def app(_env):
    # Load (or reload) to pick up env vars
    mod = _load_auth_proxy()
    return mod.app


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
            # Will fail to connect to upstream (no dagster running), but should attempt proxy
            resp = await client.get("/server_info", cookies={"dagster_token": token})
    # 502 is expected — proxy tried to reach upstream but nothing is running
    assert resp.status_code == 502


@pytest.mark.asyncio
async def test_set_token_endpoint(app):
    token = _make_token()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", follow_redirects=False
    ) as client:
        resp = await client.get(f"/auth/set-token?token={token}")
    assert resp.status_code == 307
    assert "dagster_token" in resp.headers.get("set-cookie", "")
