"""Tests for auth-protected API endpoints."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import jwt
import pytest
from fastapi.testclient import TestClient

TEST_SECRET = "test-jwt-secret"
TEST_USER_ID = str(uuid4())


def _make_token(sub: str, email: str = "test@example.com") -> str:
    payload = {
        "sub": sub,
        "email": email,
        "exp": int(time.time()) + 3600,
        "aud": "authenticated",
    }
    return jwt.encode(payload, TEST_SECRET, algorithm="HS256")



def test_research_endpoint_requires_auth(_patch_settings):
    """POST /api/research without a token returns 401."""
    from d4bl.app.api import app

    client = TestClient(app, raise_server_exceptions=False)
    response = client.post("/api/research", json={"query": "test"})
    assert response.status_code == 401


def test_jobs_endpoint_requires_auth(_patch_settings):
    """GET /api/jobs without a token returns 401."""
    from d4bl.app.api import app

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/api/jobs")
    assert response.status_code == 401


def test_job_status_endpoint_requires_auth(_patch_settings):
    """GET /api/jobs/{job_id} without a token returns 401."""
    from d4bl.app.api import app

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get(f"/api/jobs/{uuid4()}")
    assert response.status_code == 401


def test_evaluations_endpoint_requires_auth(_patch_settings):
    """GET /api/evaluations without a token returns 401."""
    from d4bl.app.api import app

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/api/evaluations")
    assert response.status_code == 401


def test_vector_search_endpoint_requires_auth(_patch_settings):
    """POST /api/vector/search without a token returns 401."""
    from d4bl.app.api import app

    client = TestClient(app, raise_server_exceptions=False)
    response = client.post("/api/vector/search", json={"query": "test"})
    assert response.status_code == 401


def test_query_endpoint_requires_auth(_patch_settings):
    """POST /api/query without a token returns 401."""
    from d4bl.app.api import app

    client = TestClient(app, raise_server_exceptions=False)
    response = client.post("/api/query", json={"question": "test"})
    assert response.status_code == 401


def test_indicators_endpoint_requires_auth(_patch_settings):
    """GET /api/explore/indicators without a token returns 401."""
    from d4bl.app.api import app

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/api/explore/indicators")
    assert response.status_code == 401


def test_policies_endpoint_requires_auth(_patch_settings):
    """GET /api/explore/policies without a token returns 401."""
    from d4bl.app.api import app

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/api/explore/policies")
    assert response.status_code == 401


def test_states_endpoint_requires_auth(_patch_settings):
    """GET /api/explore/states without a token returns 401."""
    from d4bl.app.api import app

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/api/explore/states")
    assert response.status_code == 401


def test_public_endpoints_no_auth_needed(_patch_settings):
    """Public endpoints should NOT require auth."""
    from d4bl.app.api import app

    client = TestClient(app, raise_server_exceptions=False)

    # Root
    response = client.get("/")
    assert response.status_code == 200

    # Health
    response = client.get("/api/health")
    assert response.status_code == 200

    # Models (may fail due to Ollama not running, but should NOT be 401)
    response = client.get("/api/models")
    assert response.status_code != 401


def test_auth_me_endpoint(_patch_settings):
    """GET /api/auth/me returns user info with valid token."""
    from d4bl.app.api import app

    client = TestClient(app, raise_server_exceptions=False)

    # Without token -> 401
    response = client.get("/api/auth/me")
    assert response.status_code == 401

    # With valid token -> 200
    token = _make_token(TEST_USER_ID)
    with patch("d4bl.app.auth._fetch_user_role", new_callable=AsyncMock, return_value="user"):
        response = client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == TEST_USER_ID
    assert data["email"] == "test@example.com"
    assert data["role"] == "user"


def test_admin_invite_requires_admin(_patch_settings):
    """POST /api/admin/invite requires admin role."""
    from d4bl.app.api import app

    client = TestClient(app, raise_server_exceptions=False)

    # No token -> 401
    response = client.post("/api/admin/invite", json={"email": "new@example.com"})
    assert response.status_code == 401

    # Regular user token -> 403
    token = _make_token(TEST_USER_ID)
    with patch("d4bl.app.auth._fetch_user_role", new_callable=AsyncMock, return_value="user"):
        response = client.post(
            "/api/admin/invite",
            json={"email": "new@example.com"},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert response.status_code == 403


def test_admin_users_requires_admin(_patch_settings):
    """GET /api/admin/users requires admin role."""
    from d4bl.app.api import app

    client = TestClient(app, raise_server_exceptions=False)

    # No token -> 401
    response = client.get("/api/admin/users")
    assert response.status_code == 401

    # Regular user token -> 403
    token = _make_token(TEST_USER_ID)
    with patch("d4bl.app.auth._fetch_user_role", new_callable=AsyncMock, return_value="user"):
        response = client.get(
            "/api/admin/users",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert response.status_code == 403
