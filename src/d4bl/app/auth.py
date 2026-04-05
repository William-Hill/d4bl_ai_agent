"""
JWT authentication and RBAC dependencies for FastAPI.

Validates Supabase-issued JWTs and provides role-based access control.
Supports both HS256 (legacy) and ES256 (JWKS) token verification.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from uuid import UUID

import httpx
import jwt
from fastapi import Depends, HTTPException, Request
from jwt import PyJWK
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from d4bl.infra.database import get_db
from d4bl.settings import get_settings

logger = logging.getLogger(__name__)

# Cached JWKS keys with TTL
_jwks_cache: dict[str, PyJWK] = {}
_jwks_cache_time: float = 0.0
_jwks_lock = threading.Lock()
_JWKS_TTL = 3600  # 1 hour


def _refresh_jwks(supabase_url: str) -> None:
    """Fetch and cache JWKS public keys from Supabase."""
    global _jwks_cache, _jwks_cache_time
    try:
        resp = httpx.get(
            f"{supabase_url}/auth/v1/.well-known/jwks.json",
            timeout=10.0,
        )
        resp.raise_for_status()
        keys = resp.json().get("keys", [])
        new_cache = {}
        for key_data in keys:
            kid = key_data.get("kid")
            if kid:
                new_cache[kid] = PyJWK(key_data)
        _jwks_cache.update(new_cache)
        _jwks_cache_time = time.monotonic()
        logger.info("Refreshed JWKS cache: %d keys", len(new_cache))
    except Exception:
        logger.exception("Failed to fetch JWKS from Supabase")


def _get_jwks_key(kid: str, supabase_url: str) -> PyJWK | None:
    """Get a JWKS key by kid, refreshing cache if needed."""
    with _jwks_lock:
        if kid not in _jwks_cache or (time.monotonic() - _jwks_cache_time) > _JWKS_TTL:
            _refresh_jwks(supabase_url)
    return _jwks_cache.get(kid)


def decode_supabase_jwt(token: str, settings: object) -> dict:
    """Decode a Supabase JWT, supporting both ES256 (JWKS) and HS256."""
    header = jwt.get_unverified_header(token)
    alg = header.get("alg", "HS256")
    kid = header.get("kid")

    if alg == "ES256" and kid and settings.supabase_url:
        jwk = _get_jwks_key(kid, settings.supabase_url)
        if jwk is None:
            raise jwt.InvalidTokenError(f"Unknown key ID: {kid}")
        return jwt.decode(
            token,
            jwk.key,
            algorithms=["ES256"],
            audience="authenticated",
        )

    # Fallback to HS256 with JWT secret
    return jwt.decode(
        token,
        settings.supabase_jwt_secret,
        algorithms=["HS256"],
        audience="authenticated",
    )


@dataclass(frozen=True)
class CurrentUser:
    """Authenticated user extracted from a valid JWT."""

    id: UUID
    email: str
    role: str  # "user" or "admin"

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


async def _fetch_user_role(db: AsyncSession, user_id: str) -> str:
    """Look up a user's role from the profiles table. Defaults to 'user'."""
    result = await db.execute(
        text("SELECT role FROM profiles WHERE id = CAST(:uid AS uuid)"),
        {"uid": user_id},
    )
    row = result.scalar_one_or_none()
    return row or "user"


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> CurrentUser:
    """FastAPI dependency: extract and validate the Supabase JWT.

    Raises:
        HTTPException 401 - missing or invalid token
    """
    auth_header = request.headers.get("authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing authentication token")

    token = auth_header.removeprefix("Bearer ").strip()
    settings = get_settings()

    if not settings.supabase_jwt_secret and not settings.supabase_url:
        raise HTTPException(status_code=500, detail="Auth not configured")

    try:
        payload = decode_supabase_jwt(token, settings)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

    user_id = payload.get("sub")
    email = payload.get("email", "")

    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token claims")

    role = await _fetch_user_role(db, user_id)

    return CurrentUser(id=UUID(user_id), email=email, role=role)


async def require_admin(
    user: CurrentUser = Depends(get_current_user),
) -> CurrentUser:
    """FastAPI dependency: require the authenticated user to be an admin.

    Raises:
        HTTPException 403 - user is not an admin
    """
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user
