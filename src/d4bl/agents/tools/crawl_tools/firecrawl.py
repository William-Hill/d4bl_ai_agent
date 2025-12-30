"""
Firecrawl search tools for web crawling and search.
"""
from __future__ import annotations

import json
import logging
from typing import Type, Union

import requests
from crewai.tools import BaseTool
from crewai_tools import FirecrawlSearchTool
from pydantic import BaseModel

from d4bl.agents.tools.crawl_tools.utils import (
    FirecrawlSearchWrapperInput,
    filter_problematic_urls,
)

logger = logging.getLogger(__name__)

# Try to import firecrawl-py SDK for self-hosted support
try:
    from firecrawl import FirecrawlApp
    FIRECRAWL_SDK_AVAILABLE = True
except ImportError:
    FIRECRAWL_SDK_AVAILABLE = False
    # Log warning will be handled when the SDK is actually needed


class FirecrawlSearchWrapper(BaseTool):
    """Wrapper tool for FirecrawlSearchTool that normalizes input format for Ollama compatibility."""

    name: str = "Firecrawl web search tool"
    description: str = (
        "Use Firecrawl's web search and crawl capabilities. "
        "Provide a plain text query string; returns structured crawl results. "
        "Automatically filters out paywalled or problematic URLs."
    )
    args_schema: Type[BaseModel] = FirecrawlSearchWrapperInput

    def __init__(self, firecrawl_tool: FirecrawlSearchTool):
        super().__init__()
        object.__setattr__(self, "_firecrawl_tool", firecrawl_tool)

    def _run(self, query: Union[str, dict]) -> str:
        normalized_query = FirecrawlSearchWrapperInput(query=query).query
        try:
            result = self._firecrawl_tool._run(query=normalized_query)
            # Parse and filter if it's a JSON string
            try:
                result_dict = json.loads(result) if isinstance(result, str) else result
                if isinstance(result_dict, dict):
                    # Apply filtering for cloud Firecrawl results too
                    filtered = filter_problematic_urls(result_dict)
                    return json.dumps(filtered, indent=2)
            except (json.JSONDecodeError, AttributeError):
                pass  # Not JSON, return as-is
            return result
        except Exception as e:
            logger.error(f"Firecrawl search failed: {e}")
            return json.dumps({
                "error": f"Firecrawl search failed: {str(e)}",
                "query": normalized_query,
                "suggestion": "Try rephrasing the query or check Firecrawl service status"
            }, indent=2)


class SelfHostedFirecrawlSearchTool(BaseTool):
    """Self-hosted Firecrawl search tool that supports custom base URLs."""

    name: str = "Firecrawl web search tool (self-hosted)"
    description: str = (
        "Use self-hosted Firecrawl's web search and crawl capabilities. "
        "Provide a plain text query string; returns structured crawl results."
    )
    args_schema: Type[BaseModel] = FirecrawlSearchWrapperInput

    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        max_pages: int = 3,
        max_results: int = 5,
        timeout: int = 20,  # Reduced to 20 seconds for faster failure on paywalled content
    ):
        super().__init__()
        if not FIRECRAWL_SDK_AVAILABLE:
            raise ImportError(
                "firecrawl-py SDK is required for self-hosted Firecrawl. "
                "Install with: pip install firecrawl-py"
            )
        
        object.__setattr__(self, "_base_url", base_url.rstrip("/"))
        object.__setattr__(self, "_api_key", api_key)
        object.__setattr__(self, "_max_pages", max_pages)
        object.__setattr__(self, "_max_results", max_results)
        object.__setattr__(self, "_timeout", timeout)
        
        # Initialize Firecrawl client with custom base URL
        # The firecrawl-py SDK supports base_url parameter
        try:
            client = FirecrawlApp(
                api_key=api_key or "dummy",  # API key may be optional for self-hosted
                base_url=base_url,
            )
            object.__setattr__(self, "_client", client)
        except Exception as e:
            logger.warning(
                "Failed to initialize Firecrawl client with SDK, will use direct HTTP: %s",
                e
            )
            object.__setattr__(self, "_client", None)

    def _run(self, query: Union[str, dict]) -> str:
        """Run search using self-hosted Firecrawl."""
        normalized_query = FirecrawlSearchWrapperInput(query=query).query
        
        # Try using SDK first
        if self._client:
            try:
                result = self._client.search(
                    query=normalized_query,
                    pageOptions={
                        "maxResults": self._max_results,
                        # Timeout settings (in milliseconds) - lower values skip paywalled content faster
                        "timeout": 15000,  # 15 seconds - very aggressive timeout to prevent loops
                        "waitFor": 1000,  # Wait 1 second for content to load
                        # Exclude problematic domains from search results
                        "excludeDomains": [
                            "researchgate.net", "jstor.org", "sciencedirect.com",
                            "ieee.org", "acm.org", "springer.com", "nature.com",
                            "elsevier.com", "wiley.com", "tandfonline.com",
                            "sagepub.com", "oup.com", "cambridge.org",
                            "academia.edu", "semanticscholar.org"
                        ],
                        # Skip PDF engine for HTML pages - prevents unnecessary PDF attempts
                        "onlyMainContent": True,  # Focus on main content, skip PDF parsing
                        "formats": ["markdown"],  # Only extract these formats, skip PDF
                    },
                )
                # Filter out problematic URLs from results
                filtered_result = filter_problematic_urls(result)
                return json.dumps(filtered_result, indent=2)
            except Exception as e:
                logger.warning("Firecrawl SDK search failed, trying direct HTTP: %s", e)
        
        # Fallback to direct HTTP API calls
        return self._run_http(normalized_query)
    
    def _run_http(self, query: str) -> str:
        """Fallback HTTP implementation for self-hosted Firecrawl."""
        try:
            # Firecrawl search endpoint
            search_url = f"{self._base_url}/v0/search"
            headers = {"Content-Type": "application/json"}
            if self._api_key:
                headers["Authorization"] = f"Bearer {self._api_key}"
            
            payload = {
                "query": query,
                "pageOptions": {
                    "maxResults": self._max_results,
                    # Timeout settings (in milliseconds) - lower values skip paywalled content faster
                    "timeout": 15000,  # 15 seconds - very aggressive timeout to prevent loops
                    "waitFor": 1000,  # Wait 1 second for content to load
                    # Exclude problematic domains from search results
                    "excludeDomains": [
                        "researchgate.net", "jstor.org", "sciencedirect.com",
                        "ieee.org", "acm.org", "springer.com", "nature.com",
                        "elsevier.com", "wiley.com", "tandfonline.com",
                        "sagepub.com", "oup.com", "cambridge.org",
                        "academia.edu", "semanticscholar.org"
                    ],
                    # Skip PDF engine for HTML pages - prevents unnecessary PDF attempts
                    "onlyMainContent": True,  # Focus on main content, skip PDF parsing
                    "formats": ["markdown"],  # Only extract these formats, skip PDF
                },
            }
            
            response = requests.post(
                search_url,
                json=payload,
                headers=headers,
                timeout=self._timeout,
            )
            
            if response.status_code == 200:
                result = response.json()
                # Filter out problematic URLs
                filtered_result = filter_problematic_urls(result)
                return json.dumps(filtered_result, indent=2)
            else:
                error_msg = f"Firecrawl API error {response.status_code}: {response.text[:500]}"
                logger.error(error_msg)
                return json.dumps(
                    {
                        "error": error_msg,
                        "query": query,
                        "status_code": response.status_code,
                    },
                    indent=2,
                )
        except requests.exceptions.RequestException as e:
            logger.error("Firecrawl HTTP request failed: %s", e)
            return json.dumps(
                {
                    "error": f"Firecrawl request failed: {str(e)}",
                    "query": query,
                },
                indent=2,
            )

