"""Orchestrates the full NL query pipeline."""

import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from d4bl.infra.vector_store import get_vector_store
from d4bl.query.fusion import QueryResult, ResultFusion
from d4bl.query.parser import QueryParser
from d4bl.query.structured import StructuredSearcher

logger = logging.getLogger(__name__)


class QueryEngine:
    """Orchestrates NL query parsing, search, and synthesis.

    Usage:
        engine = QueryEngine()
        result = await engine.query(db=session, question="What are NIL policies?")
        print(result.answer)
        for source in result.sources:
            print(source.url, source.relevance_score)
    """

    def __init__(self, ollama_base_url: Optional[str] = None):
        self.parser = QueryParser(ollama_base_url=ollama_base_url)
        self.vector_store = get_vector_store()
        self.structured_searcher = StructuredSearcher()
        self.fusion = ResultFusion(ollama_base_url=ollama_base_url)

    async def close(self) -> None:
        """Release HTTP sessions held by parser and fusion."""
        await self.parser.close()
        await self.fusion.close()

    async def query(
        self,
        db: AsyncSession,
        question: str,
        job_id: Optional[str] = None,
        limit: int = 10,
        similarity_threshold: float = 0.7,
    ) -> QueryResult:
        """Execute a full NL query pipeline.

        Args:
            db: Async database session.
            question: The user's natural language question.
            job_id: Optional job ID to scope vector search.
            limit: Max results per data source.
            similarity_threshold: Minimum similarity for vector results.

        Returns:
            QueryResult with synthesized answer and source citations.
        """
        # 1. Parse the query
        parsed = await self.parser.parse(question)
        logger.info(
            "Parsed query: intent=%s, entities=%s, sources=%s",
            parsed.intent,
            parsed.entities,
            parsed.data_sources,
        )

        # 2. Search data sources based on parser output
        vector_results = []
        structured_results = []

        if "vector" in parsed.data_sources:
            for sq in parsed.search_queries:
                results = await self.vector_store.search_similar(
                    db=db,
                    query_text=sq,
                    job_id=job_id,
                    limit=limit,
                    similarity_threshold=similarity_threshold,
                )
                vector_results.extend(results)

        if "structured" in parsed.data_sources:
            structured_results = await self.structured_searcher.search(
                db=db,
                search_queries=parsed.search_queries,
                limit=limit,
            )

        # 3. Merge and rank results
        sources = self.fusion.merge_and_rank(
            vector_results, structured_results
        )

        # 4. Synthesize answer
        return await self.fusion.synthesize(
            query=question, sources=sources
        )
