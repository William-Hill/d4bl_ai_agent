"""Fuse vector and structured search results into a synthesized answer."""

import logging
from dataclasses import dataclass
from typing import Optional

import aiohttp

from d4bl.query.structured import StructuredResult
from d4bl.settings import get_settings

logger = logging.getLogger(__name__)

SYNTHESIS_PROMPT = """You are a research assistant for a data justice platform. Based on the following sources, answer the user's question. Cite sources by number [1], [2], etc.

If the sources don't contain enough information to answer, say so clearly.

Question: {query}

Sources:
{sources_text}

Answer:"""


@dataclass
class SourceReference:
    """A source used to answer a query."""

    url: str
    title: str
    snippet: str
    source_type: str  # "vector" or "structured"
    relevance_score: float


@dataclass
class QueryResult:
    """The final result of a natural language query."""

    answer: str
    sources: list[SourceReference]
    query: str


class ResultFusion:
    """Merge, rank, and synthesize results from multiple data sources."""

    def __init__(self, ollama_base_url: Optional[str] = None):
        settings = get_settings()
        self.ollama_base_url = (
            ollama_base_url or settings.ollama_base_url
        ).rstrip("/")
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Return a persistent ClientSession, creating it if necessary."""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=60)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def close(self) -> None:
        """Close and release the underlying HTTP session."""
        if self._session is not None and not self._session.closed:
            await self._session.close()
        self._session = None

    def merge_and_rank(
        self,
        vector_results: list[dict],
        structured_results: list[StructuredResult],
    ) -> list[SourceReference]:
        """Merge vector and structured results into a ranked source list."""
        sources: list[SourceReference] = []
        seen_urls: set[str] = set()

        # Add vector results
        for vr in vector_results:
            url = vr.get("url", "")
            if url in seen_urls:
                continue
            seen_urls.add(url)
            metadata = vr.get("metadata") or {}
            sources.append(
                SourceReference(
                    url=url,
                    title=metadata.get("title", url),
                    snippet=(vr.get("content") or "")[:300],
                    source_type="vector",
                    relevance_score=float(vr.get("similarity", 0)),
                )
            )

        # Add structured results (deduplicated by job_id)
        seen_job_ids: set[str] = set()
        for sr in structured_results:
            job_key = str(sr.job_id)
            if job_key in seen_job_ids:
                continue
            seen_job_ids.add(job_key)
            sources.append(
                SourceReference(
                    url=f"job://{sr.job_id}",
                    title=f"Research: {sr.query[:80]}",
                    snippet=(sr.summary or "")[:300],
                    source_type="structured",
                    relevance_score=sr.relevance_score,
                )
            )

        # Sort by relevance score descending
        sources.sort(key=lambda s: s.relevance_score, reverse=True)
        return sources

    async def synthesize(
        self,
        query: str,
        sources: list[SourceReference],
    ) -> QueryResult:
        """Generate a synthesized answer from ranked sources using LLM."""
        if not sources:
            return QueryResult(
                answer="No relevant results found for your query.",
                sources=[],
                query=query,
            )

        try:
            answer = await self._generate_answer(query, sources)
        except Exception:
            logger.warning("LLM synthesis failed, returning raw sources", exc_info=True)
            answer = self._fallback_answer(sources)

        return QueryResult(answer=answer, sources=sources, query=query)

    async def _generate_answer(
        self, query: str, sources: list[SourceReference]
    ) -> str:
        """Use Ollama/Mistral to synthesize an answer."""
        sources_text = "\n".join(
            f"[{i + 1}] ({s.source_type}) {s.title}\n{s.snippet}"
            for i, s in enumerate(sources[:10])  # Limit context
        )
        prompt = SYNTHESIS_PROMPT.format(
            query=query, sources_text=sources_text
        )

        session = await self._get_session()
        async with session.post(
            f"{self.ollama_base_url}/api/generate",
            json={
                "model": "mistral",
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.3},
            },
        ) as response:
            if response.status != 200:
                raise RuntimeError(
                    f"Ollama returned status {response.status}"
                )
            data = await response.json()

        return data.get("response", "").strip()

    def _fallback_answer(self, sources: list[SourceReference]) -> str:
        """Build a simple answer from sources without LLM."""
        lines = ["Here are the most relevant sources found:\n"]
        for i, s in enumerate(sources[:5]):
            lines.append(f"{i + 1}. **{s.title}** ({s.source_type})")
            lines.append(f"   {s.snippet}\n")
        return "\n".join(lines)
