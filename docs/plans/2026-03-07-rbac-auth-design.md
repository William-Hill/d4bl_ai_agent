# RBAC & Authentication Design

**Date:** 2026-03-07
**Status:** Approved
**Approach:** Supabase Auth + RLS + Backend Middleware

## Summary

Add user authentication and role-based access control (RBAC) to the D4BL Research and Analysis Tool. Users log in via Supabase Auth, research jobs are scoped to their owner, and admins can manage users and see all data. Registration is invite-only.

## Decisions

- **Auth provider:** Supabase Auth (email/password, invite-only)
- **Roles:** `user` and `admin`
- **Job visibility:** Private by default (users see own jobs, admins see all)
- **Explore pages:** Open to all authenticated users
- **Registration:** Invite-only (admins invite via email)

## Section 1: Data Model

### `profiles` table (Supabase, linked to `auth.users`)

| Column | Type | Notes |
|--------|------|-------|
| `id` | `uuid` | PK, references `auth.users(id)` |
| `email` | `text` | Denormalized from auth.users |
| `role` | `text` | `'user'` or `'admin'`, default `'user'` |
| `display_name` | `text` | Optional |
| `created_at` | `timestamptz` | Default `now()` |
| `updated_at` | `timestamptz` | Default `now()` |

### Changes to `research_jobs` table

- Replace `tenant_id` column with `user_id uuid REFERENCES auth.users(id)`
- Add index on `user_id`

### RLS policies on `research_jobs`

- Users can `SELECT` rows where `user_id = auth.uid()`
- Admins can `SELECT` all rows
- `INSERT` requires `user_id = auth.uid()`
- No direct `UPDATE`/`DELETE` from client (backend handles via service role)

### Trigger

Auto-create a `profiles` row when a user is added to `auth.users` (standard Supabase pattern).

## Section 2: Backend Authentication

### JWT Middleware (`src/d4bl/app/auth.py` -- new file)

- FastAPI dependency that extracts `Authorization: Bearer <token>` header
- Validates JWT against Supabase's JWT secret (`SUPABASE_JWT_SECRET` env var)
- Decodes claims to get `sub` (user ID) and fetches role from `profiles` table (cached briefly)
- Returns a `CurrentUser` dataclass with `id`, `email`, `role`
- Raises `401` for missing/invalid tokens, `403` for insufficient role

### Endpoint changes

```python
# Any authenticated user
@app.post("/api/research")
async def create_research(request: ResearchRequest, user: CurrentUser = Depends(get_current_user)):
    # user.id used as job owner

# Admin only
@app.get("/api/admin/users")
async def list_users(user: CurrentUser = Depends(require_admin)):
    ...
```

**Modified endpoints:**
- `POST /api/research` -- set `user_id` from authenticated user instead of `tenant_id`
- `GET /api/jobs` -- filter by `user_id` unless admin
- `GET /api/jobs/{job_id}` -- verify ownership or admin
- `WS /ws/{job_id}` -- validate JWT on connection, verify job ownership
- Explore/query endpoints -- require authentication, no ownership filtering
- `POST /api/evaluations` -- admin only

### Settings additions

- `SUPABASE_JWT_SECRET` -- for JWT validation
- `SUPABASE_URL` -- for admin API calls
- `SUPABASE_SERVICE_ROLE_KEY` -- for admin operations (invite users, manage profiles)

## Section 3: Frontend Authentication

### Supabase client (`ui-nextjs/lib/supabase.ts` -- new file)

- Browser client using `@supabase/ssr` with cookie-based session storage
- `NEXT_PUBLIC_SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_ANON_KEY` env vars

### Next.js middleware (`ui-nextjs/middleware.ts` -- new file)

- Refreshes Supabase session on every request
- Redirects unauthenticated users to `/login`
- Allows `/login` page without auth

### Pages

- `/login` -- email/password form, calls `supabase.auth.signInWithPassword()`
- No signup page (invite-only)

### Layout changes (`ui-nextjs/app/layout.tsx`)

- Add user menu to nav bar (email display, role badge, sign out button)
- Wrap app in auth context provider

### Auth context (`ui-nextjs/lib/auth-context.tsx` -- new file)

- React context providing `user`, `role`, `isAdmin`, `signOut`
- Fetches role from backend on session load

### API client changes (`ui-nextjs/lib/api.ts`)

- All requests include `Authorization: Bearer <access_token>` header
- Token retrieved from Supabase session
- On 401 response, redirect to `/login`

### Role-based UI

- Admin users see an "Admin" link in nav
- Job history only shows the user's own jobs (enforced by backend)

## Section 4: Admin Features

### Admin API endpoints (new routes in `api.py`)

- `POST /api/admin/invite` -- accepts `email`, calls Supabase `auth.admin.invite_user_by_email()` via service role key
- `GET /api/admin/users` -- lists all profiles with roles
- `PATCH /api/admin/users/{user_id}` -- update role (`user`/`admin`)
- All gated behind `require_admin` dependency

### Admin frontend page (`ui-nextjs/app/admin/page.tsx`)

- Table of users (email, role, created date)
- "Invite User" button with email input modal
- Role toggle dropdown per user
- Protected by role check -- redirects non-admins

### First admin bootstrapping

- Migration or setup script sets first user's role to `admin`
- Alternatively, `ADMIN_EMAIL` env var seeds the first admin when the profile trigger fires

## Section 5: Migration Strategy

### Handling existing data

- Existing `research_jobs` rows have `tenant_id` but no `user_id`
- Migration adds `user_id` column as nullable first
- Existing jobs remain accessible to admins only (no owner)
- After migration, `tenant_id` column is dropped

### Rollout steps

1. Deploy Supabase Auth configuration (enable email provider, disable public signups)
2. Run database migration: add `profiles` table, add `user_id` to `research_jobs`, create RLS policies, create auth trigger
3. Deploy backend with auth middleware (all endpoints require JWT)
4. Deploy frontend with login page and auth context
5. Bootstrap first admin via script/migration
6. Admin invites remaining users

### CLI unchanged

- CLI (`src/d4bl/main.py`) remains unauthenticated for local usage -- it doesn't go through the API
- Auth is API-layer only
