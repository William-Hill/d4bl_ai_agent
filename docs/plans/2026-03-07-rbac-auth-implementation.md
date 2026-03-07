# RBAC & Authentication Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add Supabase Auth with RBAC so users log in, own their research jobs, and admins manage users via invite-only registration.

**Architecture:** Supabase Auth issues JWTs. FastAPI middleware validates JWTs and enforces ownership/role checks. Next.js middleware gates all pages behind login. A `profiles` table stores roles. RLS on `research_jobs` provides defense-in-depth.

**Tech Stack:** Supabase Auth, PyJWT, FastAPI Depends, `@supabase/ssr`, Next.js middleware, Supabase migrations

**Design doc:** `docs/plans/2026-03-07-rbac-auth-design.md`

---

### Task 1: Database Migration -- profiles table and research_jobs user_id

**Files:**
- Create: `supabase/migrations/20260307000001_add_auth_profiles.sql`
- Modify: `src/d4bl/infra/database.py:33-69` (ResearchJob model)
- Modify: `tests/test_tenant_filter.py` (rename to `tests/test_user_ownership.py`)
- Test: `tests/test_user_ownership.py`

**Step 1: Write the Supabase migration SQL**

Create `supabase/migrations/20260307000001_add_auth_profiles.sql`:

```sql
-- Create profiles table linked to Supabase auth.users
CREATE TABLE IF NOT EXISTS public.profiles (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    email TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'user' CHECK (role IN ('user', 'admin')),
    display_name TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Index for role-based lookups
CREATE INDEX IF NOT EXISTS ix_profiles_role ON public.profiles(role);

-- Auto-create profile on new auth.users signup
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO public.profiles (id, email, role)
    VALUES (
        NEW.id,
        NEW.email,
        CASE
            WHEN NEW.email = current_setting('app.admin_email', true)
            THEN 'admin'
            ELSE 'user'
        END
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();

-- Add user_id to research_jobs (nullable for existing rows)
ALTER TABLE public.research_jobs
    ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES auth.users(id);

CREATE INDEX IF NOT EXISTS ix_research_jobs_user_id
    ON public.research_jobs(user_id);

-- Enable RLS on research_jobs
ALTER TABLE public.research_jobs ENABLE ROW LEVEL SECURITY;

-- RLS: users see own jobs
CREATE POLICY "Users can view own jobs"
    ON public.research_jobs FOR SELECT
    USING (
        user_id = auth.uid()
        OR EXISTS (
            SELECT 1 FROM public.profiles
            WHERE profiles.id = auth.uid() AND profiles.role = 'admin'
        )
    );

-- RLS: users can insert own jobs
CREATE POLICY "Users can insert own jobs"
    ON public.research_jobs FOR INSERT
    WITH CHECK (user_id = auth.uid());

-- Enable RLS on profiles
ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;

-- RLS: users can read own profile, admins can read all
CREATE POLICY "Users can view own profile"
    ON public.profiles FOR SELECT
    USING (
        id = auth.uid()
        OR EXISTS (
            SELECT 1 FROM public.profiles p
            WHERE p.id = auth.uid() AND p.role = 'admin'
        )
    );

-- RLS: only admins can update profiles
CREATE POLICY "Admins can update profiles"
    ON public.profiles FOR UPDATE
    USING (
        EXISTS (
            SELECT 1 FROM public.profiles p
            WHERE p.id = auth.uid() AND p.role = 'admin'
        )
    );
```

**Step 2: Update ResearchJob model**

In `src/d4bl/infra/database.py`, replace `tenant_id` with `user_id` on the `ResearchJob` class:

```python
# Line 50: Replace tenant_id with user_id
# Remove: tenant_id = Column(String(100), nullable=True, index=True)
# Add:
user_id = Column(PG_UUID(as_uuid=True), nullable=True, index=True)
```

Update `to_dict()` (lines 52-69): replace `"tenant_id": self.tenant_id` with `"user_id": str(self.user_id) if self.user_id else None`.

**Step 3: Write tests for user ownership**

Create `tests/test_user_ownership.py` (replacing `tests/test_tenant_filter.py`):

```python
"""Tests for user_id ownership on ResearchJob."""
from __future__ import annotations

from uuid import uuid4

from d4bl.infra.database import ResearchJob


def test_research_job_has_user_id_column():
    """ResearchJob model should have a user_id column."""
    assert hasattr(ResearchJob, "user_id")


def test_research_job_to_dict_includes_user_id():
    """to_dict() should include user_id."""
    uid = uuid4()
    job = ResearchJob(query="test", status="pending", user_id=uid)
    d = job.to_dict()
    assert "user_id" in d
    assert d["user_id"] == str(uid)


def test_research_job_user_id_nullable():
    """user_id should be nullable (for legacy jobs)."""
    job = ResearchJob(query="test", status="pending")
    assert job.user_id is None
```

**Step 4: Run tests**

Run: `cd /Users/william-meroxa/Development/d4bl_ai_agent && python -m pytest tests/test_user_ownership.py -v`
Expected: 3 PASSED

**Step 5: Delete old tenant test**

Delete `tests/test_tenant_filter.py`.

**Step 6: Run full test suite to check for breakage**

Run: `python -m pytest tests/ -v`
Expected: All pass. Fix any tests that reference `tenant_id`.

**Step 7: Commit**

```bash
git add supabase/migrations/20260307000001_add_auth_profiles.sql \
        src/d4bl/infra/database.py \
        tests/test_user_ownership.py
git rm tests/test_tenant_filter.py
git commit -m "feat: add profiles table, replace tenant_id with user_id on ResearchJob"
```

---

### Task 2: Settings -- Add Supabase auth config

**Files:**
- Modify: `src/d4bl/settings.py:19-143` (Settings dataclass)
- Test: `tests/test_settings.py`

**Step 1: Write failing test**

Add to `tests/test_settings.py`:

```python
def test_supabase_auth_settings(monkeypatch):
    """Settings should expose Supabase auth fields."""
    get_settings.cache_clear()
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_JWT_SECRET", "test-jwt-secret")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-service-key")
    monkeypatch.setenv("ADMIN_EMAIL", "admin@example.com")
    s = get_settings()
    assert s.supabase_url == "https://test.supabase.co"
    assert s.supabase_jwt_secret == "test-jwt-secret"
    assert s.supabase_service_role_key == "test-service-key"
    assert s.admin_email == "admin@example.com"
    get_settings.cache_clear()
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_settings.py::test_supabase_auth_settings -v`
Expected: FAIL (attribute not found)

**Step 3: Add Supabase settings fields**

In `src/d4bl/settings.py`, add fields after the `tenant_id` field (line 60):

```python
# -- Supabase Auth --
supabase_url: str | None = field(init=False)
supabase_jwt_secret: str | None = field(init=False)
supabase_service_role_key: str | None = field(init=False)
admin_email: str | None = field(init=False)
```

In `__post_init__`, after the tenant_id assignment (line 143), add:

```python
# Supabase Auth
_set("supabase_url", os.getenv("SUPABASE_URL"))
_set("supabase_jwt_secret", os.getenv("SUPABASE_JWT_SECRET"))
_set("supabase_service_role_key", os.getenv("SUPABASE_SERVICE_ROLE_KEY"))
_set("admin_email", os.getenv("ADMIN_EMAIL"))
```

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_settings.py::test_supabase_auth_settings -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/d4bl/settings.py tests/test_settings.py
git commit -m "feat: add Supabase auth settings (URL, JWT secret, service role key)"
```

---

### Task 3: Backend auth module -- JWT validation and role checking

**Files:**
- Create: `src/d4bl/app/auth.py`
- Test: `tests/test_auth.py`

**Step 1: Write failing tests**

Create `tests/test_auth.py`:

```python
"""Tests for JWT authentication and role-checking dependencies."""
from __future__ import annotations

import time
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import jwt
import pytest

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
    from fastapi import HTTPException

    request = _make_request(None)
    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(request, mock_db)
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user_expired_token(mock_db):
    """Expired JWT raises 401."""
    from fastapi import HTTPException

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
    from fastapi import HTTPException

    user = CurrentUser(id=uuid4(), email="user@test.com", role="user")
    with pytest.raises(HTTPException) as exc_info:
        await require_admin(user)
    assert exc_info.value.status_code == 403
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_auth.py -v`
Expected: FAIL (module not found)

**Step 3: Add PyJWT dependency**

Run: `cd /Users/william-meroxa/Development/d4bl_ai_agent && pip install PyJWT`

Add `"PyJWT>=2.8.0"` to the `dependencies` list in `pyproject.toml` (line 7-12).

**Step 4: Write the auth module**

Create `src/d4bl/app/auth.py`:

```python
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
from sqlalchemy import select, text
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
        HTTPException 401 – missing or invalid token
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
        HTTPException 403 – user is not an admin
    """
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user
```

**Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_auth.py -v`
Expected: 5 PASSED

**Step 6: Commit**

```bash
git add src/d4bl/app/auth.py tests/test_auth.py pyproject.toml
git commit -m "feat: add JWT auth module with role-based access control"
```

---

### Task 4: Protect API endpoints with auth

**Files:**
- Modify: `src/d4bl/app/api.py:1-628`
- Modify: `src/d4bl/app/schemas.py` (add admin schemas)
- Test: `tests/test_api_auth.py`

**Step 1: Write failing tests**

Create `tests/test_api_auth.py`:

```python
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
ADMIN_USER_ID = str(uuid4())


def _make_token(sub: str, email: str = "test@example.com") -> str:
    payload = {
        "sub": sub,
        "email": email,
        "exp": int(time.time()) + 3600,
        "aud": "authenticated",
    }
    return jwt.encode(payload, TEST_SECRET, algorithm="HS256")


@pytest.fixture
def _patch_settings():
    """Patch settings for auth testing."""
    mock_settings = MagicMock()
    mock_settings.supabase_jwt_secret = TEST_SECRET
    mock_settings.cors_allowed_origins = ("*",)
    mock_settings.tenant_id = None
    with patch("d4bl.app.auth.get_settings", return_value=mock_settings):
        with patch("d4bl.app.api.get_settings", return_value=mock_settings):
            with patch("d4bl.settings.get_settings", return_value=mock_settings):
                yield


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
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_api_auth.py -v`
Expected: FAIL (endpoints currently return 200 without auth)

**Step 3: Add auth dependencies to API endpoints**

Modify `src/d4bl/app/api.py`:

1. Add imports at top:
```python
from d4bl.app.auth import CurrentUser, get_current_user, require_admin
```

2. Update `create_research` (line 153-194):
```python
@app.post("/api/research", response_model=ResearchResponse)
async def create_research(
    request: ResearchRequest,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
```
Replace `tenant_id=_settings.tenant_id` with `user_id=user.id` in the ResearchJob constructor.

3. Update `get_job_status` (line 196-201):
```python
@app.get("/api/jobs/{job_id}", response_model=JobStatus)
async def get_job_status(
    job_id: str,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
```
After fetching the job, add ownership check:
```python
if not user.is_admin and job.user_id != user.id:
    raise HTTPException(status_code=404, detail="Job not found")
```

4. Update `get_job_history` (line 204-247):
```python
@app.get("/api/jobs", response_model=JobHistoryResponse)
async def get_job_history(
    page: int = 1,
    page_size: int = 20,
    status: str | None = None,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
```
Replace tenant_id filter with user_id filter:
```python
if not user.is_admin:
    filters.append(ResearchJob.user_id == user.id)
```

5. Add `get_current_user` dependency to all other endpoints:
- `get_evaluations` -- add `user: CurrentUser = Depends(get_current_user)`
- `websocket_endpoint` -- extract token from query param `?token=...` (WebSockets can't send headers easily)
- `search_similar_content`, `get_scraped_content_by_job`, `natural_language_query` -- add auth dependency
- `get_indicators`, `get_policies`, `get_states_summary` -- add auth dependency
- Keep `read_root`, `health_check`, `list_models` public (no auth)

6. For the WebSocket endpoint, update to accept token as query parameter:
```python
@app.websocket("/ws/{job_id}")
async def websocket_endpoint(websocket: WebSocket, job_id: str, token: str | None = None):
    # Validate token
    if not token:
        await websocket.close(code=1008, reason="Missing token")
        return
    # ... validate JWT and check job ownership ...
```

**Step 4: Add admin schemas to schemas.py**

Add to `src/d4bl/app/schemas.py`:

```python
# --- Admin models ---

class InviteRequest(BaseModel):
    email: str

    @field_validator("email")
    @classmethod
    def email_not_blank(cls, v: str) -> str:
        if not v or not v.strip() or "@" not in v:
            raise ValueError("Valid email required")
        return v.strip()


class UserProfile(BaseModel):
    id: str
    email: str
    role: str
    display_name: str | None = None
    created_at: str | None = None


class UpdateRoleRequest(BaseModel):
    role: Literal["user", "admin"]
```

**Step 5: Add admin endpoints to api.py**

Add at end of `api.py` (before `if __name__`):

```python
@app.post("/api/admin/invite")
async def invite_user(
    request: InviteRequest,
    user: CurrentUser = Depends(require_admin),
):
    """Invite a new user by email (admin only)."""
    import httpx

    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_service_role_key:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{settings.supabase_url}/auth/v1/invite",
            json={"email": request.email},
            headers={
                "apikey": settings.supabase_service_role_key,
                "Authorization": f"Bearer {settings.supabase_service_role_key}",
                "Content-Type": "application/json",
            },
        )

    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail="Failed to invite user")

    return {"message": f"Invitation sent to {request.email}"}


@app.get("/api/admin/users", response_model=list[UserProfile])
async def list_users(
    user: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """List all user profiles (admin only)."""
    result = await db.execute(text(
        "SELECT id, email, role, display_name, created_at FROM profiles ORDER BY created_at"
    ))
    rows = result.mappings().all()
    return [
        UserProfile(
            id=str(row["id"]),
            email=row["email"],
            role=row["role"],
            display_name=row["display_name"],
            created_at=row["created_at"].isoformat() if row["created_at"] else None,
        )
        for row in rows
    ]


@app.patch("/api/admin/users/{user_id}")
async def update_user_role(
    user_id: str,
    request: UpdateRoleRequest,
    user: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Update a user's role (admin only)."""
    target_uuid = parse_job_uuid(user_id)  # reuse UUID parser
    await db.execute(
        text("UPDATE profiles SET role = :role, updated_at = now() WHERE id = CAST(:uid AS uuid)"),
        {"role": request.role, "uid": str(target_uuid)},
    )
    await db.commit()
    return {"message": f"User {user_id} role updated to {request.role}"}
```

**Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/test_api_auth.py -v`
Expected: 2 PASSED

**Step 7: Run full test suite**

Run: `python -m pytest tests/ -v`
Expected: All pass. Fix any tests that break due to the new auth dependency (existing tests may need to mock out `get_current_user`).

**Step 8: Commit**

```bash
git add src/d4bl/app/api.py src/d4bl/app/schemas.py tests/test_api_auth.py
git commit -m "feat: protect API endpoints with JWT auth, add admin endpoints"
```

---

### Task 5: Update existing tests to work with auth

**Files:**
- Modify: `tests/conftest.py`
- Modify: `tests/test_app_helpers.py`
- Modify: any other tests that call API endpoints

**Step 1: Add auth test fixtures to conftest.py**

Add to `tests/conftest.py`:

```python
import time
from unittest.mock import MagicMock, patch

import jwt


TEST_JWT_SECRET = "test-jwt-secret-for-fixtures"
TEST_USER_ID = "00000000-0000-0000-0000-000000000001"
TEST_ADMIN_ID = "00000000-0000-0000-0000-000000000002"


def _make_test_token(sub: str, email: str = "test@example.com") -> str:
    payload = {
        "sub": sub,
        "email": email,
        "exp": int(time.time()) + 3600,
        "aud": "authenticated",
    }
    return jwt.encode(payload, TEST_JWT_SECRET, algorithm="HS256")


@pytest.fixture
def user_token():
    """JWT token for a regular user."""
    return _make_test_token(TEST_USER_ID, "user@test.com")


@pytest.fixture
def admin_token():
    """JWT token for an admin user."""
    return _make_test_token(TEST_ADMIN_ID, "admin@test.com")


@pytest.fixture
def auth_headers(user_token):
    """Authorization headers for a regular user."""
    return {"Authorization": f"Bearer {user_token}"}


@pytest.fixture
def admin_auth_headers(admin_token):
    """Authorization headers for an admin user."""
    return {"Authorization": f"Bearer {admin_token}"}
```

**Step 2: Update existing API tests**

For each test file that exercises API endpoints (e.g., `test_app_helpers.py`, `test_explore_api.py`, `test_api_query.py`), add the auth dependency override or mock. The simplest approach: patch `get_current_user` to return a mock user.

Example override pattern for TestClient tests:

```python
from d4bl.app.auth import CurrentUser, get_current_user

mock_user = CurrentUser(id=uuid4(), email="test@test.com", role="user")

app.dependency_overrides[get_current_user] = lambda: mock_user
# ... run tests ...
del app.dependency_overrides[get_current_user]
```

**Step 3: Run full test suite**

Run: `python -m pytest tests/ -v`
Expected: All pass

**Step 4: Commit**

```bash
git add tests/
git commit -m "fix: update existing tests to work with auth middleware"
```

---

### Task 6: Frontend -- Install Supabase packages and create client

**Files:**
- Modify: `ui-nextjs/package.json`
- Create: `ui-nextjs/lib/supabase.ts`

**Step 1: Install Supabase packages**

Run: `cd /Users/william-meroxa/Development/d4bl_ai_agent/ui-nextjs && npm install @supabase/supabase-js @supabase/ssr`

**Step 2: Create Supabase client utilities**

Create `ui-nextjs/lib/supabase.ts`:

```typescript
import { createBrowserClient } from '@supabase/ssr';

export function createClient() {
  return createBrowserClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!
  );
}
```

**Step 3: Verify build**

Run: `cd /Users/william-meroxa/Development/d4bl_ai_agent/ui-nextjs && npm run build`
Expected: Build succeeds

**Step 4: Commit**

```bash
git add ui-nextjs/package.json ui-nextjs/package-lock.json ui-nextjs/lib/supabase.ts
git commit -m "feat: add Supabase client for frontend auth"
```

---

### Task 7: Frontend -- Auth context and API client changes

**Files:**
- Create: `ui-nextjs/lib/auth-context.tsx`
- Modify: `ui-nextjs/lib/api.ts`
- Modify: `ui-nextjs/app/layout.tsx`

**Step 1: Create auth context**

Create `ui-nextjs/lib/auth-context.tsx`:

```tsx
'use client';

import { createContext, useContext, useEffect, useState } from 'react';
import { User, Session } from '@supabase/supabase-js';
import { createClient } from './supabase';

interface AuthContextType {
  user: User | null;
  session: Session | null;
  role: string | null;
  isAdmin: boolean;
  isLoading: boolean;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType>({
  user: null,
  session: null,
  role: null,
  isAdmin: false,
  isLoading: true,
  signOut: async () => {},
});

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [session, setSession] = useState<Session | null>(null);
  const [role, setRole] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const supabase = createClient();

  useEffect(() => {
    // Get initial session
    supabase.auth.getSession().then(({ data: { session } }) => {
      setSession(session);
      setUser(session?.user ?? null);
      if (session?.user) {
        fetchRole(session.access_token);
      } else {
        setIsLoading(false);
      }
    });

    // Listen for auth changes
    const { data: { subscription } } = supabase.auth.onAuthStateChange(
      (_event, session) => {
        setSession(session);
        setUser(session?.user ?? null);
        if (session?.user) {
          fetchRole(session.access_token);
        } else {
          setRole(null);
          setIsLoading(false);
        }
      }
    );

    return () => subscription.unsubscribe();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  async function fetchRole(accessToken: string) {
    try {
      const { API_BASE } = await import('./api');
      const response = await fetch(`${API_BASE}/api/auth/me`, {
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      if (response.ok) {
        const data = await response.json();
        setRole(data.role);
      }
    } catch {
      setRole('user');
    } finally {
      setIsLoading(false);
    }
  }

  const signOut = async () => {
    await supabase.auth.signOut();
    setUser(null);
    setSession(null);
    setRole(null);
  };

  return (
    <AuthContext.Provider value={{
      user,
      session,
      role,
      isAdmin: role === 'admin',
      isLoading,
      signOut,
    }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
```

**Step 2: Add /api/auth/me endpoint to backend**

Add to `src/d4bl/app/api.py`:

```python
@app.get("/api/auth/me")
async def get_me(user: CurrentUser = Depends(get_current_user)):
    """Return the authenticated user's profile info."""
    return {"id": str(user.id), "email": user.email, "role": user.role}
```

**Step 3: Update API client to include auth headers**

Modify `ui-nextjs/lib/api.ts`:

Add a helper to get the auth token:

```typescript
import { createClient } from './supabase';

async function getAuthHeaders(): Promise<Record<string, string>> {
  const supabase = createClient();
  const { data: { session } } = await supabase.auth.getSession();
  if (session?.access_token) {
    return {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${session.access_token}`,
    };
  }
  return { 'Content-Type': 'application/json' };
}
```

Update every `fetch` call to use `await getAuthHeaders()` instead of hardcoded headers. For example, `createResearchJob`:

```typescript
export async function createResearchJob(
  query: string,
  summaryFormat: string,
  selectedAgents?: string[],
  model?: string
): Promise<ResearchResponse> {
  const headers = await getAuthHeaders();
  const response = await fetch(`${API_BASE}/api/research`, {
    method: 'POST',
    headers,
    body: JSON.stringify({
      query,
      summary_format: summaryFormat,
      selected_agents: selectedAgents,
      model,
    }),
  });

  if (response.status === 401) {
    window.location.href = '/login';
    throw new Error('Authentication required');
  }

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to create research job');
  }

  return response.json();
}
```

Apply the same pattern to `getEvaluations`, `getJobStatus`, `getJobHistory`.

**Step 4: Update WebSocket hook to pass token**

The `useWebSocket` hook needs to append the token as a query parameter. In the WebSocket URL construction, change:

```typescript
// In hooks/useWebSocket.ts (or wherever WS_BASE is used)
const { data: { session } } = await supabase.auth.getSession();
const wsUrl = `${WS_BASE}/ws/${jobId}?token=${session?.access_token}`;
```

**Step 5: Update layout.tsx with AuthProvider and user menu**

Modify `ui-nextjs/app/layout.tsx`:

```tsx
import { AuthProvider } from '@/lib/auth-context';
import NavBar from '@/components/NavBar';

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className={`${geistSans.variable} ${geistMono.variable} antialiased bg-[#292929]`}>
        <AuthProvider>
          <NavBar />
          {children}
        </AuthProvider>
      </body>
    </html>
  );
}
```

**Step 6: Create NavBar component**

Create `ui-nextjs/components/NavBar.tsx`:

```tsx
'use client';

import Link from 'next/link';
import { useAuth } from '@/lib/auth-context';

export default function NavBar() {
  const { user, role, isAdmin, signOut } = useAuth();

  return (
    <nav className="border-b border-[#404040] bg-[#1a1a1a] px-6 py-3 flex items-center gap-8">
      <span className="font-bold text-[#00ff32] text-lg tracking-tight">D4BL</span>
      <Link href="/" className="text-sm text-gray-300 hover:text-[#00ff32] transition-colors">
        Research
      </Link>
      <Link href="/explore" className="text-sm text-gray-300 hover:text-[#00ff32] transition-colors">
        Explore Data
      </Link>
      {isAdmin && (
        <Link href="/admin" className="text-sm text-gray-300 hover:text-[#00ff32] transition-colors">
          Admin
        </Link>
      )}
      <div className="ml-auto flex items-center gap-4">
        {user && (
          <>
            <span className="text-sm text-gray-400">{user.email}</span>
            {role && (
              <span className="text-xs px-2 py-0.5 rounded bg-[#404040] text-gray-300">
                {role}
              </span>
            )}
            <button
              onClick={signOut}
              className="text-sm text-gray-400 hover:text-red-400 transition-colors"
            >
              Sign out
            </button>
          </>
        )}
      </div>
    </nav>
  );
}
```

**Step 7: Verify build**

Run: `cd /Users/william-meroxa/Development/d4bl_ai_agent/ui-nextjs && npm run build`
Expected: Build succeeds

**Step 8: Commit**

```bash
git add ui-nextjs/lib/auth-context.tsx ui-nextjs/lib/api.ts ui-nextjs/app/layout.tsx \
        ui-nextjs/components/NavBar.tsx src/d4bl/app/api.py
git commit -m "feat: add auth context, protected API calls, and user nav bar"
```

---

### Task 8: Frontend -- Login page and Next.js middleware

**Files:**
- Create: `ui-nextjs/app/login/page.tsx`
- Create: `ui-nextjs/middleware.ts`

**Step 1: Create login page**

Create `ui-nextjs/app/login/page.tsx`:

```tsx
'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { createClient } from '@/lib/supabase';
import D4BLLogo from '@/components/D4BLLogo';

export default function LoginPage() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const router = useRouter();
  const supabase = createClient();

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);

    const { error } = await supabase.auth.signInWithPassword({ email, password });

    if (error) {
      setError(error.message);
      setLoading(false);
    } else {
      router.push('/');
      router.refresh();
    }
  };

  return (
    <div className="min-h-screen bg-[#292929] flex items-center justify-center px-4">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <div className="flex justify-center mb-6">
            <D4BLLogo />
          </div>
          <h1 className="text-2xl font-bold text-white mb-2">Sign In</h1>
          <p className="text-gray-400 text-sm">
            Access is invite-only. Contact your administrator for an account.
          </p>
        </div>

        <form onSubmit={handleLogin} className="space-y-4">
          <div>
            <label htmlFor="email" className="block text-sm text-gray-300 mb-1">
              Email
            </label>
            <input
              id="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              className="w-full px-3 py-2 bg-[#1a1a1a] border border-[#404040] rounded text-white
                         focus:outline-none focus:border-[#00ff32] transition-colors"
            />
          </div>

          <div>
            <label htmlFor="password" className="block text-sm text-gray-300 mb-1">
              Password
            </label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              className="w-full px-3 py-2 bg-[#1a1a1a] border border-[#404040] rounded text-white
                         focus:outline-none focus:border-[#00ff32] transition-colors"
            />
          </div>

          {error && (
            <p className="text-red-400 text-sm">{error}</p>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full py-2 bg-[#00ff32] text-black font-semibold rounded
                       hover:bg-[#00cc28] disabled:opacity-50 transition-colors"
          >
            {loading ? 'Signing in...' : 'Sign In'}
          </button>
        </form>
      </div>
    </div>
  );
}
```

**Step 2: Create Next.js middleware**

Create `ui-nextjs/middleware.ts`:

```typescript
import { createServerClient } from '@supabase/ssr';
import { NextResponse, type NextRequest } from 'next/server';

export async function middleware(request: NextRequest) {
  let supabaseResponse = NextResponse.next({ request });

  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() {
          return request.cookies.getAll();
        },
        setAll(cookiesToSet) {
          cookiesToSet.forEach(({ name, value, options }) =>
            request.cookies.set(name, value)
          );
          supabaseResponse = NextResponse.next({ request });
          cookiesToSet.forEach(({ name, value, options }) =>
            supabaseResponse.cookies.set(name, value, options)
          );
        },
      },
    }
  );

  const { data: { user } } = await supabase.auth.getUser();

  // Allow access to login page and static assets
  const isLoginPage = request.nextUrl.pathname === '/login';
  const isPublicPath = request.nextUrl.pathname.startsWith('/_next') ||
                       request.nextUrl.pathname.startsWith('/favicon') ||
                       request.nextUrl.pathname === '/api/health';

  if (!user && !isLoginPage && !isPublicPath) {
    const url = request.nextUrl.clone();
    url.pathname = '/login';
    return NextResponse.redirect(url);
  }

  if (user && isLoginPage) {
    const url = request.nextUrl.clone();
    url.pathname = '/';
    return NextResponse.redirect(url);
  }

  return supabaseResponse;
}

export const config = {
  matcher: [
    '/((?!_next/static|_next/image|favicon.ico|favicon.png).*)',
  ],
};
```

**Step 3: Verify build**

Run: `cd /Users/william-meroxa/Development/d4bl_ai_agent/ui-nextjs && npm run build`
Expected: Build succeeds

**Step 4: Commit**

```bash
git add ui-nextjs/app/login/page.tsx ui-nextjs/middleware.ts
git commit -m "feat: add login page and Next.js auth middleware"
```

---

### Task 9: Frontend -- Admin page

**Files:**
- Create: `ui-nextjs/app/admin/page.tsx`

**Step 1: Create admin page**

Create `ui-nextjs/app/admin/page.tsx`:

```tsx
'use client';

import { useState, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/lib/auth-context';
import { API_BASE } from '@/lib/api';
import { createClient } from '@/lib/supabase';

interface UserProfile {
  id: string;
  email: string;
  role: string;
  display_name: string | null;
  created_at: string | null;
}

export default function AdminPage() {
  const { isAdmin, isLoading, session } = useAuth();
  const router = useRouter();
  const [users, setUsers] = useState<UserProfile[]>([]);
  const [inviteEmail, setInviteEmail] = useState('');
  const [inviteLoading, setInviteLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const getHeaders = useCallback(() => ({
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${session?.access_token}`,
  }), [session?.access_token]);

  const fetchUsers = useCallback(async () => {
    if (!session?.access_token) return;
    try {
      const response = await fetch(`${API_BASE}/api/admin/users`, {
        headers: getHeaders(),
      });
      if (response.ok) {
        setUsers(await response.json());
      }
    } catch {
      setError('Failed to load users');
    }
  }, [session?.access_token, getHeaders]);

  useEffect(() => {
    if (!isLoading && !isAdmin) {
      router.push('/');
    }
  }, [isAdmin, isLoading, router]);

  useEffect(() => {
    if (isAdmin) fetchUsers();
  }, [isAdmin, fetchUsers]);

  const handleInvite = async (e: React.FormEvent) => {
    e.preventDefault();
    setInviteLoading(true);
    setMessage(null);
    setError(null);

    try {
      const response = await fetch(`${API_BASE}/api/admin/invite`, {
        method: 'POST',
        headers: getHeaders(),
        body: JSON.stringify({ email: inviteEmail }),
      });

      if (response.ok) {
        setMessage(`Invitation sent to ${inviteEmail}`);
        setInviteEmail('');
        fetchUsers();
      } else {
        const data = await response.json();
        setError(data.detail || 'Failed to send invitation');
      }
    } catch {
      setError('Failed to send invitation');
    } finally {
      setInviteLoading(false);
    }
  };

  const handleRoleChange = async (userId: string, newRole: string) => {
    try {
      const response = await fetch(`${API_BASE}/api/admin/users/${userId}`, {
        method: 'PATCH',
        headers: getHeaders(),
        body: JSON.stringify({ role: newRole }),
      });

      if (response.ok) {
        fetchUsers();
      } else {
        setError('Failed to update role');
      }
    } catch {
      setError('Failed to update role');
    }
  };

  if (isLoading) {
    return <div className="min-h-screen bg-[#292929] flex items-center justify-center">
      <p className="text-gray-400">Loading...</p>
    </div>;
  }

  if (!isAdmin) return null;

  return (
    <div className="min-h-screen bg-[#292929]">
      <div className="max-w-4xl mx-auto px-4 py-8">
        <h1 className="text-3xl font-bold text-white mb-8">User Management</h1>

        {/* Invite form */}
        <div className="bg-[#1a1a1a] border border-[#404040] rounded-lg p-6 mb-8">
          <h2 className="text-lg font-semibold text-white mb-4">Invite User</h2>
          <form onSubmit={handleInvite} className="flex gap-3">
            <input
              type="email"
              value={inviteEmail}
              onChange={(e) => setInviteEmail(e.target.value)}
              placeholder="user@example.com"
              required
              className="flex-1 px-3 py-2 bg-[#292929] border border-[#404040] rounded text-white
                         focus:outline-none focus:border-[#00ff32] transition-colors"
            />
            <button
              type="submit"
              disabled={inviteLoading}
              className="px-4 py-2 bg-[#00ff32] text-black font-semibold rounded
                         hover:bg-[#00cc28] disabled:opacity-50 transition-colors"
            >
              {inviteLoading ? 'Sending...' : 'Send Invite'}
            </button>
          </form>
          {message && <p className="mt-3 text-green-400 text-sm">{message}</p>}
          {error && <p className="mt-3 text-red-400 text-sm">{error}</p>}
        </div>

        {/* Users table */}
        <div className="bg-[#1a1a1a] border border-[#404040] rounded-lg overflow-hidden">
          <table className="w-full">
            <thead>
              <tr className="border-b border-[#404040]">
                <th className="px-4 py-3 text-left text-sm text-gray-400">Email</th>
                <th className="px-4 py-3 text-left text-sm text-gray-400">Role</th>
                <th className="px-4 py-3 text-left text-sm text-gray-400">Joined</th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id} className="border-b border-[#404040] last:border-0">
                  <td className="px-4 py-3 text-white text-sm">{u.email}</td>
                  <td className="px-4 py-3">
                    <select
                      value={u.role}
                      onChange={(e) => handleRoleChange(u.id, e.target.value)}
                      className="bg-[#292929] border border-[#404040] rounded px-2 py-1
                                 text-sm text-white focus:outline-none focus:border-[#00ff32]"
                    >
                      <option value="user">user</option>
                      <option value="admin">admin</option>
                    </select>
                  </td>
                  <td className="px-4 py-3 text-gray-400 text-sm">
                    {u.created_at ? new Date(u.created_at).toLocaleDateString() : '-'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
```

**Step 2: Verify build**

Run: `cd /Users/william-meroxa/Development/d4bl_ai_agent/ui-nextjs && npm run build`
Expected: Build succeeds

**Step 3: Commit**

```bash
git add ui-nextjs/app/admin/page.tsx
git commit -m "feat: add admin page for user management and invitations"
```

---

### Task 10: Remove tenant_id from settings and API

**Files:**
- Modify: `src/d4bl/settings.py:59-60,142-143` (remove tenant_id)
- Modify: `src/d4bl/app/api.py` (remove any remaining tenant_id references)
- Modify: `tests/test_settings.py` (remove tenant_id test if exists)

**Step 1: Remove tenant_id from Settings**

In `src/d4bl/settings.py`:
- Remove field: `tenant_id: str | None = field(init=False)` (line 60)
- Remove assignment: `_set("tenant_id", os.getenv("TENANT_ID"))` (line 143)

**Step 2: Remove tenant_id references from api.py**

Search for any remaining `tenant_id` references in `api.py` and remove them.

Remove `_settings.tenant_id` usage (should have been replaced in Task 4, but verify).

**Step 3: Run full test suite**

Run: `python -m pytest tests/ -v`
Expected: All pass

**Step 4: Commit**

```bash
git add src/d4bl/settings.py src/d4bl/app/api.py tests/
git commit -m "refactor: remove tenant_id, fully replaced by user_id auth"
```

---

### Task 11: Bootstrap admin script

**Files:**
- Create: `scripts/bootstrap_admin.py`

**Step 1: Create bootstrap script**

Create `scripts/bootstrap_admin.py`:

```python
"""Bootstrap the first admin user in Supabase.

Usage:
    python scripts/bootstrap_admin.py admin@example.com

This invites the given email via Supabase Auth and sets their role to 'admin'
in the profiles table (via the trigger that checks ADMIN_EMAIL).
"""
from __future__ import annotations

import asyncio
import sys

import httpx

from d4bl.settings import get_settings


async def main(email: str) -> None:
    settings = get_settings()

    if not settings.supabase_url or not settings.supabase_service_role_key:
        print("Error: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set")
        sys.exit(1)

    # Invite the user
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{settings.supabase_url}/auth/v1/invite",
            json={"email": email},
            headers={
                "apikey": settings.supabase_service_role_key,
                "Authorization": f"Bearer {settings.supabase_service_role_key}",
                "Content-Type": "application/json",
            },
        )

    if response.status_code >= 400:
        print(f"Error inviting user: {response.text}")
        sys.exit(1)

    user_data = response.json()
    user_id = user_data.get("id")

    # Set the user as admin in profiles
    if user_id:
        async with httpx.AsyncClient() as client:
            response = await client.patch(
                f"{settings.supabase_url}/rest/v1/profiles?id=eq.{user_id}",
                json={"role": "admin"},
                headers={
                    "apikey": settings.supabase_service_role_key,
                    "Authorization": f"Bearer {settings.supabase_service_role_key}",
                    "Content-Type": "application/json",
                    "Prefer": "return=minimal",
                },
            )

    print(f"Admin invitation sent to {email}")
    print("The user will receive an email with a link to set their password.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python scripts/bootstrap_admin.py <admin-email>")
        sys.exit(1)

    asyncio.run(main(sys.argv[1]))
```

**Step 2: Commit**

```bash
git add scripts/bootstrap_admin.py
git commit -m "feat: add admin bootstrap script for initial setup"
```

---

### Task 12: Update documentation

**Files:**
- Modify: `CLAUDE.md`
- Modify: `docs/API.md`

**Step 1: Update CLAUDE.md**

Add to the Configuration section:

```markdown
## Authentication

All API endpoints (except `/`, `/api/health`, `/api/models`) require a valid Supabase JWT in the `Authorization: Bearer <token>` header.

```
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_JWT_SECRET=your-jwt-secret
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
ADMIN_EMAIL=first-admin@example.com
NEXT_PUBLIC_SUPABASE_URL=https://your-project.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=your-anon-key
```
```

**Step 2: Update docs/API.md**

Replace the "no authentication" note with documentation of the auth scheme.

**Step 3: Commit**

```bash
git add CLAUDE.md docs/API.md
git commit -m "docs: update API and project docs with auth configuration"
```

---

### Task 13: Add httpx dependency

**Files:**
- Modify: `pyproject.toml`

**Step 1: Add httpx to dependencies**

`httpx` is needed for the admin invite endpoint and bootstrap script. Add to the `dependencies` list in `pyproject.toml`:

```toml
"httpx>=0.27",
```

Note: `httpx` is already in `[project.optional-dependencies] test`, so it's available in dev. Adding it to main deps ensures it's available in production.

**Step 2: Install**

Run: `pip install httpx`

**Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "chore: add httpx to production dependencies for admin API calls"
```

---

Plan complete and saved to `docs/plans/2026-03-07-rbac-auth-implementation.md`. Two execution options:

**1. Subagent-Driven (this session)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Parallel Session (separate)** - Open a new session with executing-plans, batch execution with checkpoints

Which approach?