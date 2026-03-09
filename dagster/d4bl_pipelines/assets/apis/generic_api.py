"""Generic API asset factory.

Dynamically creates Dagster assets from data_sources rows with
source_type='api'.  Each generated asset fetches data from a
configured HTTP endpoint and upserts results into the
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
    asset,
)

# Backward-compatible aliases for tests
_slugify = slugify
_derive_record_key = derive_record_key


def _extract_path(data: Any, path: str) -> Any:
    """Walk a dot-notation path to extract nested data.

    Examples:
        _extract_path({"data": {"results": [1, 2]}}, "data.results")
        # => [1, 2]

        _extract_path({"items": [{"id": 1}]}, "items")
        # => [{"id": 1}]

        _extract_path({"a": 1}, "")
        # => {"a": 1}
    """
    if not path:
        return data
    current = data
    for key in path.split("."):
        if isinstance(current, dict):
            if key not in current:
                raise KeyError(
                    f"Key '{key}' not found in response at path "
                    f"'{path}'. Available keys: "
                    f"{list(current.keys())}"
                )
            current = current[key]
        elif isinstance(current, (list, tuple)) and key.isdigit():
            current = current[int(key)]
        else:
            raise KeyError(
                f"Cannot traverse key '{key}' on type "
                f"{type(current).__name__}"
            )
    return current


def _build_headers(
    config: dict[str, Any],
) -> dict[str, str]:
    """Build HTTP headers from config, resolving auth if present."""
    headers = dict(config.get("headers") or {})
    auth = config.get("auth")
    if not auth:
        return headers

    auth_type = auth.get("type", "").lower()
    env_var = auth.get("credentials_env_var", "")

    if auth_type == "bearer":
        token = os.environ.get(env_var, "")
        if token:
            headers["Authorization"] = f"Bearer {token}"
    elif auth_type == "api_key":
        header_name = auth.get("header_name", "X-API-Key")
        key = os.environ.get(env_var, "")
        if key:
            headers[header_name] = key

    return headers


def _make_asset_fn(source_config: dict[str, Any]):
    """Create the async asset function for a single data source."""
    source_id = source_config["id"]
    config = source_config["config"]
    url = config["url"]
    method = config.get("method", "GET").upper()
    params = config.get("params") or {}
    response_path = config.get("response_path", "")

    async def _asset_fn(
        context: AssetExecutionContext,
    ) -> MaterializeResult:
        from sqlalchemy import text

        db_url = context.resources.db_url

        headers = _build_headers(config)
        timeout = aiohttp.ClientTimeout(total=60)

        context.log.info(
            f"Fetching {method} {url} for source "
            f"'{source_config['name']}'"
        )

        async with aiohttp.ClientSession() as http_session:
            if method == "POST":
                body = config.get("body") or {}
                async with http_session.post(
                    url,
                    headers=headers,
                    json=body,
                    params=params,
                    timeout=timeout,
                ) as resp:
                    resp.raise_for_status()
                    raw_data = await resp.json()
            else:
                async with http_session.get(
                    url,
                    headers=headers,
                    params=params,
                    timeout=timeout,
                ) as resp:
                    resp.raise_for_status()
                    raw_data = await resp.json()

        # Extract records from response
        extracted = _extract_path(raw_data, response_path)
        if isinstance(extracted, dict):
            records = [extracted]
        elif isinstance(extracted, list):
            records = extracted
        else:
            records = [{"value": extracted}]

        records_ingested = 0
        now = datetime.now(timezone.utc)
        content_hash = compute_content_hash(records)

        upsert_sql = text(INGESTED_RECORDS_UPSERT_SQL)

        async with db_session(db_url) as session:
            for idx, record in enumerate(records):
                record_key = derive_record_key(
                    record, idx, source_id
                )
                record_id = uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    f"generic_api:{source_id}:{record_key}",
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
                for idx2, record2 in enumerate(records):
                    rk = derive_record_key(
                        record2, idx2, source_id
                    )
                    rid = uuid.uuid5(
                        uuid.NAMESPACE_URL,
                        f"generic_api:{source_id}:{rk}",
                    )
                    lineage_records.append(
                        build_lineage_record(
                            ingestion_run_id=ingestion_run_id,
                            target_table="ingested_records",
                            record_id=rid,
                            source_url=url,
                            source_hash=content_hash,
                            transformation={
                                "steps": [
                                    "fetch_api",
                                    "extract_path",
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
                context.log.warning(
                    f"Lineage recording failed: {lineage_exc}"
                )

        context.log.info(
            f"Ingested {records_ingested} records from "
            f"'{source_config['name']}'"
        )

        return MaterializeResult(
            metadata={
                "records_ingested": records_ingested,
                "source_url": url,
                "content_hash": content_hash,
                "source_id": str(source_id),
                "source_name": source_config["name"],
            }
        )

    return _asset_fn


def build_api_assets(
    data_sources: list[dict[str, Any]],
) -> list[AssetsDefinition]:
    """Build Dagster assets from a list of API data source configs.

    Each entry in data_sources should have:
        - id: str or UUID -- unique identifier
        - name: str -- human-readable name (slugified for asset name)
        - config: dict with keys:
            - url: str -- endpoint URL
            - method: str -- HTTP method (GET or POST)
            - headers: dict -- extra HTTP headers (optional)
            - params: dict -- query parameters (optional)
            - auth: dict -- optional, with 'type' (bearer|api_key)
              and 'credentials_env_var'
            - response_path: str -- dot-notation path to extract
              data from JSON response (optional)

    Returns a list of AssetsDefinition suitable for Dagster.
    """
    assets: list[AssetsDefinition] = []

    for source in data_sources:
        if source.get("source_type") != "api":
            continue

        slug = slugify(source["name"])
        description = (
            f"Generic API ingestion: {source['name']} "
            f"({source['config'].get('url', 'unknown url')})"
        )

        fn = _make_asset_fn(source)
        # Set function metadata for Dagster introspection
        fn.__name__ = slug
        fn.__qualname__ = slug

        decorated = asset(
            name=slug,
            group_name="apis",
            description=description,
        )(fn)

        assets.append(decorated)

    return assets
