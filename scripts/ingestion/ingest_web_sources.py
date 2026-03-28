"""Ingest content from configured web sources.

Reads target URLs from data_sources table (source_type='web_scrape'),
extracts content using the tiered content extractor, and upserts to
ingested_records.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone

_SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from ingestion.helpers import get_db_connection, upsert_batch, make_record_id
from ingestion.lib.content_extractor import extract

logger = logging.getLogger(__name__)

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


def main() -> int:
    """Scrape all configured web sources. Returns records ingested."""
    conn = get_db_connection()
    conn.autocommit = False
    cur = conn.cursor()

    cur.execute(
        "SELECT id, name, config FROM data_sources WHERE source_type = 'web_scrape' AND enabled = true"
    )
    sources = cur.fetchall()

    if not sources:
        print("No web scrape sources configured in data_sources table.")
        return 0

    records_ingested = 0
    now = datetime.now(timezone.utc).isoformat()

    for source_id, source_name, config in sources:
        urls = config.get("urls", []) if config else []
        force_js = config.get("force_js", False) if config else False

        if not urls:
            print(f"  Skipping {source_name}: no URLs in config")
            continue

        print(f"  Scraping {source_name}: {len(urls)} URLs")
        batch = []

        for url in urls:
            print(f"    Extracting: {url}")
            result = extract(url, force_js=force_js)

            if not result:
                print(f"    No content extracted from {url}")
                continue

            record_id = make_record_id("web_scrape", source_name, url)
            batch.append({
                "id": str(record_id),
                "source_type": "web_scrape",
                "source_key": source_name,
                "external_id": url,
                "title": result.title[:500] if result.title else None,
                "url": url,
                "content": result.text,
                "published_at": result.date,
                "metadata": json.dumps({
                    "author": result.author,
                    "extraction_method": result.source_type,
                }),
                "ingested_at": now,
            })

        if batch:
            count = upsert_batch(conn, UPSERT_SQL, batch)
            records_ingested += count
            print(f"  Upserted {count} records from {source_name}")

    cur.close()
    conn.close()
    print(f"Web scrape complete: {records_ingested} total records")
    return records_ingested


if __name__ == "__main__":
    sys.exit(0 if main() >= 0 else 1)
