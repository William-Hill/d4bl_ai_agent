"""Search structured PostgreSQL data (research jobs, evaluations)."""

import logging
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from d4bl.infra.database import ResearchJob

logger = logging.getLogger(__name__)


@dataclass
class StructuredResult:
    """A result from the structured database."""

    job_id: str
    query: str
    status: str
    summary: Optional[str]
    created_at: str
    relevance_score: float


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
                        row.query, search_queries
                    ),
                )
                for row in rows
            ]
        except Exception:
            logger.warning("Structured search failed", exc_info=True)
            return []

    def _extract_summary(self, result: Optional[dict]) -> Optional[str]:
        """Extract a summary string from the job result JSON."""
        if not result:
            return None
        if isinstance(result, dict):
            return result.get("summary") or result.get("raw", "")[:500]
        return str(result)[:500]

    def _score_relevance(
        self, job_query: str, search_queries: list[str]
    ) -> float:
        """Simple keyword overlap relevance score (0.0 to 1.0)."""
        job_words = set(job_query.lower().split())
        max_score = 0.0
        for sq in search_queries:
            sq_words = set(sq.lower().split())
            if not sq_words:
                continue
            overlap = len(job_words & sq_words) / len(sq_words)
            max_score = max(max_score, overlap)
        return round(max_score, 2)
