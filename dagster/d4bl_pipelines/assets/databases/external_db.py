"""External database asset factory.

Dynamically creates Dagster assets from data_sources rows with
source_type='database'.  Each generated asset connects to an external
Postgres/MySQL database, executes a configured query, and upserts
results into the local ingested_records table.
"""

import hashlib
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any

from dagster import (
    AssetExecutionContext,
    AssetsDefinition,
    MaterializeResult,
    MetadataValue,
    asset,
)

from d4bl_pipelines.utils import (
    INGESTED_RECORDS_UPSERT_SQL,
    compute_content_hash,
    derive_record_key,
    slugify,
)

# Backward-compatible aliases for tests
_slugify = slugify
_derive_record_key = derive_record_key


async def _get_last_run_time(session, source_id: str) -> datetime | None:
    """Query ingestion_runs table for last successful completion time.

    Returns None if no previous successful run exists.
    """
    from sqlalchemy import text

    result = await session.execute(
        text("""
            SELECT completed_at
            FROM ingestion_runs
            WHERE source_id = CAST(:source_id AS UUID)
              AND status = 'success'
            ORDER BY completed_at DESC
            LIMIT 1
        """),
        {"source_id": str(source_id)},
    )
    row = result.fetchone()
    return row[0] if row else None


def _make_asset_fn(source_config: dict[str, Any]):
    """Create the async asset function for a single database source."""
    source_id = source_config["id"]
    config = source_config["config"]
    connection_env_var = config["connection_env_var"]
    query = config["query"]
    incremental = config.get("incremental", False)

    async def _asset_fn(
        context: AssetExecutionContext,
    ) -> MaterializeResult:
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import (
            AsyncSession,
            create_async_engine,
        )
        from sqlalchemy.orm import sessionmaker

        # --- Connect to external database ---
        external_db_url = os.environ.get(connection_env_var, "")
        if not external_db_url:
            raise ValueError(
                f"Environment variable '{connection_env_var}' is not set "
                f"or empty. Cannot connect to external database for "
                f"source '{source_config['name']}'."
            )

        external_engine = create_async_engine(
            external_db_url, pool_size=3, max_overflow=5
        )

        # --- Connect to local database ---
        db_url = context.resources.db_url
        local_engine = create_async_engine(
            db_url, pool_size=3, max_overflow=5
        )
        local_session_factory = sessionmaker(
            local_engine, class_=AsyncSession, expire_on_commit=False
        )

        try:
            # Resolve incremental placeholder
            resolved_query = query
            if incremental and ":last_run" in query:
                async with local_session_factory() as session:
                    last_run = await _get_last_run_time(
                        session, source_id
                    )
                if last_run is None:
                    # No prior run -- use epoch as fallback
                    last_run = datetime(1970, 1, 1, tzinfo=timezone.utc)
                resolved_query = query.replace(
                    ":last_run",
                    f"'{last_run.isoformat()}'",
                )

            context.log.info(
                f"Executing query on external DB for source "
                f"'{source_config['name']}' via env var "
                f"'{connection_env_var}'"
            )

            # --- Execute query on external database ---
            async with external_engine.connect() as conn:
                result = await conn.execute(text(resolved_query))
                columns = list(result.keys())
                rows = result.fetchall()

            records = [
                dict(zip(columns, row)) for row in rows
            ]

            context.log.info(
                f"Fetched {len(records)} rows from external DB"
            )

            # --- Upsert into local ingested_records ---
            records_ingested = 0
            now = datetime.now(timezone.utc)
            content_hash = compute_content_hash(records)
            query_hash = hashlib.sha256(
                resolved_query.encode()
            ).hexdigest()[:32]

            upsert_sql = text(INGESTED_RECORDS_UPSERT_SQL)

            async with local_session_factory() as session:
                for idx, record in enumerate(records):
                    record_key = derive_record_key(
                        record, idx, source_id
                    )
                    record_id = uuid.uuid5(
                        uuid.NAMESPACE_URL,
                        f"external_db:{source_id}:{record_key}",
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
                            f"external_db:{source_id}:{rk}",
                        )
                        lineage_records.append(
                            build_lineage_record(
                                ingestion_run_id=ingestion_run_id,
                                target_table="ingested_records",
                                record_id=rid,
                                source_url=connection_env_var,
                                source_hash=content_hash,
                                transformation={
                                    "steps": [
                                        "query_external_db",
                                        "transform",
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
            await external_engine.dispose()
            await local_engine.dispose()

        # Basic quality score: 1.0 if records were returned,
        # 0.0 if the query returned nothing.
        quality_score = 1.0 if records_ingested > 0 else 0.0

        context.log.info(
            f"Ingested {records_ingested} records from "
            f"'{source_config['name']}'"
        )

        return MaterializeResult(
            metadata={
                "records_ingested": records_ingested,
                "source_db": connection_env_var,
                "query_hash": query_hash,
                "content_hash": content_hash,
                "quality_score": MetadataValue.float(quality_score),
                "source_id": str(source_id),
                "source_name": source_config["name"],
            }
        )

    return _asset_fn


def build_external_db_assets(
    data_sources: list[dict[str, Any]],
) -> list[AssetsDefinition]:
    """Build Dagster assets from a list of database data source configs.

    Only processes entries where source_type == 'database'.

    Each entry in data_sources should have:
        - id: str or UUID -- unique identifier
        - name: str -- human-readable name (slugified for asset name)
        - source_type: str -- must be 'database' to be processed
        - config: dict with keys:
            - connection_env_var: str -- name of the environment variable
              containing the database connection string
            - query: str -- SQL query to execute; may contain :last_run
              placeholder for incremental loads
            - incremental: bool -- whether to use incremental loading
              (default false)

    Returns a list of AssetsDefinition suitable for Dagster.
    """
    assets: list[AssetsDefinition] = []

    for source in data_sources:
        if source.get("source_type") != "database":
            continue

        slug = slugify(source["name"])
        description = (
            f"External database ingestion: {source['name']} "
            f"(env: {source['config'].get('connection_env_var', '?')})"
        )

        fn = _make_asset_fn(source)
        # Set function metadata for Dagster introspection
        fn.__name__ = slug
        fn.__qualname__ = slug

        decorated = asset(
            name=slug,
            group_name="databases",
            description=description,
        )(fn)

        assets.append(decorated)

    return assets
