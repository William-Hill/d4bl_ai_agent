#!/usr/bin/env python
"""
Ingest state policy bills from OpenStates GraphQL API into policy_bills table.

Usage:
    python scripts/ingest_openstates.py [--state ms] [--session 2025] [--dry-run]

Env vars:
    OPENSTATES_API_KEY   (required)
    POSTGRES_*           (connection settings)
"""
import argparse
import asyncio
import os
import sys
from pathlib import Path
from typing import Optional

import aiohttp
from sqlalchemy.dialects.postgresql import insert

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import d4bl.infra.database as dbmod
from d4bl.infra.database import PolicyBill

OPENSTATES_URL = "https://v3.openstates.org/graphql"

# D4BL focus topic tags to search for
FOCUS_SUBJECTS = [
    "housing",
    "wealth",
    "education",
    "criminal justice",
    "voting rights",
    "economic development",
    "health care",
]

# Map OpenStates status strings to our simplified enum
STATUS_MAP = {
    "introduced": "introduced",
    "in committee": "introduced",
    "referred to committee": "introduced",
    "passed upper": "passed",
    "passed lower": "passed",
    "passed": "passed",
    "signed": "signed",
    "vetoed": "failed",
    "failed": "failed",
    "dead": "failed",
}

BILLS_QUERY = """
query BillsByState($state: String!, $session: String, $subject: String, $after: String) {
  bills(jurisdiction: $state, session: $session, subject: $subject, after: $after, first: 50) {
    pageInfo { hasNextPage endCursor }
    edges {
      node {
        id
        identifier
        title
        abstract
        classification
        subject
        session { identifier }
        createdAt
        updatedAt
        statusText
        sources { url }
      }
    }
  }
}
"""


async def fetch_bills_for_subject(
    http: aiohttp.ClientSession,
    api_key: str,
    state: str,
    session: Optional[str],
    subject: str,
) -> list[dict]:
    """Fetch all pages of bills for a given state and subject."""
    bills: list[dict] = []
    after: Optional[str] = None
    headers = {"X-API-Key": api_key}

    while True:
        variables: dict[str, object] = {"state": state, "subject": subject}
        if session:
            variables["session"] = session
        if after:
            variables["after"] = after

        async with http.post(
            OPENSTATES_URL,
            json={"query": BILLS_QUERY, "variables": variables},
            headers=headers,
        ) as resp:
            resp.raise_for_status()
            data = await resp.json()

        edges = data.get("data", {}).get("bills", {}).get("edges", [])
        page_info = data.get("data", {}).get("bills", {}).get("pageInfo", {})

        for edge in edges:
            bills.append(edge["node"])

        if not page_info.get("hasNextPage"):
            break
        after = page_info["endCursor"]

    return bills


def map_status(status_text: Optional[str]) -> str:
    if not status_text:
        return "other"
    lower = status_text.lower()
    for key, value in STATUS_MAP.items():
        if key in lower:
            return value
    return "other"


# Map OpenStates jurisdiction slug to 2-letter abbreviation and full name
STATE_MAP: dict[str, tuple[str, str]] = {
    "al": ("AL", "Alabama"),
    "ak": ("AK", "Alaska"),
    "az": ("AZ", "Arizona"),
    "ar": ("AR", "Arkansas"),
    "ca": ("CA", "California"),
    "co": ("CO", "Colorado"),
    "ct": ("CT", "Connecticut"),
    "de": ("DE", "Delaware"),
    "fl": ("FL", "Florida"),
    "ga": ("GA", "Georgia"),
    "hi": ("HI", "Hawaii"),
    "id": ("ID", "Idaho"),
    "il": ("IL", "Illinois"),
    "in": ("IN", "Indiana"),
    "ia": ("IA", "Iowa"),
    "ks": ("KS", "Kansas"),
    "ky": ("KY", "Kentucky"),
    "la": ("LA", "Louisiana"),
    "me": ("ME", "Maine"),
    "md": ("MD", "Maryland"),
    "ma": ("MA", "Massachusetts"),
    "mi": ("MI", "Michigan"),
    "mn": ("MN", "Minnesota"),
    "ms": ("MS", "Mississippi"),
    "mo": ("MO", "Missouri"),
    "mt": ("MT", "Montana"),
    "ne": ("NE", "Nebraska"),
    "nv": ("NV", "Nevada"),
    "nh": ("NH", "New Hampshire"),
    "nj": ("NJ", "New Jersey"),
    "nm": ("NM", "New Mexico"),
    "ny": ("NY", "New York"),
    "nc": ("NC", "North Carolina"),
    "nd": ("ND", "North Dakota"),
    "oh": ("OH", "Ohio"),
    "ok": ("OK", "Oklahoma"),
    "or": ("OR", "Oregon"),
    "pa": ("PA", "Pennsylvania"),
    "ri": ("RI", "Rhode Island"),
    "sc": ("SC", "South Carolina"),
    "sd": ("SD", "South Dakota"),
    "tn": ("TN", "Tennessee"),
    "tx": ("TX", "Texas"),
    "ut": ("UT", "Utah"),
    "vt": ("VT", "Vermont"),
    "va": ("VA", "Virginia"),
    "wa": ("WA", "Washington"),
    "wv": ("WV", "West Virginia"),
    "wi": ("WI", "Wisconsin"),
    "wy": ("WY", "Wyoming"),
}


async def ingest_state(
    db_session,
    http: aiohttp.ClientSession,
    api_key: str,
    state_slug: str,
    session_id: Optional[str],
    dry_run: bool,
) -> int:
    """Ingest all focus-topic bills for one state. Returns row count."""
    abbrev, full_name = STATE_MAP.get(state_slug.lower(), (state_slug.upper(), state_slug))
    count = 0
    seen_ids: set[str] = set()

    for subject in FOCUS_SUBJECTS:
        try:
            bills = await fetch_bills_for_subject(http, api_key, state_slug, session_id, subject)
        except Exception as e:  # pragma: no cover - defensive logging
            print(f"  Warning: {state_slug}/{subject} failed: {e}", file=sys.stderr)
            continue

        for bill in bills:
            bill_id = bill["id"]
            if bill_id in seen_ids:
                continue
            seen_ids.add(bill_id)

            url = bill.get("sources", [{}])[0].get("url") if bill.get("sources") else None
            sess = bill.get("session", {}).get("identifier", session_id or "")

            if not dry_run:
                stmt = (
                    insert(PolicyBill)
                    .values(
                        state=abbrev,
                        state_name=full_name,
                        bill_id=bill_id,
                        bill_number=bill.get("identifier", ""),
                        title=bill.get("title", ""),
                        summary=bill.get("abstract"),
                        status=map_status(bill.get("statusText")),
                        topic_tags=bill.get("subject", []),
                        session=sess,
                        url=url,
                        introduced_date=bill.get("createdAt"),
                        last_action_date=bill.get("updatedAt"),
                    )
                    .on_conflict_do_update(
                        index_elements=["state", "bill_id", "session"],
                        set={
                            "state_name": full_name,
                            "bill_number": bill.get("identifier", ""),
                            "title": bill.get("title", ""),
                            "summary": bill.get("abstract"),
                            "status": map_status(bill.get("statusText")),
                            "topic_tags": bill.get("subject", []),
                            "url": url,
                            "introduced_date": bill.get("createdAt"),
                            "last_action_date": bill.get("updatedAt"),
                        },
                    )
                )
                await db_session.execute(stmt)
            count += 1

    if not dry_run:
        await db_session.commit()

    return count


async def main(state_filter: Optional[str], session_id: Optional[str], dry_run: bool) -> None:
    api_key = os.getenv("OPENSTATES_API_KEY")
    if not api_key:
        print("Error: OPENSTATES_API_KEY environment variable required", file=sys.stderr)
        sys.exit(1)

    dbmod.init_db()
    assert dbmod.async_session_maker is not None, "init_db() must set async_session_maker"
    if not dry_run:
        await dbmod.create_tables()

    states = [state_filter] if state_filter else list(STATE_MAP.keys())
    total = 0

    print(f"Ingesting OpenStates bills (states={len(states)}, dry_run={dry_run})")

    async with dbmod.async_session_maker() as db:
        async with aiohttp.ClientSession() as http:
            for state_slug in states:
                count = await ingest_state(db, http, api_key, state_slug, session_id, dry_run)
                print(f"  {state_slug}: {count} bills")
                total += count

    print(f"Done. {total} total bills {'would be' if dry_run else ''} ingested.")
    await dbmod.close_db()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest OpenStates policy bills")
    parser.add_argument(
        "--state",
        default=None,
        help="State slug, e.g. ms for Mississippi",
    )
    parser.add_argument(
        "--session",
        default=None,
        help="Session identifier, e.g. 2025",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch but do not write to DB",
    )
    args = parser.parse_args()

    asyncio.run(main(args.state, args.session, args.dry_run))

