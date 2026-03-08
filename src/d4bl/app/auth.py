"""
JWT authentication and RBAC dependencies for FastAPI.

Validates Supabase-issued JWTs and provides role-based access control.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from d4bl.infra.database import get_db
from d4bl.settings import get_settings

logger = logging.getLogger(__name__)


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

    if not settings.supabase_jwt_secret:
        raise HTTPException(status_code=500, detail="Auth not configured")

    try:
        payload = jwt.decode(
            token,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
            audience="authenticated",
        )
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
