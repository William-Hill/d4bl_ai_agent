"""Keyword monitor asset factory.

Dynamically creates Dagster assets from keyword_monitors rows.
Each generated asset searches across configured data sources for
records matching any of the monitor's keywords, using case-insensitive
LIKE queries on the ingested_records table.
"""

from functools import partial
from typing import Any

from d4bl_pipelines.utils import db_session, slugify
from dagster import (
    AssetExecutionContext,
    AssetsDefinition,
    MaterializeResult,
    asset,
)

# Backward-compatible alias for tests (keyword monitors use
# "unnamed_monitor" as fallback)
_slugify = partial(slugify, fallback="unnamed_monitor")


def _build_keyword_query(
    keywords: list[str], source_ids: list[str]
) -> tuple[str, dict[str, Any]]:
    """Build a SQL WHERE clause for keyword matching.

    Returns a tuple of (where_clause, params_dict) that searches the
    ``data`` JSONB column (cast to text) for any keyword match using
    case-insensitive LIKE, scoped to the given source_ids.
    """
    if not keywords or not source_ids:
        return "WHERE FALSE", {}

    keyword_conditions = []
    params: dict[str, Any] = {}

    for idx, kw in enumerate(keywords):
        param_name = f"kw_{idx}"
        keyword_conditions.append(
            f"LOWER(CAST(data AS TEXT)) LIKE :{param_name}"
        )
        params[param_name] = f"%{kw.lower()}%"

    source_conditions = []
    for idx, sid in enumerate(source_ids):
        param_name = f"src_{idx}"
        source_conditions.append(
            f"source_id = CAST(:{param_name} AS UUID)"
        )
        params[param_name] = str(sid)

    keyword_clause = " OR ".join(keyword_conditions)
    source_clause = " OR ".join(source_conditions)

    where = f"({source_clause}) AND ({keyword_clause})"
    return where, params


def _make_asset_fn(monitor_config: dict[str, Any]):
    """Create the async asset function for a single keyword monitor."""
    monitor_id = monitor_config["id"]
    monitor_name = monitor_config["name"]
    keywords = monitor_config["keywords"]
    source_ids = [str(sid) for sid in monitor_config["source_ids"]]

    async def _asset_fn(
        context: AssetExecutionContext,
    ) -> MaterializeResult:
        from sqlalchemy import text

        db_url = context.resources.db_url

        context.log.info(
            f"Running keyword search '{monitor_name}' "
            f"with keywords {keywords} across "
            f"{len(source_ids)} source(s)"
        )

        where_clause, params = _build_keyword_query(
            keywords, source_ids
        )

        query_sql = text(
            f"SELECT id, source_id, record_key, data "
            f"FROM ingested_records "
            f"WHERE {where_clause}"
        )

        total_matches = 0
        keywords_matched: set[str] = set()
        sources_searched = len(source_ids)

        async with db_session(db_url) as session:
            result = await session.execute(query_sql, params)
            rows = result.fetchall()
            total_matches = len(rows)

            # Determine which keywords actually matched
            for row in rows:
                data_text = str(row[3]).lower()
                for kw in keywords:
                    if kw.lower() in data_text:
                        keywords_matched.add(kw)

        # Quality score: ratio of keywords that had matches
        if keywords:
            quality_score = round(
                len(keywords_matched) / len(keywords), 2
            )
        else:
            quality_score = 0.0

        context.log.info(
            f"Keyword search '{monitor_name}': "
            f"{total_matches} matches across "
            f"{sources_searched} source(s), "
            f"{len(keywords_matched)}/{len(keywords)} keywords matched"
        )

        return MaterializeResult(
            metadata={
                "total_matches": total_matches,
                "keywords_matched": list(sorted(keywords_matched)),
                "sources_searched": sources_searched,
                "quality_score": quality_score,
                "monitor_id": str(monitor_id),
                "monitor_name": monitor_name,
            }
        )

    return _asset_fn


def build_keyword_monitor_assets(
    monitors: list[dict[str, Any]],
) -> list[AssetsDefinition]:
    """Build Dagster assets from a list of keyword monitor configs.

    Each entry in monitors should have:
        - id: str or UUID -- unique identifier
        - name: str -- human-readable name (slugified for asset name)
        - keywords: list[str] -- keywords to search for
        - source_ids: list[str|UUID] -- data source IDs to search
        - enabled: bool -- whether the monitor is active

    Only enabled monitors produce assets.

    Returns a list of AssetsDefinition suitable for Dagster.
    """
    assets: list[AssetsDefinition] = []

    for monitor in monitors:
        if not monitor.get("enabled", True):
            continue

        slug = f"keyword_search_{slugify(monitor['name'], fallback='unnamed_monitor')}"
        description = (
            f"Keyword monitor: {monitor['name']} -- "
            f"searches for {monitor['keywords']}"
        )

        fn = _make_asset_fn(monitor)
        fn.__name__ = slug
        fn.__qualname__ = slug

        decorated = asset(
            name=slug,
            group_name="keyword_monitors",
            description=description,
        )(fn)

        assets.append(decorated)

    return assets
