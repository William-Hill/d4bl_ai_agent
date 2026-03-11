"""Auth proxy for the Dagster webserver.

Validates Supabase JWTs from a cookie and proxies authenticated admin
requests to the Dagster webserver running on localhost:3003.
"""
from __future__ import annotations

import logging
import os
import time
from contextlib import asynccontextmanager

import httpx
import jwt
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, Response, RedirectResponse
from starlette.routing import Route

logger = logging.getLogger(__name__)

DAGSTER_UPSTREAM = "http://127.0.0.1:3003"
COOKIE_NAME = "dagster_token"
_ADMIN_CACHE_TTL = 60  # seconds

# Read config from env
_jwt_secret = lambda: os.environ.get("SUPABASE_JWT_SECRET", "")
_supabase_url = lambda: os.environ.get("SUPABASE_URL", "")
_supabase_anon_key = lambda: os.environ.get("SUPABASE_ANON_KEY", "")

# TTL cache for admin checks: {user_id: (is_admin, timestamp)}
_admin_cache: dict[str, tuple[bool, float]] = {}

# Shared httpx client, initialized in lifespan
_http_client: httpx.AsyncClient | None = None


def _decode_token(token: str) -> dict | None:
    """Decode and verify a Supabase JWT. Returns claims or None."""
    try:
        return jwt.decode(token, _jwt_secret(), algorithms=["HS256"], audience="authenticated")
    except (jwt.InvalidTokenError, jwt.ExpiredSignatureError):
        return None


async def _check_admin(user_id: str) -> bool:
    """Check if the user has admin role via the Supabase REST API.

    Results are cached for _ADMIN_CACHE_TTL seconds to avoid hitting
    the Supabase API on every proxied request (JS, CSS, assets, etc.).
    """
    now = time.monotonic()
    cached = _admin_cache.get(user_id)
    if cached and (now - cached[1]) < _ADMIN_CACHE_TTL:
        return cached[0]

    supabase_url = _supabase_url()
    service_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not supabase_url or not service_key:
        logger.warning("Supabase config missing, denying admin check")
        return False
    try:
        client = _http_client or httpx.AsyncClient()
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
        is_admin = len(rows) > 0 and rows[0].get("role") == "admin"
        _admin_cache[user_id] = (is_admin, now)
        return is_admin
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
        client = _http_client or httpx.AsyncClient()
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


@asynccontextmanager
async def _lifespan(app):
    global _http_client
    _http_client = httpx.AsyncClient()
    yield
    await _http_client.aclose()
    _http_client = None


# Routes — auth endpoints first, then catch-all proxy
routes = [
    Route("/auth/set-token", _set_token),
    Route("/auth/logout", _logout),
    Route("/{path:path}", _proxy, methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"]),
]

app = Starlette(routes=routes, lifespan=_lifespan)
