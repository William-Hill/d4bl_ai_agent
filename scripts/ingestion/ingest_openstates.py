"""OpenStates policy bills ingestion script.

Fetches state policy bills from the OpenStates REST API v3
for D4BL focus subjects and upserts into the policy_bills table.

Usage:
    DATABASE_URL=postgresql://... OPENSTATES_API_KEY=... \
        python scripts/ingestion/ingest_openstates.py

Environment variables:
    DATABASE_URL           - PostgreSQL connection URL (required)
    OPENSTATES_API_KEY     - OpenStates API key (required)
    OPENSTATES_STATE       - Filter to a single state slug (optional)
    OPENSTATES_SESSION     - Filter to a specific legislative session (optional)
"""

import json
import os
import time

import httpx

from .helpers import (
    get_db_connection, execute_batch, make_record_id,
)

OPENSTATES_URL = "https://v3.openstates.org/bills"

# D4BL focus keywords — used to tag bills locally after fetch
FOCUS_KEYWORDS = {
    "housing": ["housing", "rent", "tenant", "landlord", "eviction",
                 "homelessness", "affordable housing"],
    "wealth": ["wealth", "income", "poverty", "economic inequality"],
    "education": ["education", "school", "student", "teacher",
                   "curriculum", "university"],
    "criminal justice": ["criminal", "justice", "police", "prison",
                         "incarceration", "sentencing", "bail"],
    "voting rights": ["voting", "election", "ballot", "voter",
                       "redistricting", "gerrymandering"],
    "economic development": ["economic development", "jobs", "workforce",
                              "small business", "employment"],
    "health care": ["health", "medicaid", "medicare", "hospital",
                     "insurance", "mental health"],
}

# Map OpenStates status strings to simplified enum
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

# Map OpenStates jurisdiction slug to 2-letter abbreviation and full name
STATE_MAP = {
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

UPSERT_SQL = """
    INSERT INTO policy_bills
        (id, state, state_name,
         bill_id, bill_number,
         title, summary, status,
         topic_tags, session,
         introduced_date,
         last_action_date, url)
    VALUES
        (%(id)s::UUID,
         %(state)s, %(state_name)s,
         %(bill_id)s, %(bill_number)s,
         %(title)s, %(summary)s, %(status)s,
         %(topic_tags)s::JSON,
         %(session)s,
         %(introduced_date)s::DATE,
         %(last_action_date)s::DATE,
         %(url)s)
    ON CONFLICT (state, bill_id, session)
    DO UPDATE SET
        state_name = EXCLUDED.state_name,
        bill_number = EXCLUDED.bill_number,
        title = EXCLUDED.title,
        summary = EXCLUDED.summary,
        status = EXCLUDED.status,
        topic_tags = EXCLUDED.topic_tags,
        url = EXCLUDED.url,
        introduced_date = EXCLUDED.introduced_date,
        last_action_date = EXCLUDED.last_action_date
"""

def _map_status(status_text):
    """Map an OpenStates status string to a simplified status enum."""
    if not status_text:
        return "other"
    lower = status_text.lower()
    for key, value in STATUS_MAP.items():
        if key in lower:
            return value
    return "other"


# Cap pages per query to avoid over-fetching
_MAX_PAGES = 10


def _api_get(client, params):
    """GET with retry on 429 (exponential backoff, up to 3 attempts)."""
    for attempt in range(3):
        if attempt > 0:
            wait = 10 * (2 ** (attempt - 1))  # 10s, 20s on retries
            print(f"    429 rate-limited, waiting {wait}s...")
            time.sleep(wait)
        resp = client.get(OPENSTATES_URL, params=params, timeout=60)
        if resp.status_code != 429:
            time.sleep(2)  # rate-limit courtesy delay after success
            return resp
    return resp


def _match_topics(title, subjects):
    """Return list of matching D4BL focus topics based on bill title and subjects."""
    text = (title + " " + " ".join(subjects)).lower()
    matched = []
    for topic, keywords in FOCUS_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            matched.append(topic)
    return matched


def _fetch_bills_for_state(client, api_key, jurisdiction, session_id):
    """Fetch recent bills for a jurisdiction (no subject filter)."""
    bills = []
    page = 1

    while page <= _MAX_PAGES:
        params = {
            "jurisdiction": jurisdiction,
            "per_page": 20,
            "page": page,
            "sort": "updated_desc",
            "apikey": api_key,
        }
        if session_id:
            params["session"] = session_id

        resp = _api_get(client, params)
        resp.raise_for_status()
        data = resp.json()

        results = data.get("results", [])
        bills.extend(results)

        pagination = data.get("pagination", {})
        if page >= pagination.get("max_page", 1):
            break
        page += 1

    return bills


def main():
    api_key = os.environ.get("OPENSTATES_API_KEY")
    if not api_key:
        raise RuntimeError("OPENSTATES_API_KEY environment variable is required")

    state_filter = os.environ.get("OPENSTATES_STATE")
    session_id = os.environ.get("OPENSTATES_SESSION")

    conn = get_db_connection()
    conn.autocommit = False
    cur = conn.cursor()

    states = (
        [state_filter.lower()]
        if state_filter
        else list(STATE_MAP.keys())
    )

    records_ingested = 0
    states_covered = []
    topics_covered = set()

    print(
        f"Fetching OpenStates bills for "
        f"states={len(states)}, topics={len(FOCUS_KEYWORDS)}"
    )

    try:
        with httpx.Client(timeout=60) as client:
            for state_slug in states:
                abbrev, full_name = STATE_MAP.get(
                    state_slug, (state_slug.upper(), state_slug)
                )

                try:
                    all_bills = _fetch_bills_for_state(
                        client, api_key, full_name, session_id,
                    )
                except Exception as exc:
                    print(f"  {state_slug} failed: {exc}")
                    continue

                # Filter to D4BL-relevant bills and tag topics locally
                batch = []
                state_count = 0
                for bill in all_bills:
                    bill_id = bill.get("id", "")
                    title = bill.get("title", "")
                    subjects = bill.get("subject", [])

                    matched = _match_topics(title, subjects)
                    if not matched:
                        continue

                    topics_covered.update(matched)

                    url = bill.get("openstates_url")
                    sess = bill.get("session", session_id or "")
                    status_text = bill.get(
                        "latest_action_description", ""
                    )
                    intro_date = bill.get("first_action_date") or None
                    last_date = bill.get("latest_action_date") or None

                    # Merge OpenStates subjects with matched D4BL topics
                    all_tags = list(set(subjects + matched))

                    batch.append({
                        "id": make_record_id(
                            "openstates", abbrev, bill_id, sess,
                        ),
                        "state": abbrev,
                        "state_name": full_name,
                        "bill_id": bill_id,
                        "bill_number": bill.get("identifier", ""),
                        "title": title,
                        "summary": title,
                        "status": _map_status(status_text),
                        "topic_tags": json.dumps(all_tags),
                        "session": sess,
                        "introduced_date": intro_date,
                        "last_action_date": last_date,
                        "url": url,
                    })
                    state_count += 1

                    if len(batch) >= 500:
                        execute_batch(cur, UPSERT_SQL, batch)
                        conn.commit()
                        records_ingested += len(batch)
                        print(f"  Committed batch: {records_ingested} records so far")
                        batch = []

                # Flush remaining batch for this state
                if batch:
                    execute_batch(cur, UPSERT_SQL, batch)
                    conn.commit()
                    records_ingested += len(batch)
                    batch = []

                if state_count > 0:
                    states_covered.append(state_slug)

                print(f"  {state_slug}: {state_count} D4BL-relevant bills (of {len(all_bills)} fetched)")

    finally:
        cur.close()
        conn.close()

    print(
        f"Ingested {records_ingested} bills "
        f"from {len(states_covered)} states"
    )
    return records_ingested


if __name__ == "__main__":
    main()
