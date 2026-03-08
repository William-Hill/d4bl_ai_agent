"""OpenStates policy bills ingestion asset.

Migrated from scripts/ingest_openstates.py.
Fetches state policy bills from the OpenStates GraphQL API
for D4BL focus subjects and upserts into policy_bills table.
"""

import hashlib
import json
import logging
import os
import uuid
from typing import Optional

import aiohttp
from dagster import (
    AssetExecutionContext,
    MaterializeResult,
    MetadataValue,
    asset,
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


def _map_status(status_text: Optional[str]) -> str:
    """Map an OpenStates status string to a simplified status enum."""
    if not status_text:
        return "other"
    lower = status_text.lower()
    for key, value in STATUS_MAP.items():
        if key in lower:
            return value
    return "other"


async def _fetch_bills_for_subject(
    http: aiohttp.ClientSession,
    api_key: str,
    state: str,
    session_id: Optional[str],
    subject: str,
) -> list[dict]:
    """Fetch all pages of bills for a given state and subject."""
    bills: list[dict] = []
    after: Optional[str] = None
    headers = {"X-API-Key": api_key}

    while True:
        variables: dict[str, object] = {
            "state": state,
            "subject": subject,
        }
        if session_id:
            variables["session"] = session_id
        if after:
            variables["after"] = after

        timeout = aiohttp.ClientTimeout(total=30)
        async with http.post(
            OPENSTATES_URL,
            json={"query": BILLS_QUERY, "variables": variables},
            headers=headers,
            timeout=timeout,
        ) as resp:
            resp.raise_for_status()
            data = await resp.json()

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


@asset(
    group_name="apis",
    description=(
        "State policy bills from OpenStates: legislation on housing, "
        "wealth, education, criminal justice, voting rights, "
        "economic development, and health care."
    ),
    metadata={
        "source": "OpenStates GraphQL API v3",
        "methodology": "D4BL equity-focused policy tracking",
    },
)
async def openstates_bills(
    context: AssetExecutionContext,
) -> MaterializeResult:
    """Fetch OpenStates policy bills and upsert into policy_bills table."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import (
        AsyncSession,
        create_async_engine,
    )
    from sqlalchemy.orm import sessionmaker

    api_key = os.environ.get("OPENSTATES_API_KEY")
    if not api_key:
        context.log.error(
            "OPENSTATES_API_KEY environment variable is required"
        )
        return MaterializeResult(
            metadata={
                "records_ingested": 0,
                "status": "missing_api_key",
            }
        )

    state_filter = os.environ.get("OPENSTATES_STATE")
    session_id = os.environ.get("OPENSTATES_SESSION")
    db_url = context.resources.db_url

    engine = create_async_engine(
        db_url, pool_size=3, max_overflow=5
    )
    async_session = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    states = (
        [state_filter.lower()]
        if state_filter
        else list(STATE_MAP.keys())
    )

    records_ingested = 0
    states_covered: list[str] = []
    topics_covered: set[str] = set()
    all_bill_ids: list[str] = []

    context.log.info(
        f"Fetching OpenStates bills for "
        f"states={len(states)}, subjects={len(FOCUS_SUBJECTS)}"
    )

    try:
        async with aiohttp.ClientSession() as http:
            async with async_session() as session:
                for state_slug in states:
                    abbrev, full_name = STATE_MAP.get(
                        state_slug, (state_slug.upper(), state_slug)
                    )
                    seen_ids: set[str] = set()
                    state_count = 0

                    for subject in FOCUS_SUBJECTS:
                        try:
                            bills = await _fetch_bills_for_subject(
                                http,
                                api_key,
                                state_slug,
                                session_id,
                                subject,
                            )
                        except Exception as exc:
                            context.log.warning(
                                f"{state_slug}/{subject} failed: "
                                f"{exc}"
                            )
                            continue

                        if bills:
                            topics_covered.add(subject)

                        for bill in bills:
                            bill_id = bill["id"]
                            if bill_id in seen_ids:
                                continue
                            seen_ids.add(bill_id)

                            url = (
                                bill.get("sources", [{}])[0]
                                .get("url")
                                if bill.get("sources")
                                else None
                            )
                            sess = (
                                bill.get("session", {})
                                .get("identifier", session_id or "")
                            )
                            record_id = uuid.uuid5(
                                uuid.NAMESPACE_URL,
                                f"openstates:{abbrev}:{bill_id}:"
                                f"{sess}",
                            )

                            upsert_sql = text("""
                                INSERT INTO policy_bills
                                    (id, state, state_name,
                                     bill_id, bill_number,
                                     title, summary, status,
                                     topic_tags, session,
                                     introduced_date,
                                     last_action_date, url)
                                VALUES
                                    (CAST(:id AS UUID),
                                     :state, :state_name,
                                     :bill_id, :bill_number,
                                     :title, :summary, :status,
                                     CAST(:topic_tags AS JSON),
                                     :session,
                                     CAST(:introduced_date AS DATE),
                                     CAST(:last_action_date AS DATE),
                                     :url)
                                ON CONFLICT (state, bill_id, session)
                                DO UPDATE SET
                                    state_name = :state_name,
                                    bill_number = :bill_number,
                                    title = :title,
                                    summary = :summary,
                                    status = :status,
                                    topic_tags =
                                        CAST(:topic_tags AS JSON),
                                    url = :url,
                                    introduced_date =
                                        CAST(:introduced_date AS DATE),
                                    last_action_date =
                                        CAST(:last_action_date AS DATE)
                            """)
                            await session.execute(
                                upsert_sql,
                                {
                                    "id": str(record_id),
                                    "state": abbrev,
                                    "state_name": full_name,
                                    "bill_id": bill_id,
                                    "bill_number": bill.get(
                                        "identifier", ""
                                    ),
                                    "title": bill.get("title", ""),
                                    "summary": bill.get("abstract"),
                                    "status": _map_status(
                                        bill.get("statusText")
                                    ),
                                    "topic_tags": json.dumps(
                                        bill.get("subject", [])
                                    ),
                                    "session": sess,
                                    "introduced_date": bill.get(
                                        "createdAt"
                                    ),
                                    "last_action_date": bill.get(
                                        "updatedAt"
                                    ),
                                    "url": url,
                                },
                            )
                            state_count += 1
                            all_bill_ids.append(bill_id)

                    if state_count > 0:
                        states_covered.append(state_slug)
                    records_ingested += state_count

                    context.log.info(
                        f"  {state_slug}: {state_count} bills"
                    )

                await session.commit()

                # --- Lineage recording ---
                try:
                    from d4bl_pipelines.quality.lineage import (
                        build_lineage_record,
                        write_lineage_batch,
                    )

                    ingestion_run_id = uuid.uuid4()
                    lineage_records = []
                    for bill_id_val in all_bill_ids:
                        rec_id = uuid.uuid5(
                            uuid.NAMESPACE_URL,
                            f"openstates:lineage:{bill_id_val}",
                        )
                        lineage_records.append(
                            build_lineage_record(
                                ingestion_run_id=ingestion_run_id,
                                target_table="policy_bills",
                                record_id=rec_id,
                                source_url=OPENSTATES_URL,
                                source_hash=hashlib.sha256(
                                    f"{sorted(states_covered)}:"
                                    f"{records_ingested}:"
                                    f"{sorted(all_bill_ids)}"
                                    .encode()
                                ).hexdigest()[:32],
                                transformation={
                                    "steps": [
                                        "fetch_graphql",
                                        "map_status",
                                        "upsert",
                                    ]
                                },
                            )
                        )
                    if lineage_records:
                        await write_lineage_batch(
                            session, lineage_records
                        )
                    context.log.info(
                        f"Wrote {len(lineage_records)} "
                        f"lineage records"
                    )
                except Exception as lineage_exc:
                    logging.getLogger(__name__).warning(
                        "Lineage recording failed: %s",
                        lineage_exc,
                    )
    finally:
        await engine.dispose()

    # Compute coverage metadata
    all_states = set(STATE_MAP.keys())
    covered_states = set(states_covered)
    missing_states = all_states - covered_states
    all_topics = set(FOCUS_SUBJECTS)
    missing_topics = all_topics - topics_covered

    content_hash = hashlib.sha256(
        f"{sorted(states_covered)}:{records_ingested}:"
        f"{sorted(all_bill_ids)}"
        .encode()
    ).hexdigest()[:32]

    context.log.info(
        f"Ingested {records_ingested} bills "
        f"from {len(covered_states)} states"
    )

    # Compute bias flags from coverage data
    bias_flags = []
    if missing_states:
        bias_flags.append(
            f"missing_states: {len(missing_states)} of "
            f"{len(all_states)} states not covered"
        )
    if missing_topics:
        bias_flags.append(
            f"missing_topics: {sorted(missing_topics)}"
        )
    bias_flags.append(
        "single_source: all data from OpenStates API only"
    )

    # Quality score: weighted average of state and topic coverage
    state_coverage = len(covered_states) / len(all_states)
    topic_coverage = len(topics_covered) / len(all_topics)
    quality_score = min(
        5.0, (state_coverage * 0.6 + topic_coverage * 0.4) * 5
    )

    return MaterializeResult(
        metadata={
            "records_ingested": records_ingested,
            "states_covered": len(covered_states),
            "states_missing": sorted(
                [s.upper() for s in missing_states]
            ),
            "topics_covered": sorted(topics_covered),
            "topics_missing": sorted(missing_topics),
            "content_hash": content_hash,
            "quality_score": MetadataValue.float(quality_score),
            "source_url": OPENSTATES_URL,
            "bias_flags": MetadataValue.json_serializable(
                bias_flags
            ),
            "coverage_metadata": MetadataValue.json_serializable({
                "state_coverage_pct": round(
                    state_coverage * 100, 1
                ),
                "topic_coverage_pct": round(
                    topic_coverage * 100, 1
                ),
                "total_states_queried": len(states),
                "total_topics": len(FOCUS_SUBJECTS),
            }),
        }
    )
