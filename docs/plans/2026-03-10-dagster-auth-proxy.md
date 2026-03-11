# Dagster Auth Proxy Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Gate the Dagster UI behind Supabase JWT auth so only admin users can access it.

**Architecture:** A small FastAPI reverse proxy runs on port 8080 in the Dagster container, validating a `dagster_token` cookie before forwarding requests to the Dagster webserver on localhost:3003. The frontend admin page gets a link that opens the Dagster UI in a new tab.

**Tech Stack:** FastAPI, httpx, PyJWT, Supabase auth

---

### Task 1: Auth proxy — JWT validation and proxying

**Files:**
- Create: `dagster/auth_proxy.py`
- Create: `dagster/tests/test_auth_proxy.py`

**Step 1: Write the failing tests**

Create `dagster/tests/test_auth_proxy.py`:

```python
"""Tests for the Dagster auth proxy."""
from __future__ import annotations

import time
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import jwt
import pytest
from httpx import ASGITransport, AsyncClient

TEST_SECRET = "test-secret-key"
TEST_USER_ID = str(uuid4())


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
    # Re-import to pick up env vars
    import importlib
    import dagster.auth_proxy as mod
    importlib.reload(mod)
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
    with patch("dagster.auth_proxy._check_admin", new_callable=AsyncMock, return_value=False):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/", cookies={"dagster_token": token})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_proxies_request(app):
    token = _make_token()
    with patch("dagster.auth_proxy._check_admin", new_callable=AsyncMock, return_value=True):
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
```

**Step 2: Run tests to verify they fail**

Run: `cd dagster && python -m pytest tests/test_auth_proxy.py -v`
Expected: FAIL (module not found)

**Step 3: Write the auth proxy**

Create `dagster/auth_proxy.py`:

```python
"""Auth proxy for the Dagster webserver.

Validates Supabase JWTs from a cookie and proxies authenticated admin
requests to the Dagster webserver running on localhost:3003.
"""
from __future__ import annotations

import logging
import os

import httpx
import jwt
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, Response, RedirectResponse
from starlette.routing import Route

logger = logging.getLogger(__name__)

DAGSTER_UPSTREAM = "http://127.0.0.1:3003"
COOKIE_NAME = "dagster_token"

# Read config from env
_jwt_secret = lambda: os.environ.get("SUPABASE_JWT_SECRET", "")
_supabase_url = lambda: os.environ.get("SUPABASE_URL", "")
_supabase_anon_key = lambda: os.environ.get("SUPABASE_ANON_KEY", "")


def _decode_token(token: str) -> dict | None:
    """Decode and verify a Supabase JWT. Returns claims or None."""
    try:
        return jwt.decode(token, _jwt_secret(), algorithms=["HS256"], audience="authenticated")
    except (jwt.InvalidTokenError, jwt.ExpiredSignatureError):
        return None


async def _check_admin(user_id: str) -> bool:
    """Check if the user has admin role via the D4BL API's admin endpoint.

    Uses the user's own token forwarded to the API, but for simplicity
    we query the profiles table via the Supabase REST API.
    """
    supabase_url = _supabase_url()
    service_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not supabase_url or not service_key:
        logger.warning("Supabase config missing, denying admin check")
        return False
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{supabase_url}/rest/v1/profiles",
                params={"id": f"eq.{user_id}", "select": "role"},
                headers={
                    "apikey": service_key,
                    "Authorization": f"Bearer {service_key}",
                },
                timeout=10.0,
            )
            resp.raise_for_status()
            rows = resp.json()
            return len(rows) > 0 and rows[0].get("role") == "admin"
    except Exception:
        logger.exception("Admin check failed")
        return False


def _login_page() -> HTMLResponse:
    """Return a minimal login page that uses Supabase JS to sign in."""
    supabase_url = _supabase_url()
    anon_key = _supabase_anon_key()
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Dagster — Sign in</title>
  <style>
    body {{ margin:0; min-height:100vh; display:flex; align-items:center; justify-content:center;
           background:#1a1a1a; color:#e0e0e0; font-family:system-ui,sans-serif; }}
    .card {{ background:#292929; border:1px solid #404040; border-radius:12px; padding:2rem;
             width:100%; max-width:380px; }}
    h1 {{ margin:0 0 1.5rem; font-size:1.25rem; text-align:center; }}
    input {{ width:100%; padding:0.6rem; margin-bottom:0.75rem; background:#1a1a1a;
             border:1px solid #404040; border-radius:6px; color:#fff; box-sizing:border-box; }}
    input:focus {{ outline:none; border-color:#00ff32; }}
    button {{ width:100%; padding:0.6rem; background:#00ff32; color:#000; font-weight:600;
              border:none; border-radius:6px; cursor:pointer; }}
    button:hover {{ background:#00cc28; }}
    .error {{ color:#ff6b6b; font-size:0.85rem; margin-top:0.5rem; text-align:center; display:none; }}
  </style>
  <script src="https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2/dist/umd/supabase.min.js"></script>
</head>
<body>
  <div class="card">
    <h1>Sign in to Dagster</h1>
    <form id="login-form">
      <input type="email" id="email" placeholder="Email" required>
      <input type="password" id="password" placeholder="Password" required>
      <button type="submit">Sign in</button>
      <p class="error" id="error"></p>
    </form>
  </div>
  <script>
    const supabase = window.supabase.createClient("{supabase_url}", "{anon_key}");
    document.getElementById("login-form").addEventListener("submit", async (e) => {{
      e.preventDefault();
      const email = document.getElementById("email").value;
      const password = document.getElementById("password").value;
      const errEl = document.getElementById("error");
      errEl.style.display = "none";
      const {{ data, error }} = await supabase.auth.signInWithPassword({{ email, password }});
      if (error) {{
        errEl.textContent = error.message;
        errEl.style.display = "block";
        return;
      }}
      // Set cookie via our endpoint, then redirect to Dagster
      window.location.href = "/auth/set-token?token=" + data.session.access_token;
    }});
  </script>
</body>
</html>"""
    return HTMLResponse(html)


async def _set_token(request: Request) -> Response:
    """Set the JWT cookie and redirect to the Dagster UI root."""
    token = request.query_params.get("token", "")
    if not token:
        return HTMLResponse("Missing token", status_code=400)
    response = RedirectResponse(url="/", status_code=307)
    response.set_cookie(
        COOKIE_NAME, token, httponly=True, secure=True, samesite="lax", max_age=3600
    )
    return response


async def _logout(request: Request) -> Response:
    """Clear the auth cookie and redirect to login."""
    response = RedirectResponse(url="/", status_code=307)
    response.delete_cookie(COOKIE_NAME)
    return response


async def _proxy(request: Request) -> Response:
    """Validate JWT cookie, check admin role, and proxy to Dagster."""
    token = request.cookies.get(COOKIE_NAME)

    if not token:
        return _login_page()

    claims = _decode_token(token)
    if claims is None:
        # Invalid/expired token — clear cookie and show login
        resp = _login_page()
        resp.delete_cookie(COOKIE_NAME)
        return resp

    user_id = claims.get("sub")
    if not user_id:
        return _login_page()

    if not await _check_admin(user_id):
        return HTMLResponse("Access denied. Admin role required.", status_code=403)

    # Proxy the request to Dagster
    url = f"{DAGSTER_UPSTREAM}{request.url.path}"
    if request.url.query:
        url += f"?{request.url.query}"

    try:
        body = await request.body()
        async with httpx.AsyncClient() as client:
            proxy_resp = await client.request(
                method=request.method,
                url=url,
                headers={
                    k: v for k, v in request.headers.items()
                    if k.lower() not in ("host", "cookie")
                },
                content=body,
                timeout=30.0,
            )
        return Response(
            content=proxy_resp.content,
            status_code=proxy_resp.status_code,
            headers=dict(proxy_resp.headers),
        )
    except httpx.ConnectError:
        return HTMLResponse("Dagster webserver is starting up. Refresh in a moment.", status_code=502)
    except Exception:
        logger.exception("Proxy error")
        return HTMLResponse("Proxy error", status_code=502)


# Routes — auth endpoints first, then catch-all proxy
routes = [
    Route("/auth/set-token", _set_token),
    Route("/auth/logout", _logout),
]

app = Starlette(routes=routes, default=_proxy)
```

**Step 4: Run tests to verify they pass**

Run: `cd dagster && python -m pytest tests/test_auth_proxy.py -v`
Expected: All 6 tests PASS

**Step 5: Commit**

```bash
git add dagster/auth_proxy.py dagster/tests/test_auth_proxy.py
git commit -m "feat: add auth proxy for Dagster UI (#71)"
```

---

### Task 2: Entrypoint script and Dockerfile changes

**Files:**
- Create: `dagster/entrypoint.sh`
- Modify: `dagster/Dockerfile:6,18,20-23`
- Modify: `dagster/requirements.txt`

**Step 1: Add PyJWT to requirements**

Add to `dagster/requirements.txt`:

```
PyJWT>=2.8
```

**Step 2: Create entrypoint script**

Create `dagster/entrypoint.sh`:

```bash
#!/bin/sh
set -e

# Start Dagster webserver in background (localhost only)
dagster-webserver -h 127.0.0.1 -p 3003 &
DAGSTER_PID=$!

# Start auth proxy on externally-facing port
exec uvicorn auth_proxy:app --host 0.0.0.0 --port 8080 --log-level info
```

**Step 3: Update Dockerfile**

Modify `dagster/Dockerfile` to:

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY dagster/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt uvicorn

COPY dagster/dagster.yaml dagster/workspace.yaml ./
COPY dagster/d4bl_pipelines/ ./d4bl_pipelines/
COPY dagster/auth_proxy.py dagster/entrypoint.sh ./

ENV DAGSTER_HOME=/app

RUN addgroup --system dagster && adduser --system --ingroup dagster dagster \
    && chown -R dagster:dagster /app \
    && chmod +x /app/entrypoint.sh

USER dagster

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8080/auth/set-token')"]

CMD ["/app/entrypoint.sh"]
```

**Step 4: Verify Dockerfile builds**

Run: `docker build -f dagster/Dockerfile -t dagster-auth-test .`
Expected: Build succeeds

**Step 5: Commit**

```bash
git add dagster/entrypoint.sh dagster/Dockerfile dagster/requirements.txt
git commit -m "feat: add entrypoint and Dockerfile for auth proxy (#71)"
```

---

### Task 3: Update Fly.io and Docker Compose config

**Files:**
- Modify: `fly.dagster-web.toml:8`
- Modify: `docker-compose.dagster.yml:8-10`

**Step 1: Update fly.dagster-web.toml**

Change `internal_port` from 3003 to 8080:

```toml
[http_service]
  internal_port = 8080
```

**Step 2: Update docker-compose.dagster.yml**

Update the webserver service command and port mapping:

```yaml
  dagster-webserver:
    build:
      context: .
      dockerfile: dagster/Dockerfile
    ports:
      - "3003:8080"
    environment:
      DAGSTER_POSTGRES_URL: "postgresql://${POSTGRES_USER:-postgres}:${POSTGRES_PASSWORD:-postgres}@postgres:5432/${POSTGRES_DB:-postgres}"
      POSTGRES_HOST: postgres
      POSTGRES_PORT: "5432"
      POSTGRES_USER: "${POSTGRES_USER:-postgres}"
      POSTGRES_PASSWORD: "${POSTGRES_PASSWORD:-postgres}"
      POSTGRES_DB: "${POSTGRES_DB:-postgres}"
      SUPABASE_JWT_SECRET: "${SUPABASE_JWT_SECRET:-}"
      SUPABASE_URL: "${SUPABASE_URL:-}"
      SUPABASE_ANON_KEY: "${SUPABASE_ANON_KEY:-}"
      SUPABASE_SERVICE_ROLE_KEY: "${SUPABASE_SERVICE_ROLE_KEY:-}"
    depends_on:
      postgres:
        condition: service_healthy
    networks:
      - d4bl-network
```

**Step 3: Commit**

```bash
git add fly.dagster-web.toml docker-compose.dagster.yml
git commit -m "feat: update Fly.io and Compose config for auth proxy port (#71)"
```

---

### Task 4: Add Dagster link to admin page

**Files:**
- Modify: `ui-nextjs/app/admin/page.tsx:115-116`

**Step 1: Add the Dagster UI link**

After the `<h1>` tag in the admin page, add a link section:

```tsx
        <h1 className="text-3xl font-bold text-white mb-8">User Management</h1>

        {/* External tools */}
        <div className="bg-[#1a1a1a] border border-[#404040] rounded-lg p-6 mb-8">
          <h2 className="text-lg font-semibold text-white mb-4">Tools</h2>
          <a
            href={`${process.env.NEXT_PUBLIC_DAGSTER_URL || 'https://d4bl-dagster-web.fly.dev'}/auth/set-token?token=${session?.access_token}`}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-2 px-4 py-2 bg-[#292929] border border-[#404040]
                       rounded text-white hover:border-[#00ff32] transition-colors"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
            </svg>
            Open Dagster Pipelines
          </a>
        </div>
```

**Step 2: Commit**

```bash
git add ui-nextjs/app/admin/page.tsx
git commit -m "feat: add Dagster UI link to admin page (#71)"
```

---

### Task 5: Update CI health check

**Files:**
- Modify: `.github/workflows/deploy-staging.yml:70-72`

**Step 1: Add Dagster health check**

After the existing health checks, add:

```yaml
      - name: Check Dagster UI (auth proxy)
        run: curl --fail --retry 5 --retry-delay 10 https://d4bl-dagster-web.fly.dev/
```

Note: This should return 200 (the login page), confirming the proxy is running.

**Step 2: Commit**

```bash
git add .github/workflows/deploy-staging.yml
git commit -m "feat: add Dagster auth proxy health check to CI (#71)"
```

---

### Task 6: Set Fly.io secrets

**Step 1: Set required secrets on the Dagster web app**

Run (manually, not automated):

```bash
flyctl secrets set \
  SUPABASE_JWT_SECRET=<value> \
  SUPABASE_URL=<value> \
  SUPABASE_ANON_KEY=<value> \
  SUPABASE_SERVICE_ROLE_KEY=<value> \
  --app d4bl-dagster-web
```

This step is manual — values come from the existing Fly.io secrets on the API app.

---

### Task 7: End-to-end verification

**Step 1: Deploy and test**

After merging to main (triggering deploy-staging):

1. Visit `https://d4bl-dagster-web.fly.dev/` — should see login page
2. Log in with admin credentials — should see Dagster UI
3. Log in with non-admin credentials — should see "Access denied"
4. Visit without logging in — should see login page
5. From the main app admin page, click "Open Dagster Pipelines" — should land in Dagster UI authenticated
