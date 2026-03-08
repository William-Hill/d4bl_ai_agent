"""Lineage record builder for D4BL data ingestion assets."""

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession


def build_lineage_record(
    ingestion_run_id: uuid.UUID,
    target_table: str,
    record_id: uuid.UUID,
    source_url: str | None = None,
    source_hash: str | None = None,
    transformation: dict[str, Any] | None = None,
    quality_score: float | None = None,
    coverage_metadata: dict[str, Any] | None = None,
    bias_flags: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a lineage record dict for a single ingested row.

    Args:
        ingestion_run_id: UUID of the current ingestion run.
        target_table: Name of the destination table (e.g. "census_indicators").
        record_id: Primary-key UUID of the row being tracked.
        source_url: URL the data was fetched from, if applicable.
        source_hash: SHA-256 hex digest of the raw source payload.
        transformation: Freeform dict describing transforms applied to the data.
        quality_score: Numeric quality score (1-5 scale) from quality checks.
        coverage_metadata: Dict with demographic/geographic coverage details.
        bias_flags: Dict with any detected bias or representativeness warnings.

    Returns:
        A dict ready to be passed to ``write_lineage_batch``.
    """
    return {
        "id": uuid.uuid4(),
        "ingestion_run_id": ingestion_run_id,
        "target_table": target_table,
        "record_id": record_id,
        "source_url": source_url,
        "source_hash": source_hash,
        "transformation": transformation,
        "quality_score": quality_score,
        "coverage_metadata": coverage_metadata,
        "bias_flags": bias_flags,
        "retrieved_at": datetime.now(timezone.utc),
    }


async def write_lineage_batch(
    session: AsyncSession,
    records: list[dict[str, Any]],
) -> int:
    """Write a batch of lineage records to the data_lineage table.

    Args:
        session: SQLAlchemy AsyncSession.
        records: List of dicts from build_lineage_record().

    Returns:
        Number of records written.
    """
    from sqlalchemy import text

    count = 0
    try:
        for rec in records:
            await session.execute(
                text("""
                    INSERT INTO data_lineage
                        (id, ingestion_run_id, target_table, record_id,
                         source_url, source_hash, transformation,
                         quality_score, coverage_metadata, bias_flags, retrieved_at)
                    VALUES
                        (CAST(:id AS UUID), CAST(:ingestion_run_id AS UUID),
                         :target_table, CAST(:record_id AS UUID),
                         :source_url, :source_hash,
                         CAST(:transformation AS JSONB),
                         :quality_score,
                         CAST(:coverage_metadata AS JSONB),
                         CAST(:bias_flags AS JSONB),
                         :retrieved_at)
                """),
                {
                    "id": str(rec["id"]),
                    "ingestion_run_id": str(rec["ingestion_run_id"]),
                    "target_table": rec["target_table"],
                    "record_id": str(rec["record_id"]),
                    "source_url": rec["source_url"],
                    "source_hash": rec["source_hash"],
                    "transformation": json.dumps(rec["transformation"]) if rec["transformation"] is not None else None,
                    "quality_score": rec["quality_score"],
                    "coverage_metadata": json.dumps(rec["coverage_metadata"]) if rec["coverage_metadata"] is not None else None,
                    "bias_flags": json.dumps(rec["bias_flags"]) if rec["bias_flags"] is not None else None,
                    "retrieved_at": rec["retrieved_at"],
                },
            )
            count += 1
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    return count
