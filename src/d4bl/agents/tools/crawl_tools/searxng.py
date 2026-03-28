"""SearXNG meta-search tool for CrewAI agents.

Queries a self-hosted SearXNG instance for web search results.
Replaces Serper.dev as the search provider.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx
from crewai.tools import BaseTool

from .utils import PROBLEMATIC_DOMAINS

logger = logging.getLogger(__name__)


class SearXNGSearchTool(BaseTool):
    """Search the web using a self-hosted SearXNG instance."""

    name: str = "SearXNG Web Search"
    description: str = (
        "Search the web for information on any topic. Returns a list of "
        "results with title, URL, and snippet. Use specific search queries "
        "for best results."
    )
    base_url: str = "http://searxng:8080"
    default_category: str = "general"
    max_results: int = 10
    timeout: int = 30

    def __init__(
        self,
        base_url: str = "http://searxng:8080",
        default_category: str = "general",
        max_results: int = 10,
        timeout: int = 30,
        **kwargs: Any,
    ):
        super().__init__(
            base_url=base_url,
            default_category=default_category,
            max_results=max_results,
            timeout=timeout,
            **kwargs,
        )

    def _is_problematic_url(self, url: str) -> bool:
        """Return True if the URL belongs to a known problematic domain."""
        return bool(url and any(domain in url.lower() for domain in PROBLEMATIC_DOMAINS))

    def _run(self, query: str) -> str:
        """Execute a search query against SearXNG.

        Args:
            query: The search query string.

        Returns:
            JSON string of results: [{"title": ..., "url": ..., "content": ...}]
        """
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.get(
                    f"{self.base_url}/search",
                    params={
                        "q": query,
                        "format": "json",
                        "categories": self.default_category,
                    },
                )

                if response.status_code != 200:
                    return json.dumps(
                        {"error": f"SearXNG returned HTTP {response.status_code}"}
                    )

                data = response.json()
                results = data.get("results", [])

                # Filter problematic URLs and build output list
                filtered = []
                for r in results:
                    url = r.get("url", "")
                    if self._is_problematic_url(url):
                        logger.info("Skipping paywalled/problematic URL: %s", url)
                        continue
                    filtered.append(
                        {
                            "title": r.get("title", ""),
                            "url": url,
                            "content": r.get("content", ""),
                        }
                    )

                # Limit results
                filtered = filtered[: self.max_results]

                logger.info(
                    "SearXNG: query=%r category=%s results=%d",
                    query,
                    self.default_category,
                    len(filtered),
                )

                return json.dumps(filtered, indent=2)

        except Exception as e:
            logger.exception("SearXNG search failed for query: %s", query)
            return json.dumps({"error": f"Search failed: {str(e)}"})
