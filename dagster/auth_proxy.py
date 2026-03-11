"""Auth proxy for the Dagster webserver.

Validates Supabase JWTs from a cookie and proxies authenticated admin
requests to the Dagster webserver running on localhost:3003.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from contextlib import asynccontextmanager

import httpx
import jwt
from jwt import PyJWK
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response
from starlette.routing import Route

logger = logging.getLogger(__name__)

DAGSTER_UPSTREAM = "http://127.0.0.1:3003"
COOKIE_NAME = "dagster_token"
_ADMIN_CACHE_TTL = 60  # seconds
_JWKS_TTL = 3600  # seconds

def _allowed_origins() -> list[str]:
    """Allowed origins for cross-origin set-token requests from the admin page."""
    return [
        o.strip()
        for o in os.environ.get("CORS_ALLOWED_ORIGINS", "http://localhost:3000").split(",")
        if o.strip()
    ]

# Headers that must not be forwarded by proxies (RFC 2616 Section 13.5.1)
_HOP_BY_HOP = frozenset({
    "transfer-encoding", "connection", "keep-alive", "te",
    "trailers", "upgrade", "proxy-authorization", "proxy-authenticate",
})

def _jwt_secret() -> str:
    return os.environ.get("SUPABASE_JWT_SECRET", "")


def _supabase_url() -> str:
    return os.environ.get("SUPABASE_URL", "")


def _supabase_anon_key() -> str:
    return os.environ.get("SUPABASE_ANON_KEY", "")

# TTL cache for admin checks: {user_id: (is_admin, timestamp)}
_MAX_ADMIN_CACHE_SIZE = 1000
_admin_cache: dict[str, tuple[bool, float]] = {}

# Shared httpx client, initialized in lifespan
_http_client: httpx.AsyncClient | None = None

# JWKS cache for ES256 verification
_jwks_cache: dict[str, PyJWK] = {}
_jwks_cache_time: float = 0.0
_jwks_lock = threading.Lock()


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
        _jwks_cache = new_cache
        _jwks_cache_time = time.monotonic()
    except Exception:
        logger.exception("Failed to fetch JWKS from Supabase")


def _get_jwks_key(kid: str, supabase_url: str) -> PyJWK | None:
    """Get a JWKS key by kid, refreshing cache if needed."""
    with _jwks_lock:
        if kid not in _jwks_cache or (time.monotonic() - _jwks_cache_time) > _JWKS_TTL:
            _refresh_jwks(supabase_url)
    return _jwks_cache.get(kid)


def _decode_token(token: str) -> dict | None:
    """Decode and verify a Supabase JWT. Supports both ES256 (JWKS) and HS256."""
    try:
        header = jwt.get_unverified_header(token)
        alg = header.get("alg", "HS256")
        kid = header.get("kid")
        supabase_url = _supabase_url()

        if alg == "ES256" and kid and supabase_url:
            jwk = _get_jwks_key(kid, supabase_url)
            if jwk is None:
                return None
            return jwt.decode(token, jwk.key, algorithms=["ES256"], audience="authenticated")

        return jwt.decode(token, _jwt_secret(), algorithms=["HS256"], audience="authenticated")
    except jwt.InvalidTokenError:
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
        if _http_client is None:
            raise RuntimeError("httpx client not initialized")
        client = _http_client
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
        # Evict oldest entries if cache is full
        if len(_admin_cache) >= _MAX_ADMIN_CACHE_SIZE:
            oldest_key = min(_admin_cache, key=lambda k: _admin_cache[k][1])
            del _admin_cache[oldest_key]
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
      // Set cookie via POST, then redirect to Dagster
      fetch("/auth/set-token", {{
        method: "POST",
        headers: {{"Content-Type": "application/json"}},
        body: JSON.stringify({{token: data.session.access_token}})
      }}).then(r => {{ if (r.ok) window.location.href = "/"; }});
    }});
  </script>
</body>
</html>"""
    return HTMLResponse(html)


def _cors_origin(request: Request) -> str | None:
    """Return the request Origin if it is in the allowed list, else None."""
    origin = request.headers.get("origin", "")
    if origin in _allowed_origins():
        return origin
    return None


def _add_cors_headers(response: Response, origin: str) -> None:
    """Add CORS headers for credentialed cross-origin requests."""
    response.headers["Access-Control-Allow-Origin"] = origin
    response.headers["Access-Control-Allow-Credentials"] = "true"


async def _set_token(request: Request) -> Response:
    """Set the JWT cookie via POST body (JSON: {"token": "..."}).

    Supports cross-origin requests from the admin frontend by handling
    CORS preflight and emitting the required CORS headers.
    """
    origin = _cors_origin(request)

    # Handle CORS preflight
    if request.method == "OPTIONS":
        resp = Response(status_code=204)
        if origin:
            _add_cors_headers(resp, origin)
            resp.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
            resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
        return resp

    try:
        body = await request.body()
        data = json.loads(body)
        token = data.get("token", "")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return HTMLResponse("Invalid request body", status_code=400)
    if not token:
        return HTMLResponse("Missing token", status_code=400)
    response = Response(status_code=200, headers={"Content-Type": "application/json"})
    response.body = b'{"ok": true}'
    response.set_cookie(
        COOKIE_NAME, token, httponly=True, secure=True,
        samesite="none", max_age=3600,
    )
    if origin:
        _add_cors_headers(response, origin)
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
        if _http_client is None:
            raise RuntimeError("httpx client not initialized")
        client = _http_client
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
            headers={k: v for k, v in proxy_resp.headers.items() if k.lower() not in _HOP_BY_HOP},
        )
    except httpx.ConnectError:
        return HTMLResponse("Dagster webserver is starting up. Refresh in a moment.", status_code=502)
    except Exception:
        logger.exception("Proxy error")
        return HTMLResponse("Proxy error", status_code=502)


async def _healthz(request: Request) -> Response:
    """Unauthenticated health check that also verifies the upstream Dagster webserver."""
    if _http_client is None:
        return Response("Proxy not initialized", status_code=503)
    try:
        resp = await _http_client.get(f"{DAGSTER_UPSTREAM}/server_info", timeout=5.0)
        resp.raise_for_status()
    except Exception:
        return Response("Dagster upstream unhealthy", status_code=503)
    return Response("ok", status_code=200)


@asynccontextmanager
async def _lifespan(app):
    global _http_client
    _http_client = httpx.AsyncClient()
    # Pre-fetch JWKS at startup so the first request doesn't block
    supabase_url = _supabase_url()
    if supabase_url:
        _refresh_jwks(supabase_url)
    yield
    await _http_client.aclose()
    _http_client = None


# Routes — auth endpoints first, then catch-all proxy
routes = [
    Route("/healthz", _healthz),
    Route("/auth/set-token", _set_token, methods=["POST", "OPTIONS"]),
    Route("/auth/logout", _logout),
    Route("/{path:path}", _proxy, methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"]),
]

app = Starlette(routes=routes, lifespan=_lifespan)
