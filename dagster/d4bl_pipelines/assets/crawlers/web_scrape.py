"""Web scrape asset factory.

Dynamically creates Dagster assets from data_sources rows with
source_type='web_scrape'.  Each generated asset crawls configured URLs
using the existing Firecrawl or Crawl4AI infrastructure and stores
the scraped content in the scraped_content_vectors table.
"""

import hashlib
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any

import aiohttp
from dagster import (
    AssetExecutionContext,
    AssetsDefinition,
    MaterializeResult,
    MetadataValue,
    asset,
)

from d4bl_pipelines.utils import slugify

# Backward-compatible alias for tests
_slugify = slugify


async def _scrape_url(
    session: aiohttp.ClientSession,
    url: str,
    provider: str,
    provider_url: str,
    api_key: str | None = None,
) -> dict[str, Any]:
    """Make an HTTP call to the crawl provider and return the response.

    Args:
        session: Active aiohttp client session.
        url: The URL to scrape.
        provider: Either 'firecrawl' or 'crawl4ai'.
        provider_url: Base URL of the crawl provider service.
        api_key: API key for Firecrawl (ignored for Crawl4AI).

    Returns:
        Dict with at least 'content' (str) and 'metadata' (dict).
    """
    timeout = aiohttp.ClientTimeout(total=120)

    if provider == "firecrawl":
        endpoint = f"{provider_url.rstrip('/')}/v0/scrape"
        headers: dict[str, str] = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        headers["Content-Type"] = "application/json"

        async with session.post(
            endpoint,
            json={"url": url},
            headers=headers,
            timeout=timeout,
        ) as resp:
            resp.raise_for_status()
            data = await resp.json()
        return {
            "content": data.get("data", {}).get("content", ""),
            "metadata": data.get("data", {}).get("metadata", {}),
        }

    elif provider == "crawl4ai":
        endpoint = f"{provider_url.rstrip('/')}/crawl"
        async with session.post(
            endpoint,
            json={"urls": [url]},
            headers={"Content-Type": "application/json"},
            timeout=timeout,
        ) as resp:
            resp.raise_for_status()
            data = await resp.json()
        # Crawl4AI returns a list of results
        results = data if isinstance(data, list) else data.get("results", [])
        if results:
            first = results[0]
            return {
                "content": first.get("content", first.get("html", "")),
                "metadata": first.get("metadata", {}),
            }
        return {"content": "", "metadata": {}}

    else:
        raise ValueError(f"Unknown crawl provider: {provider}")


def _make_asset_fn(source_config: dict[str, Any]):
    """Create the async asset function for a single web scrape source."""
    config = source_config["config"]
    urls: list[str] = config.get("urls", [])
    crawl_provider = config.get(
        "crawl_provider", os.environ.get("CRAWL_PROVIDER", "firecrawl")
    )

    async def _asset_fn(
        context: AssetExecutionContext,
    ) -> MaterializeResult:
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import (
            AsyncSession,
            create_async_engine,
        )
        from sqlalchemy.orm import sessionmaker

        # Resolve provider settings at runtime
        provider = config.get(
            "crawl_provider",
            os.environ.get("CRAWL_PROVIDER", "firecrawl"),
        )
        if provider == "firecrawl":
            provider_url = os.environ.get(
                "FIRECRAWL_BASE_URL", "http://firecrawl-api:3002"
            )
            api_key = os.environ.get("FIRECRAWL_API_KEY", "")
        else:
            provider_url = os.environ.get(
                "CRAWL4AI_BASE_URL", "http://crawl4ai:11235"
            )
            api_key = None

        selectors = config.get("selectors")
        depth = config.get("depth", 1)

        db_url = context.resources.db_url
        engine = create_async_engine(
            db_url, pool_size=3, max_overflow=5
        )
        async_session = sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )

        insert_sql = text("""
            INSERT INTO scraped_content_vectors
                (id, url, content, content_type, metadata, created_at)
            VALUES
                (CAST(:id AS UUID), :url, :content,
                 :content_type, CAST(:metadata AS JSONB),
                 :created_at)
            ON CONFLICT (url)
            DO UPDATE SET
                content = EXCLUDED.content,
                content_type = EXCLUDED.content_type,
                metadata = CAST(:metadata AS JSONB),
                created_at = EXCLUDED.created_at
        """)

        pages_scraped = 0
        scraped_urls: list[str] = []
        all_content = []
        now = datetime.now(timezone.utc)

        context.log.info(
            f"Scraping {len(urls)} URL(s) using {provider} "
            f"for source '{source_config['name']}'"
        )

        try:
            async with aiohttp.ClientSession() as http_session:
                for url in urls:
                    context.log.info(f"Scraping: {url}")
                    try:
                        result = await _scrape_url(
                            http_session,
                            url,
                            provider,
                            provider_url,
                            api_key,
                        )
                        content = result.get("content", "")
                        meta = result.get("metadata", {})

                        if selectors:
                            meta["selectors"] = selectors
                        meta["depth"] = depth
                        meta["source_name"] = source_config["name"]
                        meta["provider"] = provider

                        record_id = uuid.uuid5(
                            uuid.NAMESPACE_URL,
                            f"web_scrape:{url}",
                        )

                        async with async_session() as session:
                            await session.execute(
                                insert_sql,
                                {
                                    "id": str(record_id),
                                    "url": url,
                                    "content": content,
                                    "content_type": "text/html",
                                    "metadata": json.dumps(
                                        meta, default=str
                                    ),
                                    "created_at": now,
                                },
                            )
                            await session.commit()

                        pages_scraped += 1
                        scraped_urls.append(url)
                        all_content.append(content)
                        context.log.info(
                            f"Scraped {url}: "
                            f"{len(content)} chars"
                        )

                    except Exception as exc:
                        context.log.warning(
                            f"Failed to scrape {url}: {exc}"
                        )
            # --- Lineage recording ---
            if scraped_urls:
                try:
                    from d4bl_pipelines.quality.lineage import (
                        build_lineage_record,
                        write_lineage_batch,
                    )

                    ingestion_run_id = uuid.uuid4()
                    lineage_records = []
                    for s_url in scraped_urls:
                        rid = uuid.uuid5(
                            uuid.NAMESPACE_URL,
                            f"web_scrape:{s_url}",
                        )
                        lineage_records.append(
                            build_lineage_record(
                                ingestion_run_id=ingestion_run_id,
                                target_table=(
                                    "scraped_content_vectors"
                                ),
                                record_id=rid,
                                source_url=s_url,
                                transformation={
                                    "steps": [
                                        "crawl",
                                        "extract_content",
                                        "upsert",
                                    ]
                                },
                            )
                        )
                    if lineage_records:
                        async with async_session() as session:
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

        combined = "\n".join(all_content)
        content_hash = hashlib.sha256(
            combined.encode()
        ).hexdigest()[:32]

        quality_score = (
            min(1.0, pages_scraped / max(len(urls), 1))
            if urls
            else 0.0
        )

        context.log.info(
            f"Scraped {pages_scraped}/{len(urls)} pages "
            f"for '{source_config['name']}'"
        )

        return MaterializeResult(
            metadata={
                "pages_scraped": pages_scraped,
                "urls": MetadataValue.json(scraped_urls),
                "content_hash": content_hash,
                "quality_score": quality_score,
                "source_name": source_config["name"],
                "provider": provider,
            }
        )

    return _asset_fn


def build_web_scrape_assets(
    data_sources: list[dict[str, Any]],
) -> list[AssetsDefinition]:
    """Build Dagster assets from data sources with source_type='web_scrape'.

    Each entry in data_sources should have:
        - id: str or UUID -- unique identifier
        - name: str -- human-readable name (slugified for asset name)
        - source_type: str -- must be 'web_scrape' to be included
        - config: dict with keys:
            - urls: list[str] -- URLs to scrape
            - depth: int -- crawl depth (default 1)
            - selectors: list[str] -- optional CSS selectors
            - crawl_provider: str -- optional override
              (defaults to CRAWL_PROVIDER env var)

    Returns a list of AssetsDefinition suitable for Dagster.
    """
    assets: list[AssetsDefinition] = []

    for source in data_sources:
        if source.get("source_type") != "web_scrape":
            continue

        slug = slugify(source["name"])
        description = (
            f"Web scrape ingestion: {source['name']} "
            f"({len(source['config'].get('urls', []))} URLs)"
        )

        fn = _make_asset_fn(source)
        fn.__name__ = slug
        fn.__qualname__ = slug

        decorated = asset(
            name=slug,
            group_name="crawlers",
            description=description,
        )(fn)

        assets.append(decorated)

    return assets
