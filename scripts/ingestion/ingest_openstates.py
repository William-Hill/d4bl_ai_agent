"""OpenStates policy bills ingestion script.

Fetches state policy bills from the OpenStates GraphQL API v3
for D4BL focus subjects and upserts into the policy_bills table.

Usage:
    DAGSTER_POSTGRES_URL=postgresql://... OPENSTATES_API_KEY=... \
        python scripts/ingestion/ingest_openstates.py

Environment variables:
    DAGSTER_POSTGRES_URL   - PostgreSQL connection URL (required)
    OPENSTATES_API_KEY     - OpenStates API key (required)
    OPENSTATES_STATE       - Filter to a single state slug (optional)
    OPENSTATES_SESSION     - Filter to a specific legislative session (optional)
"""

import json
import os

import httpx

from .helpers import (
    get_db_connection, execute_batch, make_record_id,
)

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

BILLS_QUERY = """
query BillsByState(
    $state: String!,
    $session: String,
    $subject: String,
    $after: String
) {
  bills(
    jurisdiction: $state,
    session: $session,
    subject: $subject,
    after: $after,
    first: 50
  ) {
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


def _fetch_bills_for_subject(client, api_key, state, session_id, subject):
    """Fetch all pages of bills for a given state and subject."""
    bills = []
    after = None
    headers = {"X-API-Key": api_key}

    while True:
        variables = {
            "state": state,
            "subject": subject,
        }
        if session_id:
            variables["session"] = session_id
        if after:
            variables["after"] = after

        resp = client.post(
            OPENSTATES_URL,
            json={"query": BILLS_QUERY, "variables": variables},
            headers=headers,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        edges = (
            data.get("data", {})
            .get("bills", {})
            .get("edges", [])
        )
        page_info = (
            data.get("data", {})
            .get("bills", {})
            .get("pageInfo", {})
        )

        for edge in edges:
            bills.append(edge["node"])

        if not page_info.get("hasNextPage"):
            break
        after = page_info["endCursor"]

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
        f"states={len(states)}, subjects={len(FOCUS_SUBJECTS)}"
    )

    try:
        with httpx.Client(timeout=30) as client:
            for state_slug in states:
                abbrev, full_name = STATE_MAP.get(
                    state_slug, (state_slug.upper(), state_slug)
                )
                seen_ids = set()
                state_count = 0
                batch = []

                for subject in FOCUS_SUBJECTS:
                    try:
                        bills = _fetch_bills_for_subject(
                            client, api_key, state_slug, session_id, subject
                        )
                    except Exception as exc:
                        print(f"  {state_slug}/{subject} failed: {exc}")
                        continue

                    if bills:
                        topics_covered.add(subject)

                    for bill in bills:
                        bill_id = bill["id"]
                        if bill_id in seen_ids:
                            continue
                        seen_ids.add(bill_id)

                        url = (
                            bill.get("sources", [{}])[0].get("url")
                            if bill.get("sources")
                            else None
                        )
                        sess = (
                            bill.get("session", {})
                            .get("identifier", session_id or "")
                        )
                        batch.append({
                            "id": make_record_id(
                                "openstates", abbrev, bill_id, sess,
                            ),
                            "state": abbrev,
                            "state_name": full_name,
                            "bill_id": bill_id,
                            "bill_number": bill.get("identifier", ""),
                            "title": bill.get("title", ""),
                            "summary": bill.get("abstract"),
                            "status": _map_status(bill.get("statusText")),
                            "topic_tags": json.dumps(
                                bill.get("subject", [])
                            ),
                            "session": sess,
                            "introduced_date": bill.get("createdAt"),
                            "last_action_date": bill.get("updatedAt"),
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

                print(f"  {state_slug}: {state_count} bills")

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
