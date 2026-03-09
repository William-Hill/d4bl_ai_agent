"""Search structured PostgreSQL data (research jobs, evaluations)."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from d4bl.infra.database import (
    DataLineage,
    DataSource,
    IngestionRun,
    ResearchJob,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProvenanceInfo:
    """Lineage metadata attached to a search result."""

    data_source_name: str
    quality_score: float | None = None
    coverage_gaps: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class StructuredResult:
    """A result from the structured database."""

    job_id: str
    query: str
    status: str
    summary: str | None
    created_at: str
    relevance_score: float
    provenance: list[ProvenanceInfo] = field(default_factory=list)


class StructuredSearcher:
    """Search research jobs and results in PostgreSQL."""

    async def search(
        self,
        db: AsyncSession,
        search_queries: list[str],
        limit: int = 10,
    ) -> list[StructuredResult]:
        """Search research_jobs table for matching completed jobs.

        Uses ILIKE text matching against the query and result fields.
        Returns results ordered by creation date (newest first).
        """
        if not search_queries:
            return []

        try:
            # Build OR conditions for each search query keyword
            conditions = []
            for sq in search_queries:
                for keyword in sq.split():
                    if len(keyword) >= 3:  # Skip short words
                        pattern = f"%{keyword}%"
                        conditions.append(ResearchJob.query.ilike(pattern))

            if not conditions:
                return []

            stmt = (
                select(ResearchJob)
                .where(
                    ResearchJob.status == "completed",
                    or_(*conditions),
                )
                .order_by(ResearchJob.created_at.desc())
                .limit(limit)
            )

            result = await db.execute(stmt)
            rows = result.scalars().all()

            query_word_sets = self._precompute_query_word_sets(search_queries)

            return [
                StructuredResult(
                    job_id=str(row.job_id),
                    query=row.query,
                    status=row.status,
                    summary=self._extract_summary(row.result),
                    created_at=row.created_at.isoformat()
                    if row.created_at
                    else "",
                    relevance_score=self._score_relevance(
                        row.query, query_word_sets
                    ),
                )
                for row in rows
            ]
        except Exception:
            logger.warning("Structured search failed", exc_info=True)
            return []

    def _extract_summary(self, result: dict | None) -> str | None:
        """Extract a summary string from the job result JSON."""
        if not result:
            return None
        if isinstance(result, dict):
            return result.get("summary") or result.get("raw", "")[:500]
        return str(result)[:500]

    @staticmethod
    def _precompute_query_word_sets(
        search_queries: list[str],
    ) -> list[frozenset[str]]:
        """Precompute lowercased word sets for search queries."""
        return [
            frozenset(sq.lower().split())
            for sq in search_queries
            if sq.strip()
        ]

    def _score_relevance(
        self,
        job_query: str,
        query_word_sets: list[frozenset[str]],
    ) -> float:
        """Simple keyword overlap relevance score (0.0 to 1.0)."""
        job_words = set(job_query.lower().split())
        max_score = 0.0
        for sq_words in query_word_sets:
            if not sq_words:
                continue
            overlap = len(job_words & sq_words) / len(sq_words)
            max_score = max(max_score, overlap)
        return round(max_score, 2)

    async def get_provenance_for_table(
        self,
        db: AsyncSession,
        target_table: str,
        limit: int = 20,
    ) -> list[ProvenanceInfo]:
        """Fetch aggregated provenance info for a target table.

        Returns one ProvenanceInfo per data source that contributed records
        to the given table, including average quality score and coverage gaps.
        """
        try:
            result = await db.execute(
                select(
                    DataSource.name,
                    func.avg(DataLineage.quality_score).label("avg_quality"),
                    DataLineage.coverage_metadata,
                )
                .join(
                    IngestionRun,
                    DataLineage.ingestion_run_id == IngestionRun.id,
                )
                .join(
                    DataSource,
                    IngestionRun.data_source_id == DataSource.id,
                )
                .where(DataLineage.target_table == target_table)
                .group_by(DataSource.name, DataLineage.coverage_metadata)
                .limit(limit)
            )
            rows = result.all()

            provenance_list = []
            for source_name, avg_quality, coverage_meta in rows:
                gaps = []
                if coverage_meta and isinstance(coverage_meta, dict):
                    gaps = coverage_meta.get("gaps", [])
                provenance_list.append(
                    ProvenanceInfo(
                        data_source_name=source_name,
                        quality_score=(
                            round(avg_quality, 2) if avg_quality else None
                        ),
                        coverage_gaps=gaps,
                    )
                )
            return provenance_list
        except Exception:
            logger.warning("Provenance lookup failed", exc_info=True)
            return []
