"""RSS/Atom feed asset factory.

Dynamically creates Dagster assets from data_sources rows with
source_type='rss_feed'.  Each generated asset fetches and parses
an RSS or Atom feed, then upserts new entries into the
ingested_records table.
"""

import json
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any

import aiohttp

from d4bl_pipelines.utils import (
    INGESTED_RECORDS_UPSERT_SQL,
    compute_content_hash,
    db_session,
    slugify,
)
from dagster import (
    AssetExecutionContext,
    AssetsDefinition,
    MaterializeResult,
    asset,
)

# Backward-compatible alias for tests
_slugify = slugify

ATOM_NS = "{http://www.w3.org/2005/Atom}"


def _parse_rss(root: ET.Element) -> list[dict[str, Any]]:
    """Parse RSS 2.0 XML into a list of entry dicts."""
    entries: list[dict[str, Any]] = []
    for item in root.iter("item"):
        entry: dict[str, Any] = {}
        title_el = item.find("title")
        entry["title"] = (
            title_el.text.strip() if title_el is not None
            and title_el.text else ""
        )
        link_el = item.find("link")
        entry["link"] = (
            link_el.text.strip() if link_el is not None
            and link_el.text else ""
        )
        desc_el = item.find("description")
        entry["description"] = (
            desc_el.text.strip() if desc_el is not None
            and desc_el.text else ""
        )
        pub_el = item.find("pubDate")
        entry["published"] = (
            pub_el.text.strip() if pub_el is not None
            and pub_el.text else ""
        )
        guid_el = item.find("guid")
        entry["guid"] = (
            guid_el.text.strip() if guid_el is not None
            and guid_el.text else ""
        )
        entries.append(entry)
    return entries


def _parse_atom(root: ET.Element) -> list[dict[str, Any]]:
    """Parse Atom XML into a list of entry dicts."""
    entries: list[dict[str, Any]] = []
    for item in root.iter(f"{ATOM_NS}entry"):
        entry: dict[str, Any] = {}
        title_el = item.find(f"{ATOM_NS}title")
        entry["title"] = (
            title_el.text.strip() if title_el is not None
            and title_el.text else ""
        )
        # Prefer rel="alternate" link, fall back to first <link>
        link_el = item.find(
            f"{ATOM_NS}link[@rel='alternate']"
        )
        if link_el is None:
            link_el = item.find(f"{ATOM_NS}link")
        entry["link"] = (
            link_el.get("href", "").strip() if link_el is not None
            else ""
        )
        summary_el = item.find(f"{ATOM_NS}summary")
        if summary_el is None:
            summary_el = item.find(f"{ATOM_NS}content")
        entry["description"] = (
            summary_el.text.strip() if summary_el is not None
            and summary_el.text else ""
        )
        pub_el = item.find(f"{ATOM_NS}updated")
        if pub_el is None:
            pub_el = item.find(f"{ATOM_NS}published")
        entry["published"] = (
            pub_el.text.strip() if pub_el is not None
            and pub_el.text else ""
        )
        id_el = item.find(f"{ATOM_NS}id")
        entry["guid"] = (
            id_el.text.strip() if id_el is not None
            and id_el.text else ""
        )
        entries.append(entry)
    return entries


def _parse_feed(xml_text: str) -> list[dict[str, Any]]:
    """Detect feed format (RSS 2.0 or Atom) and parse entries."""
    root = ET.fromstring(xml_text)
    # Atom feeds have a root tag of {namespace}feed
    if root.tag == f"{ATOM_NS}feed":
        return _parse_atom(root)
    # RSS feeds typically have <rss> root or <channel> inside
    return _parse_rss(root)


def _make_asset_fn(source_config: dict[str, Any]):
    """Create the async asset function for a single RSS feed source."""
    source_id = source_config["id"]
    config = source_config["config"]
    feed_url = config["feed_url"]
    max_entries = config.get("max_entries", 100)
    crawl_linked = config.get("crawl_linked", False)

    async def _asset_fn(
        context: AssetExecutionContext,
    ) -> MaterializeResult:
        from sqlalchemy import text

        db_url = context.resources.db_url

        context.log.info(
            f"Fetching RSS feed '{source_config['name']}' "
            f"from {feed_url}"
        )

        timeout = aiohttp.ClientTimeout(total=60)
        async with aiohttp.ClientSession() as http_session:
            async with http_session.get(
                feed_url, timeout=timeout
            ) as resp:
                resp.raise_for_status()
                xml_text = await resp.text()

        all_entries = _parse_feed(xml_text)
        entries = all_entries[:max_entries]
        entries_found = len(entries)

        content_hash = compute_content_hash(entries)

        # Compute a simple quality score based on field completeness
        if entries:
            filled = sum(
                sum(
                    1 for k in ("title", "link", "description",
                                "published", "guid")
                    if e.get(k)
                )
                for e in entries
            )
            quality_score = round(filled / (len(entries) * 5), 2)
        else:
            quality_score = 0.0

        # Look up existing keys to avoid duplicates
        guids = [
            e.get("guid") or e.get("link") or f"_idx_{i}_{e.get('title', '')}"
            for i, e in enumerate(entries)
        ]
        async with db_session(db_url) as session:
            if guids:
                existing_result = await session.execute(
                    text("""
                        SELECT record_key
                        FROM ingested_records
                        WHERE source_id = CAST(:source_id AS UUID)
                          AND record_key = ANY(CAST(:keys AS TEXT[]))
                    """),
                    {
                        "source_id": str(source_id),
                        "keys": guids,
                    },
                )
                existing_keys = {
                    row[0] for row in existing_result.fetchall()
                }
            else:
                existing_keys = set()

            # Build stable dedupe keys per entry — fall back to
            # title+index when guid and link are both absent.
            def _entry_key(entry: dict, idx: int) -> str:
                key = entry.get("guid") or entry.get("link") or ""
                if not key:
                    key = f"_idx_{idx}_{entry.get('title', '')}"
                return key

            keyed_entries = [
                (e, _entry_key(e, i)) for i, e in enumerate(entries)
            ]
            new_entries = [
                (e, key) for e, key in keyed_entries
                if key not in existing_keys
            ]

            upsert_sql = text(INGESTED_RECORDS_UPSERT_SQL)

            now = datetime.now(timezone.utc)
            for entry, record_key in new_entries:
                record_id = uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    f"rss_feed:{source_id}:{record_key}",
                )

                data_payload = dict(entry)
                data_payload["crawl_linked"] = crawl_linked
                data_payload["source_feed_url"] = feed_url

                await session.execute(
                    upsert_sql,
                    {
                        "id": str(record_id),
                        "source_id": str(source_id),
                        "record_key": record_key,
                        "data": json.dumps(
                            data_payload, default=str
                        ),
                        "content_hash": content_hash,
                        "ingested_at": now,
                    },
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
                for entry, rk in new_entries:
                    rid = uuid.uuid5(
                        uuid.NAMESPACE_URL,
                        f"rss_feed:{source_id}:{rk}",
                    )
                    lineage_records.append(
                        build_lineage_record(
                            ingestion_run_id=ingestion_run_id,
                            target_table="ingested_records",
                            record_id=rid,
                            source_url=feed_url,
                            source_hash=content_hash,
                            transformation={
                                "steps": [
                                    "fetch_feed",
                                    "parse_xml",
                                    "upsert",
                                ]
                            },
                            quality_score=quality_score,
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
                context.log.warning(
                    f"Lineage recording failed: {lineage_exc}"
                )

        context.log.info(
            f"Feed '{source_config['name']}': "
            f"{entries_found} entries found, "
            f"{len(new_entries)} new"
        )

        return MaterializeResult(
            metadata={
                "entries_found": entries_found,
                "new_entries": len(new_entries),
                "feed_url": feed_url,
                "content_hash": content_hash,
                "quality_score": quality_score,
                "source_id": str(source_id),
                "source_name": source_config["name"],
            }
        )

    return _asset_fn


def build_rss_assets(
    data_sources: list[dict[str, Any]],
) -> list[AssetsDefinition]:
    """Build Dagster assets from a list of RSS feed data source configs.

    Each entry in data_sources should have:
        - id: str or UUID -- unique identifier
        - name: str -- human-readable name (slugified for asset name)
        - source_type: str -- must be 'rss_feed' to be included
        - config: dict with keys:
            - feed_url: str -- URL of the RSS/Atom feed
            - max_entries: int -- max entries to process (default 100)
            - crawl_linked: bool -- whether to crawl linked article
              URLs (default false)

    Returns a list of AssetsDefinition suitable for Dagster.
    """
    assets: list[AssetsDefinition] = []

    for source in data_sources:
        if source.get("source_type") != "rss_feed":
            continue

        slug = slugify(source["name"])
        description = (
            f"RSS feed ingestion: {source['name']} "
            f"({source['config'].get('feed_url', 'unknown url')})"
        )

        fn = _make_asset_fn(source)
        fn.__name__ = slug
        fn.__qualname__ = slug

        decorated = asset(
            name=slug,
            group_name="feeds",
            description=description,
        )(fn)

        assets.append(decorated)

    return assets
