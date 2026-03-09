"""MCP source asset factory.

Dynamically creates Dagster assets from data_sources rows with
source_type='mcp'.  Each generated asset calls a configured MCP
server tool via JSON-RPC 2.0 and upserts results into the
ingested_records table.
"""

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any

import aiohttp

from d4bl_pipelines.utils import (
    INGESTED_RECORDS_UPSERT_SQL,
    compute_content_hash,
    db_session,
    derive_record_key,
    slugify,
)
from dagster import (
    AssetExecutionContext,
    AssetsDefinition,
    MaterializeResult,
    MetadataValue,
    asset,
)

# Backward-compatible aliases for tests
_slugify = slugify
_derive_record_key = derive_record_key


def _build_jsonrpc_request(
    tool_name: str,
    tool_params: dict[str, Any],
) -> dict[str, Any]:
    """Build a JSON-RPC 2.0 request body for an MCP tools/call.

    Returns a dict conforming to the JSON-RPC 2.0 spec with the
    MCP ``tools/call`` method.
    """
    return {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {
            "name": tool_name,
            "arguments": tool_params,
        },
        "id": 1,
    }


def _extract_results(response_data: dict[str, Any]) -> list[Any]:
    """Extract records from a JSON-RPC 2.0 response.

    If the response contains an ``error`` key, raises ValueError.
    If ``result`` is a list, returns it directly.
    If ``result`` is a dict, wraps it in a list.
    Otherwise wraps the value in a single-element list.
    """
    if "error" in response_data:
        err = response_data["error"]
        code = err.get("code", "unknown")
        message = err.get("message", "Unknown error")
        raise ValueError(
            f"JSON-RPC error {code}: {message}"
        )

    result = response_data.get("result")
    if result is None:
        return []
    if isinstance(result, list):
        return result
    if isinstance(result, dict):
        return [result]
    return [{"value": result}]


def _make_asset_fn(source_config: dict[str, Any]):
    """Create the async asset function for a single MCP source."""
    source_id = source_config["id"]
    config = source_config["config"]
    server_url = config["server_url"]
    tool_name = config["tool_name"]
    tool_params = config.get("tool_params") or {}
    auth_env_var = config.get("auth_env_var")

    async def _asset_fn(
        context: AssetExecutionContext,
    ) -> MaterializeResult:
        from sqlalchemy import text

        db_url = context.resources.db_url

        # Build request
        body = _build_jsonrpc_request(tool_name, tool_params)

        headers: dict[str, str] = {
            "Content-Type": "application/json",
        }
        if auth_env_var:
            token = os.environ.get(auth_env_var, "")
            if token:
                headers["Authorization"] = f"Bearer {token}"

        timeout = aiohttp.ClientTimeout(total=60)

        context.log.info(
            f"Calling MCP tool '{tool_name}' at {server_url} "
            f"for source '{source_config['name']}'"
        )

        async with aiohttp.ClientSession() as http_session:
            async with http_session.post(
                server_url,
                headers=headers,
                json=body,
                timeout=timeout,
            ) as resp:
                resp.raise_for_status()
                raw_data = await resp.json()

        # Extract records from JSON-RPC response
        records = _extract_results(raw_data)

        records_ingested = 0
        now = datetime.now(timezone.utc)
        content_hash = compute_content_hash(records)

        # Simple quality score: 1.0 if records returned, 0.0 if empty
        quality_score = 1.0 if records else 0.0

        upsert_sql = text(INGESTED_RECORDS_UPSERT_SQL)

        async with db_session(db_url) as session:
            for idx, record in enumerate(records):
                record_key = derive_record_key(
                    record, idx, source_id
                )
                record_id = uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    f"mcp:{source_id}:{record_key}",
                )
                await session.execute(
                    upsert_sql,
                    {
                        "id": str(record_id),
                        "source_id": str(source_id),
                        "record_key": record_key,
                        "data": json.dumps(
                            record, default=str
                        ),
                        "content_hash": content_hash,
                        "ingested_at": now,
                    },
                )
                records_ingested += 1

            await session.commit()

            # --- Lineage recording ---
            try:
                from d4bl_pipelines.quality.lineage import (
                    build_lineage_record,
                    write_lineage_batch,
                )

                ingestion_run_id = uuid.uuid4()
                lineage_records = []
                for idx2, rec in enumerate(records):
                    rk = derive_record_key(
                        rec, idx2, source_id
                    )
                    rid = uuid.uuid5(
                        uuid.NAMESPACE_URL,
                        f"mcp:{source_id}:{rk}",
                    )
                    lineage_records.append(
                        build_lineage_record(
                            ingestion_run_id=ingestion_run_id,
                            target_table="ingested_records",
                            record_id=rid,
                            source_url=server_url,
                            source_hash=content_hash,
                            transformation={
                                "steps": [
                                    "call_mcp_tool",
                                    "extract_results",
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
            f"Ingested {records_ingested} records from MCP "
            f"tool '{tool_name}' for '{source_config['name']}'"
        )

        return MaterializeResult(
            metadata={
                "records_ingested": records_ingested,
                "server_url": server_url,
                "tool_name": tool_name,
                "content_hash": content_hash,
                "quality_score": MetadataValue.float(
                    quality_score
                ),
            }
        )

    return _asset_fn


def build_mcp_assets(
    data_sources: list[dict[str, Any]],
) -> list[AssetsDefinition]:
    """Build Dagster assets from MCP data source configs.

    Only sources with ``source_type='mcp'`` are processed;
    all others are silently skipped.

    Each entry in data_sources should have:
        - id: str or UUID -- unique identifier
        - name: str -- human-readable name (slugified for asset)
        - source_type: str -- must be 'mcp' to be included
        - config: dict with keys:
            - server_url: str -- MCP server endpoint
            - tool_name: str -- which tool to call
            - tool_params: dict -- parameters to pass (optional)
            - auth_env_var: str -- env var for auth token (optional)

    Returns a list of AssetsDefinition suitable for Dagster.
    """
    assets: list[AssetsDefinition] = []

    for source in data_sources:
        if source.get("source_type") != "mcp":
            continue

        slug = slugify(source["name"])
        description = (
            f"MCP tool ingestion: {source['name']} "
            f"(tool={source['config'].get('tool_name', '?')} "
            f"@ {source['config'].get('server_url', '?')})"
        )

        fn = _make_asset_fn(source)
        fn.__name__ = slug
        fn.__qualname__ = slug

        decorated = asset(
            name=slug,
            group_name="mcp",
            description=description,
        )(fn)

        assets.append(decorated)

    return assets
