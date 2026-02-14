"""Parse natural language queries into structured search intents."""

import json
import logging
from dataclasses import dataclass
from typing import Optional

import aiohttp

from d4bl.settings import get_settings

logger = logging.getLogger(__name__)

PARSE_PROMPT = """You are a query parser for a research platform about data justice and racial equity.

Given a user's natural language question, extract:
1. "intent": The type of query. One of: "information_retrieval", "count_query", "comparison", "timeline", "summary".
2. "entities": Key entities mentioned (people, places, policies, organizations, topics).
3. "search_queries": 1-3 rephrased search queries optimized for semantic search.
4. "data_sources": Which data sources to query. Options: "vector" (scraped research content), "structured" (research jobs, evaluations in PostgreSQL). Include both if unsure.

Respond with ONLY a JSON object, no other text.

User question: {query}"""


@dataclass
class ParsedQuery:
    """Structured representation of a parsed natural language query."""

    original_query: str
    intent: str
    entities: list[str]
    search_queries: list[str]
    data_sources: list[str]


class QueryParser:
    """Parse natural language queries using Ollama/Mistral."""

    def __init__(self, ollama_base_url: Optional[str] = None):
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
        prompt = PARSE_PROMPT.format(query=query)

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.ollama_base_url}/api/generate",
                json={
                    "model": "mistral",
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.1},
                },
            ) as response:
                if response.status != 200:
                    raise RuntimeError(
                        f"Ollama returned status {response.status}"
                    )
                data = await response.json()

        raw_text = data.get("response", "").strip()
        parsed = json.loads(raw_text)

        return ParsedQuery(
            original_query=query,
            intent=parsed.get("intent", "information_retrieval"),
            entities=parsed.get("entities", []),
            search_queries=parsed.get("search_queries", [query]),
            data_sources=parsed.get("data_sources", ["vector", "structured"]),
        )

    def _fallback_parse(self, query: str) -> ParsedQuery:
        """Simple fallback when LLM parsing fails."""
        return ParsedQuery(
            original_query=query,
            intent="information_retrieval",
            entities=[],
            search_queries=[query],
            data_sources=["vector", "structured"],
        )
