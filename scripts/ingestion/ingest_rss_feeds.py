"""Ingest articles from RSS and Atom feeds.

Reads feed URLs from data_sources table (source_type='rss_feed'),
fetches each feed, parses entries, and upserts to ingested_records.
"""

from __future__ import annotations

import logging
import os
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import httpx

# Ensure scripts/ is on path for helpers import
_SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from ingestion.helpers import get_db_connection, make_record_id, upsert_batch

logger = logging.getLogger(__name__)

ATOM_NS = "http://www.w3.org/2005/Atom"

UPSERT_SQL = """
    INSERT INTO ingested_records
        (id, source_type, source_key, external_id, title, url, content,
         published_at, metadata, ingested_at)
    VALUES
        (CAST(%(id)s AS UUID), %(source_type)s, %(source_key)s, %(external_id)s,
         %(title)s, %(url)s, %(content)s, %(published_at)s,
         CAST(%(metadata)s AS JSONB), %(ingested_at)s)
    ON CONFLICT (source_type, external_id)
    DO UPDATE SET
        title = EXCLUDED.title,
        content = EXCLUDED.content,
        metadata = EXCLUDED.metadata,
        ingested_at = EXCLUDED.ingested_at
"""


def _extract_rss_entries(root: ET.Element) -> list[dict]:
    """Extract entry dicts from a parsed RSS root element."""
    entries = []
    for item in root.iter("item"):
        title = item.findtext("title", "")
        link = item.findtext("link", "")
        guid = item.findtext("guid", link)
        pub_date = item.findtext("pubDate", "")
        description = item.findtext("description", "")

        entries.append({
            "title": title.strip(),
            "url": link.strip(),
            "guid": guid.strip(),
            "date": pub_date.strip(),
            "content": description.strip(),
        })
    return entries


def _extract_atom_entries(root: ET.Element) -> list[dict]:
    """Extract entry dicts from a parsed Atom root element."""
    entries = []
    for entry in root.iter(f"{{{ATOM_NS}}}entry"):
        title_el = entry.find(f"{{{ATOM_NS}}}title")
        title = title_el.text.strip() if title_el is not None and title_el.text else ""

        link_el = entry.find(f"{{{ATOM_NS}}}link")
        url = link_el.get("href", "") if link_el is not None else ""

        id_el = entry.find(f"{{{ATOM_NS}}}id")
        guid = id_el.text.strip() if id_el is not None and id_el.text else url

        summary_el = entry.find(f"{{{ATOM_NS}}}summary")
        content = summary_el.text.strip() if summary_el is not None and summary_el.text else ""

        updated_el = entry.find(f"{{{ATOM_NS}}}updated")
        date = updated_el.text.strip() if updated_el is not None and updated_el.text else ""

        entries.append({
            "title": title,
            "url": url,
            "guid": guid,
            "date": date,
            "content": content,
        })
    return entries


def parse_rss_feed(xml_text: str) -> list[dict]:
    """Parse RSS 2.0 feed XML into a list of entry dicts."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        logger.warning("Failed to parse RSS XML")
        return []
    return _extract_rss_entries(root)


def parse_atom_feed(xml_text: str) -> list[dict]:
    """Parse Atom feed XML into a list of entry dicts."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        logger.warning("Failed to parse Atom XML")
        return []
    return _extract_atom_entries(root)


def parse_feed(xml_text: str) -> list[dict]:
    """Auto-detect feed format and parse entries. Parses XML once."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []

    # Detect format by root tag
    tag = root.tag.lower()
    if "feed" in tag:
        return _extract_atom_entries(root)
    if "rss" in tag or root.find("channel") is not None:
        return _extract_rss_entries(root)

    return []


def main() -> int:
    """Fetch and ingest all configured RSS feeds. Returns records ingested."""
    conn = get_db_connection()
    conn.autocommit = False
    cur = conn.cursor()

    # Get RSS feed sources from data_sources table
    cur.execute(
        "SELECT id, name, config FROM data_sources WHERE source_type = 'rss_feed' AND enabled = true"
    )
    sources = cur.fetchall()

    if not sources:
        print("No RSS feed sources configured in data_sources table.")
        return 0

    records_ingested = 0
    now = datetime.now(timezone.utc).isoformat()

    with httpx.Client(timeout=60, follow_redirects=True) as client:
        for source_id, source_name, config in sources:
            feed_url = config.get("url") if config else None
            if not feed_url:
                print(f"  Skipping {source_name}: no URL in config")
                continue

            print(f"  Fetching feed: {source_name} ({feed_url})")
            try:
                response = client.get(feed_url)
                if response.status_code != 200:
                    print(f"  HTTP {response.status_code} for {feed_url}")
                    continue

                entries = parse_feed(response.text)
                print(f"  Found {len(entries)} entries in {source_name}")

                batch = []
                for entry in entries:
                    if not entry["url"] and not entry["guid"]:
                        continue

                    record_id = make_record_id("rss", source_name, entry["guid"])
                    batch.append({
                        "id": str(record_id),
                        "source_type": "rss",
                        "source_key": source_name,
                        "external_id": entry["guid"],
                        "title": entry["title"][:500] if entry["title"] else None,
                        "url": entry["url"],
                        "content": entry["content"],
                        "published_at": entry["date"] or None,
                        "metadata": "{}",
                        "ingested_at": now,
                    })

                if batch:
                    count = upsert_batch(conn, UPSERT_SQL, batch)
                    records_ingested += count
                    print(f"  Upserted {count} records from {source_name}")

            except Exception as exc:
                print(f"  Error fetching {source_name}: {exc}")
                continue

    cur.close()
    conn.close()
    print(f"RSS ingestion complete: {records_ingested} total records")
    return records_ingested


if __name__ == "__main__":
    sys.exit(0 if main() >= 0 else 1)