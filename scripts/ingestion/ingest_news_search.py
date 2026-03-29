"""Ingest news articles discovered via SearXNG search.

Reads search queries from keyword_monitors table, queries SearXNG
with news category, extracts article content, and upserts to
ingested_records.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone

import httpx

_SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from ingestion.helpers import get_db_connection, make_record_id, upsert_batch

logger = logging.getLogger(__name__)

SEARXNG_BASE_URL = os.environ.get("SEARXNG_BASE_URL", "http://searxng:8080")

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


def search_news(query: str, base_url: str = SEARXNG_BASE_URL) -> list[dict]:
    """Query SearXNG for news results.

    Returns list of {"title", "url", "content"} dicts.
    """
    try:
        with httpx.Client(timeout=30) as client:
            response = client.get(
                f"{base_url}/search",
                params={
                    "q": query,
                    "format": "json",
                    "categories": "news",
                },
            )
            if response.status_code != 200:
                logger.warning("SearXNG returned %d for query: %s", response.status_code, query)
                return []

            data = response.json()
            return [
                {
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "content": r.get("content", ""),
                }
                for r in data.get("results", [])
                if r.get("url")
            ]
    except Exception:
        logger.exception("SearXNG search failed for: %s", query)
        return []


def deduplicate_urls(results: list[dict]) -> list[dict]:
    """Remove entries with duplicate URLs, keeping first occurrence."""
    seen: set[str] = set()
    deduped = []
    for r in results:
        url = r.get("url", "")
        if url and url not in seen:
            seen.add(url)
            deduped.append(r)
    return deduped


def main() -> int:
    """Search for news on monitored keywords and ingest results."""
    conn = get_db_connection()
    conn.autocommit = False
    cur = conn.cursor()

    # Read active keyword monitors
    cur.execute(
        "SELECT id, keyword, config FROM keyword_monitors WHERE enabled = true"
    )
    monitors = cur.fetchall()

    if not monitors:
        print("No active keyword monitors configured.")
        return 0

    records_ingested = 0
    now = datetime.now(timezone.utc).isoformat()

    for monitor_id, keyword, config in monitors:
        print(f"  Searching news for: {keyword}")
        results = search_news(keyword)
        results = deduplicate_urls(results)
        print(f"  Found {len(results)} unique results")

        batch = []
        for result in results:
            record_id = make_record_id("news_search", keyword, result["url"])
            batch.append({
                "id": str(record_id),
                "source_type": "news_search",
                "source_key": keyword,
                "external_id": result["url"],
                "title": result["title"][:500] if result["title"] else None,
                "url": result["url"],
                "content": result["content"],
                "published_at": None,
                "metadata": json.dumps({"keyword_monitor_id": str(monitor_id)}),
                "ingested_at": now,
            })

        if batch:
            count = upsert_batch(conn, UPSERT_SQL, batch)
            records_ingested += count
            print(f"  Upserted {count} records for keyword: {keyword}")

    cur.close()
    conn.close()
    print(f"News search complete: {records_ingested} total records")
    return records_ingested


if __name__ == "__main__":
    sys.exit(0 if main() >= 0 else 1)