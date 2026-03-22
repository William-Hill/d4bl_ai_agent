"""Fuse vector and structured search results into a synthesized answer."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from string import Template

from d4bl.llm.ollama_client import model_for_task, ollama_generate
from d4bl.query.structured import StructuredResult
from d4bl.settings import get_settings

logger = logging.getLogger(__name__)

SYNTHESIS_PROMPT = Template("""\
You are a research assistant for a data justice platform. \
Based on the following sources, answer the user's question. \
Cite sources by number [1], [2], etc.

If the sources don't contain enough information to answer, say so clearly.

Question: $query

Sources:
$sources_text

Answer:""")


@dataclass(frozen=True)
class SourceReference:
    """A source used to answer a query."""

    url: str
    title: str
    snippet: str
    source_type: str  # "vector" or "structured"
    relevance_score: float
    # Provenance metadata (populated for ingested data results)
    data_source_name: str | None = None
    quality_score: float | None = None
    last_updated: str | None = None
    coverage_notes: str | None = None


@dataclass(frozen=True)
class QueryResult:
    """The final result of a natural language query."""

    answer: str
    sources: list[SourceReference]
    query: str


def _summarize_provenance(
    provenance: list,
) -> tuple[str | None, float | None, str | None]:
    """Summarize a list of ProvenanceInfo into (name, quality, notes)."""
    if not provenance:
        return None, None, None

    name = ", ".join(p.data_source_name for p in provenance)
    scores = [p.quality_score for p in provenance if p.quality_score is not None]
    quality = round(sum(scores) / len(scores), 2) if scores else None
    all_gaps = [g for p in provenance for g in p.coverage_gaps]
    notes = "; ".join(all_gaps) if all_gaps else None
    return name, quality, notes


class ResultFusion:
    """Merge, rank, and synthesize results from multiple data sources."""

    def __init__(self, ollama_base_url: str | None = None) -> None:
        settings = get_settings()
        self.ollama_base_url = (
            ollama_base_url or settings.ollama_base_url
        ).rstrip("/")

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
            job_key = sr.job_id
            if job_key in seen_job_ids:
                continue
            seen_job_ids.add(job_key)

            prov_name, prov_quality, prov_notes = _summarize_provenance(
                sr.provenance
            )

            sources.append(
                SourceReference(
                    url=f"job://{sr.job_id}",
                    title=f"Research: {sr.query[:80]}",
                    snippet=(sr.summary or "")[:300],
                    source_type="structured",
                    relevance_score=sr.relevance_score,
                    data_source_name=prov_name,
                    quality_score=prov_quality,
                    last_updated=sr.created_at or None,
                    coverage_notes=prov_notes,
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
        """Use the fine-tuned explainer model (or fallback) to synthesize an answer."""
        sources_text = "\n".join(
            f"[{i + 1}] ({s.source_type}) {s.title}\n{s.snippet}"
            for i, s in enumerate(sources[:10])
        )
        prompt = SYNTHESIS_PROMPT.substitute(
            query=query, sources_text=sources_text
        )

        return await ollama_generate(
            base_url=self.ollama_base_url,
            prompt=prompt,
            model=model_for_task("explainer"),
            temperature=0.3,
            timeout_seconds=60,
        )

    def _fallback_answer(self, sources: list[SourceReference]) -> str:
        """Build a simple answer from sources without LLM."""
        lines = ["Here are the most relevant sources found:\n"]
        for i, s in enumerate(sources[:5]):
            lines.append(f"{i + 1}. **{s.title}** ({s.source_type})")
            lines.append(f"   {s.snippet}\n")
        return "\n".join(lines)
