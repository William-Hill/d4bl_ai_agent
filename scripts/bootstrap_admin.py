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
