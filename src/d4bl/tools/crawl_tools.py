"""
Crawl provider tooling shared between Crawl4AI and Firecrawl.

This isolates crawling/search concerns away from crew wiring to keep `crew.py`
smaller and easier to test.
"""
from __future__ import annotations

import json
import os
import re
import logging
from typing import List, Type, Union

import requests
from crewai.tools import BaseTool
from crewai_tools import FirecrawlSearchTool
from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)


class FirecrawlSearchWrapperInput(BaseModel):
    """Input schema for Firecrawl Search Wrapper tool."""

    query: Union[str, dict] = Field(
        ..., description="The search query as a plain text string. Example: 'data science trends 2025'"
    )

    @field_validator("query", mode="before")
    @classmethod
    def normalize_query(cls, v):
        """Normalize input - handle both strings and dicts from Ollama."""
        if isinstance(v, dict):
            if "query" in v:
                return v["query"]
            if "description" in v:
                desc = v["description"]
                if isinstance(desc, str) and len(desc) > 5:
                    return desc
            if "value" in v:
                return v["value"]

            for _, value in v.items():
                if isinstance(value, str) and len(value) > 5:
                    return value
            return str(v)

        if isinstance(v, str):
            return v

        return str(v)


class FirecrawlSearchWrapper(BaseTool):
    """Wrapper tool for FirecrawlSearchTool that normalizes input format for Ollama compatibility."""

    name: str = "Firecrawl web search tool"
    description: str = (
        "Use Firecrawl's web search and crawl capabilities. "
        "Provide a plain text query string; returns structured crawl results."
    )
    args_schema: Type[BaseModel] = FirecrawlSearchWrapperInput

    def __init__(self, firecrawl_tool: FirecrawlSearchTool):
        super().__init__()
        object.__setattr__(self, "_firecrawl_tool", firecrawl_tool)

    def _run(self, query: Union[str, dict]) -> str:
        normalized_query = FirecrawlSearchWrapperInput(query=query).query
        return self._firecrawl_tool._run(query=normalized_query)


class Crawl4AISearchTool(BaseTool):
    """Simple HTTP wrapper for a self-hosted Crawl4AI service."""

    name: str = "Crawl4AI web search tool"
    description: (
        "Search or scrape via Crawl4AI self-hosted service. "
        "Provide a plain text query; returns JSON/text from the service."
    )

    def __init__(self, base_url: str, api_key: str | None = None, timeout: int = 60):
        super().__init__()
        object.__setattr__(self, "_base_url", base_url.rstrip("/"))
        object.__setattr__(self, "_api_key", api_key)
        object.__setattr__(self, "_timeout", timeout)

    class InputSchema(BaseModel):
        query: str = Field(..., description="Plain text search or crawl query")

        @field_validator("query")
        def validate_query(cls, v):
            if not isinstance(v, str):
                raise ValueError("Query must be a plain text string")
            if not v.strip():
                raise ValueError("Query cannot be empty")
            return v

    args_schema: Type[BaseModel] = InputSchema

    def _run(self, query: str) -> str:
        # Crawl4AI expects URLs, not search queries
        # If query looks like a URL, use it directly
        # Otherwise, use Serper API to convert search query to URLs
        url_pattern = re.compile(
            r"^https?://"  # http:// or https://
            r"(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|"  # domain...
            r"localhost|"  # localhost...
            r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})"  # ...or ip
            r"(?::\d+)?"
            r"(?:/?|[/?]\S+)$",
            re.IGNORECASE,
        )

        if url_pattern.match(query.strip()):
            urls = [query.strip()]
        else:
            url_matches = re.findall(r"https?://[^\s]+", query)
            if url_matches:
                urls = url_matches
            else:
                urls = self._lookup_urls_via_serper(query)
                if isinstance(urls, str):
                    return urls  # error JSON from Serper lookup

        return self._crawl_urls_with_retry(urls, query)

    def _lookup_urls_via_serper(self, query: str) -> List[str] | str:
        """Use Serper.dev to turn a search query into URL list; return str on error."""
        serper_api_key = os.getenv("SERPER_API_KEY") or os.getenv("SERP_API_KEY")
        if not serper_api_key:
            return json.dumps(
                {
                    "error": "Search query provided but no Serper API key found",
                    "query": query,
                    "suggestion": "Set SERPER_API_KEY or SERP_API_KEY environment variable to enable search query support",
                },
                indent=2,
            )

        try:
            serper_url = "https://google.serper.dev/search"
            headers = {"X-API-KEY": serper_api_key, "Content-Type": "application/json"}
            payload = {"q": query, "num": 5}

            serper_resp = requests.post(
                serper_url, json=payload, headers=headers, timeout=self._timeout
            )

            if serper_resp.status_code != 200:
                return json.dumps(
                    {
                        "error": f"Serper.dev API error: HTTP {serper_resp.status_code}",
                        "query": query,
                        "response": serper_resp.text[:500],
                    },
                    indent=2,
                )

            search_dict = serper_resp.json()

            if "error" in search_dict:
                return json.dumps(
                    {
                        "error": f"Serper.dev API error: {search_dict.get('error')}",
                        "query": query,
                        "details": search_dict,
                    },
                    indent=2,
                )

            results = search_dict.get("organic", [])
            logger.debug("Serper.dev response keys: %s", list(search_dict.keys()))
            logger.debug("Serper.dev organic results: %s", len(results))

            if not results:
                knowledge_graph = search_dict.get("knowledgeGraph", {})
                answer_box = search_dict.get("answerBox", {})

                if knowledge_graph or answer_box:
                    return json.dumps(
                        {
                            "error": "No organic search results found",
                            "query": query,
                            "suggestion": "Serper returned knowledge graph/answer box but no URLs to crawl. Try a more specific search query.",
                            "knowledge_graph": knowledge_graph,
                            "answer_box": answer_box,
                        },
                        indent=2,
                    )

                return json.dumps(
                    {
                        "error": "No search results found",
                        "query": query,
                        "response_keys": list(search_dict.keys()),
                        "has_organic": "organic" in search_dict,
                        "organic_value": search_dict.get("organic"),
                        "full_response_sample": {
                            k: str(v)[:200] for k, v in list(search_dict.items())[:5]
                        },
                    },
                    indent=2,
                )

            urls = [result.get("link") for result in results if result.get("link")]
            if not urls:
                return json.dumps(
                    {
                        "error": "No URLs found in search results",
                        "query": query,
                        "results_count": len(results),
                        "results_sample": results[:2] if results else [],
                    },
                    indent=2,
                )

            logger.info("Found %s URLs from Serper.dev: %s", len(urls), urls[:3])
            return urls

        except requests.exceptions.RequestException as e:
            return json.dumps(
                {"error": f"Serper.dev API request error: {str(e)}", "query": query},
                indent=2,
            )
        except Exception as e:  # pragma: no cover - defensive
            import traceback

            return json.dumps(
                {
                    "error": f"Serper.dev API error: {str(e)}",
                    "query": query,
                    "traceback": traceback.format_exc(),
                },
                indent=2,
            )

    def _crawl_urls_with_retry(self, urls: List[str], query: str) -> str:
        """Crawl URLs with retry logic and error recovery."""
        endpoint = f"{self._base_url}/crawl"
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        max_retries = 3
        last_error = None

        for attempt in range(max_retries):
            try:
                resp = requests.post(
                    endpoint,
                    json={"urls": urls},
                    headers=headers,
                    timeout=self._timeout,
                )

                if resp.status_code == 200:
                    crawl_results = resp.json()
                    formatted_results = {
                        "query": query,
                        "urls_crawled": urls,
                        "results": crawl_results.get("results", []),
                        "success": crawl_results.get("success", False),
                    }
                    logger.info(
                        "Successfully crawled %s URLs on attempt %s",
                        len(urls),
                        attempt + 1,
                    )
                    return json.dumps(formatted_results, indent=2)

                if resp.status_code in (429, 503):
                    wait_time = (attempt + 1) * 2
                    logger.warning(
                        "Crawl4AI returned %s on attempt %s/%s. Retrying in %ss...",
                        resp.status_code,
                        attempt + 1,
                        max_retries,
                        wait_time,
                    )
                    if attempt < max_retries - 1:
                        import time

                        time.sleep(wait_time)
                        continue

                error_msg = f"Crawl4AI error {resp.status_code}: {resp.text[:500]}"
                logger.error(error_msg)
                raise ValueError(error_msg)

            except requests.exceptions.ConnectionError as e:
                last_error = e
                wait_time = (attempt + 1) * 2
                logger.warning(
                    "Crawl4AI connection error on attempt %s/%s: %s. Retrying in %ss...",
                    attempt + 1,
                    max_retries,
                    str(e),
                    wait_time,
                )
                if attempt < max_retries - 1:
                    import time

                    time.sleep(wait_time)
                    continue
                return self._try_firecrawl_fallback(query, urls, str(e))

            except requests.exceptions.Timeout as e:
                last_error = e
                logger.warning("Crawl4AI timeout on attempt %s/%s", attempt + 1, max_retries)
                if attempt < max_retries - 1:
                    import time

                    time.sleep((attempt + 1) * 2)
                    continue
                return self._try_firecrawl_fallback(query, urls, f"Timeout: {str(e)}")

            except Exception as e:  # pragma: no cover - defensive
                last_error = e
                logger.error("Unexpected error crawling URLs: %s", str(e), exc_info=True)
                if attempt < max_retries - 1:
                    import time

                    time.sleep((attempt + 1) * 2)
                    continue

        return json.dumps(
            {
                "error": f"Failed to crawl URLs after {max_retries} attempts",
                "query": query,
                "urls": urls,
                "last_error": str(last_error) if last_error else "Unknown error",
                "suggestion": "Check Crawl4AI service status or try again later",
            },
            indent=2,
        )

    def _try_firecrawl_fallback(self, query: str, urls: List[str], error: str) -> str:
        """Try Firecrawl as fallback when Crawl4AI fails."""
        try:
            firecrawl_api_key = os.getenv("FIRECRAWL_API_KEY")
            if not firecrawl_api_key:
                logger.warning("Firecrawl API key not available for fallback")
                return json.dumps(
                    {
                        "error": f"Crawl4AI failed: {error}",
                        "query": query,
                        "urls": urls,
                        "fallback": "Firecrawl not configured",
                    },
                    indent=2,
                )

            logger.info("Attempting Firecrawl fallback...")
            firecrawl_tool = FirecrawlSearchTool(api_key=firecrawl_api_key)
            result = firecrawl_tool._run(query=query)
            logger.info("Firecrawl fallback succeeded")

            return json.dumps(
                {
                    "query": query,
                    "urls_attempted": urls,
                    "fallback_used": "Firecrawl",
                    "original_error": error,
                    "results": result,
                },
                indent=2,
            )

        except Exception as fallback_error:  # pragma: no cover - defensive
            logger.error("Firecrawl fallback also failed: %s", str(fallback_error))
            return json.dumps(
                {
                    "error": f"Crawl4AI failed: {error}",
                    "fallback_error": str(fallback_error),
                    "query": query,
                    "urls": urls,
                    "status": "complete_failure",
                },
                indent=2,
            )

