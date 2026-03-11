# Dagster UI Auth Proxy Design

**Issue**: #71 — Add authentication to Dagster UI on Fly.io
**Date**: 2026-03-10

## Problem

The Dagster webserver at `d4bl-dagster-web.fly.dev` is publicly accessible with no authentication. Anyone can view pipeline status, trigger runs, and access operational data.

## Solution

Add a lightweight auth proxy inside the Dagster container that validates Supabase JWTs and restricts access to admin users.

## How It Works

1. **Auth proxy** (small FastAPI app) runs on port 8080 inside the Dagster container, forwarding authenticated requests to Dagster on localhost:3003.
2. **JWT validation**: The proxy reads a `dagster_token` cookie, verifies it as a valid Supabase JWT, and checks that the user has `role = 'admin'`.
3. **Login flow**: Unauthenticated requests get a simple login page that redirects to Supabase auth, stores the JWT in the cookie, then redirects back.
4. **Frontend integration**: Add a "Dagster Pipelines" link on the `/admin` page that opens the Dagster UI in a new tab, passing the user's existing session token.

## Components

### `dagster/auth_proxy.py`

Small FastAPI app (~100 lines):

- Middleware that intercepts all requests
- Reads `dagster_token` cookie
- Validates JWT signature using `SUPABASE_JWT_SECRET`
- Queries Supabase for admin role check (or decodes from JWT claims)
- Proxies valid requests to `http://localhost:3003` via `httpx`
- Returns 401 + login page for unauthenticated requests

### `dagster/Dockerfile` changes

- Add `python-jose` dependency for JWT validation
- Change entrypoint to a script that starts both the auth proxy (port 8080) and Dagster webserver (port 3003)
- Auth proxy is the externally-facing service

### `fly.dagster-web.toml` changes

- Change `internal_port` from 3003 to 8080

### `dagster/entrypoint.sh`

Starts both processes:

- `dagster-webserver -h 127.0.0.1 -p 3003 &` (binds to localhost only)
- `uvicorn auth_proxy:app --host 0.0.0.0 --port 8080`

### Frontend changes

- Add "Open Dagster UI" button on the admin page that sets the `dagster_token` cookie on the Dagster domain via a redirect endpoint, then opens the Dagster UI

## Out of Scope

- No changes to the daemon (it has no HTTP service)
- No new Fly.io apps
- No nginx/Caddy — pure Python to keep dependencies minimal

## Environment Variables Required

The Dagster webserver container needs these additional env vars (already available in the API service):

- `SUPABASE_JWT_SECRET` — for JWT signature verification
- `SUPABASE_URL` — for the login redirect flow
- `SUPABASE_ANON_KEY` — for the login page's Supabase client
