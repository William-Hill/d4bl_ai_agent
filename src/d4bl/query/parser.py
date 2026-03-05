"""Parse natural language queries into structured search intents."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from string import Template

from d4bl.llm.ollama_client import ollama_generate
from d4bl.settings import get_settings

logger = logging.getLogger(__name__)

PARSE_PROMPT = Template("""\
You are a query parser for a research platform about \
data justice and racial equity.

Given a user's natural language question, extract:
1. "entities": Key entities mentioned (people, places, policies, \
organizations, topics).
2. "search_queries": 1-3 rephrased search queries optimized for \
semantic search.
3. "data_sources": Which data sources to query. Options: "vector" \
(scraped research content), "structured" (research jobs, evaluations \
in PostgreSQL). Include both if unsure.

Respond with ONLY a JSON object, no other text.

User question: $query""")


@dataclass(frozen=True)
class ParsedQuery:
    """Structured representation of a parsed natural language query."""

    original_query: str
    entities: tuple[str, ...]
    search_queries: tuple[str, ...]
    data_sources: tuple[str, ...]


class QueryParser:
    """Parse natural language queries using Ollama/Mistral."""

    def __init__(self, ollama_base_url: str | None = None) -> None:
        settings = get_settings()
        self.ollama_base_url = (
            ollama_base_url or settings.ollama_base_url
        ).rstrip("/")

    async def parse(self, query: str) -> ParsedQuery:
        """Parse a natural language query into a structured ParsedQuery.

        Falls back to a simple keyword-based ParsedQuery if the LLM call
        fails.
        """
        try:
            return await self._parse_with_llm(query)
        except Exception:
            logger.warning(
                "LLM query parsing failed, using fallback", exc_info=True
            )
            return self._fallback_parse(query)

    async def _parse_with_llm(self, query: str) -> ParsedQuery:
        """Use Ollama/Mistral to parse the query."""
        prompt = PARSE_PROMPT.substitute(query=query)

        raw_text = await ollama_generate(
            base_url=self.ollama_base_url,
            prompt=prompt,
            temperature=0.1,
            timeout_seconds=30,
        )
        parsed = json.loads(raw_text)

        # Guard against hallucinated field types (e.g. "entities": "Mississippi")
        entities = parsed.get("entities", [])
        if not isinstance(entities, list):
            entities = []

        search_queries = parsed.get("search_queries", [query])
        if not isinstance(search_queries, list) or not search_queries:
            search_queries = [query]

        data_sources = parsed.get("data_sources", ["vector", "structured"])
        if not isinstance(data_sources, list) or not data_sources:
            data_sources = ["vector", "structured"]

        return ParsedQuery(
            original_query=query,
            entities=tuple(entities),
            search_queries=tuple(search_queries),
            data_sources=tuple(data_sources),
        )

    def _fallback_parse(self, query: str) -> ParsedQuery:
        """Simple fallback when LLM parsing fails."""
        return ParsedQuery(
            original_query=query,
            entities=(),
            search_queries=(query,),
            data_sources=("vector", "structured"),
        )
