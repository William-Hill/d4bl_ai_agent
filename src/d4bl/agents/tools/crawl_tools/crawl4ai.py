"""
Crawl4AI search tool for web crawling and search.
"""
from __future__ import annotations

import json
import os
import re
import logging
import time
from typing import List, Type, Optional

import requests
from crewai.tools import BaseTool
from crewai_tools import FirecrawlSearchTool
from pydantic import BaseModel, Field, field_validator

from d4bl.agents.tools.crawl_tools.pdf_extraction import (
    PDF_EXTRACTION_AVAILABLE,
    extract_pdf_client_side,
    is_valid_content,
)
from d4bl.agents.tools.crawl_tools.firecrawl import (
    FIRECRAWL_SDK_AVAILABLE,
    SelfHostedFirecrawlSearchTool,
)

logger = logging.getLogger(__name__)


class Crawl4AISearchTool(BaseTool):
    """Simple HTTP wrapper for a self-hosted Crawl4AI service."""

    name: str = "Crawl4AI web search tool"
    description: str = (
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
            payload = {"q": query, "num": 8}

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
            logger.info("Serper.dev results: %s", json.dumps(results, indent=2))

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

    def _filter_valid_results(self, results: List[dict]) -> tuple[List[dict], List[dict]]:
        """Filter crawl results into valid and invalid groups."""
        valid_results = []
        invalid_results = []
        
        for result in results:
            url = result.get("url", "")
            is_pdf = url.lower().endswith('.pdf') if url else False
            
            if is_valid_content(result):
                valid_results.append(result)
            else:
                # For PDFs with no content, try client-side extraction as fallback
                if is_pdf and PDF_EXTRACTION_AVAILABLE:
                    logger.info("PDF extraction failed via API, trying client-side extraction: %s", url)
                    client_extracted = extract_pdf_client_side(url, timeout=self._timeout)
                    if client_extracted and is_valid_content(client_extracted):
                        valid_results.append(client_extracted)
                        logger.info("Client-side PDF extraction succeeded for: %s", url)
                        continue
                
                invalid_results.append(result)
                logger.warning(
                    "Filtered out crawl result with insufficient content: %s",
                    url
                )
        
        return valid_results, invalid_results

    def _handle_pdfs_separately(self, pdf_urls: List[str], query: str) -> List[dict]:
        """
        Handle PDF URLs separately with optimized extraction.
        Returns list of extracted PDF results.
        """
        pdf_results = []
        
        for pdf_url in pdf_urls:
            logger.info("Processing PDF separately: %s", pdf_url)
            
            # Try client-side extraction first (more reliable)
            if PDF_EXTRACTION_AVAILABLE:
                extracted = extract_pdf_client_side(pdf_url, timeout=self._timeout)
                if extracted:
                    pdf_results.append(extracted)
                    continue
            
            # Fallback: Try via Crawl4AI API with PDF-specific config
            try:
                endpoint = f"{self._base_url}/crawl"
                headers = {"Content-Type": "application/json"}
                if self._api_key:
                    headers["Authorization"] = f"Bearer {self._api_key}"
                
                pdf_payload = {
                    "urls": [pdf_url],
                    "crawler_strategy": "PDFCrawlerStrategy",
                    "scraping_strategy": "PDFContentScrapingStrategy",
                    "extract_pdf": True,
                    "extract_text": True,
                    "extract_metadata": True,
                }
                
                resp = requests.post(
                    endpoint,
                    json=pdf_payload,
                    headers=headers,
                    timeout=self._timeout * 2,  # PDFs may take longer
                )
                
                if resp.status_code == 200:
                    crawl_result = resp.json()
                    results = crawl_result.get("results", [])
                    if results:
                        pdf_results.extend(results)
                else:
                    logger.warning(
                        "Crawl4AI API returned %s for PDF %s",
                        resp.status_code,
                        pdf_url
                    )
            except Exception as e:
                logger.warning("Error processing PDF via API: %s", e)
        
        return pdf_results

    def _crawl_urls_with_retry(self, urls: List[str], query: str) -> str:
        """Crawl URLs with retry logic and error recovery."""
        endpoint = f"{self._base_url}/crawl"
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        max_retries = 3
        last_error = None

        # Initialize PDF results list outside the retry loop
        client_extracted_pdfs = []
        
        for attempt in range(max_retries):
            try:
                # Separate PDFs from regular URLs for better handling
                pdf_urls = [url for url in urls if url.lower().endswith('.pdf')]
                regular_urls = [url for url in urls if not url.lower().endswith('.pdf')]
                
                # Build crawl payload with PDF-specific configuration
                crawl_payload = {"urls": urls}
                
                # If PDFs are present, try client-side extraction first (more reliable)
                # Only do this on first attempt to avoid re-extracting
                if pdf_urls and attempt == 0:
                    logger.info(
                        "PDFs detected (%s PDFs, %s regular URLs), attempting extraction",
                        len(pdf_urls),
                        len(regular_urls)
                    )
                    # Try client-side extraction for PDFs first
                    remaining_pdf_urls = []
                    for pdf_url in pdf_urls:
                        if PDF_EXTRACTION_AVAILABLE:
                            extracted = extract_pdf_client_side(pdf_url, timeout=self._timeout)
                            if extracted and is_valid_content(extracted):
                                client_extracted_pdfs.append(extracted)
                                logger.info("Successfully extracted PDF client-side: %s", pdf_url)
                            else:
                                remaining_pdf_urls.append(pdf_url)
                                logger.warning("Client-side PDF extraction failed for: %s", pdf_url)
                        else:
                            remaining_pdf_urls.append(pdf_url)
                    
                    # If we successfully extracted some PDFs, use those and only crawl remaining ones
                    if client_extracted_pdfs:
                        logger.info("Extracted %s PDFs client-side, %s remaining for API", len(client_extracted_pdfs), len(remaining_pdf_urls))
                        # Update URLs to only include remaining PDFs + regular URLs
                        urls = remaining_pdf_urls + regular_urls
                        crawl_payload["urls"] = urls
                    
                    # Configure API extraction for any remaining PDFs
                    if remaining_pdf_urls:
                        # Try multiple parameter formats for compatibility
                        crawl_payload["crawler_strategy"] = "PDFCrawlerStrategy"
                        crawl_payload["scraping_strategy"] = "PDFContentScrapingStrategy"
                        # Alternative parameter names (for different API versions)
                        crawl_payload["extraction_strategy"] = "pdf"
                        crawl_payload["extract_pdf"] = True
                        crawl_payload["pdf_extraction"] = True
                        # Enable text extraction from PDFs
                        crawl_payload["extract_text"] = True
                        crawl_payload["extract_metadata"] = True
                
                resp = requests.post(
                    endpoint,
                    json=crawl_payload,
                    headers=headers,
                    timeout=self._timeout,
                )

                if resp.status_code == 200:
                    crawl_results = resp.json()
                    raw_results = crawl_results.get("results", [])
                    
                    # Merge any client-side extracted PDFs from earlier
                    if client_extracted_pdfs:
                        raw_results.extend(client_extracted_pdfs)
                    
                    # If we still have PDFs that failed, try separate handling
                    pdf_urls_in_results = [r.get("url", "") for r in raw_results if r.get("url", "").lower().endswith('.pdf')]
                    failed_pdf_urls = [url for url in urls if url.lower().endswith('.pdf') and url not in pdf_urls_in_results]
                    if failed_pdf_urls:
                        logger.info("Some PDFs failed API extraction, trying separate handling: %s", failed_pdf_urls)
                        additional_pdf_results = self._handle_pdfs_separately(failed_pdf_urls, query)
                        if additional_pdf_results:
                            raw_results.extend(additional_pdf_results)
                            logger.info("Merged %s additional client-extracted PDFs", len(additional_pdf_results))
                    
                    # Filter out results with no valid content
                    valid_results, invalid_results = self._filter_valid_results(raw_results)
                    
                    if not valid_results and raw_results:
                        logger.warning(
                            "All %s crawl results were filtered out due to insufficient content. "
                            "This may indicate extraction issues.",
                            len(raw_results)
                        )
                        # Log details about why results were filtered
                        for invalid in invalid_results[:3]:  # Log first 3
                            url = invalid.get("url", "unknown")
                            has_extracted = bool(invalid.get("extracted_content"))
                            has_html = bool(invalid.get("html") or invalid.get("cleaned_html"))
                            logger.debug(
                                "  - %s: extracted_content=%s, has_html=%s",
                                url, has_extracted, has_html
                            )
                    
                    # Extract source URLs from valid results for later use
                    source_urls = [r.get("url", "") for r in valid_results if r.get("url")]
                    
                    formatted_results = {
                        "query": query,
                        "urls_crawled": urls,
                        "results": valid_results,
                        "results_filtered": len(invalid_results),
                        "source_urls": source_urls,  # Include source URLs for evaluation
                        "success": crawl_results.get("success", False) and len(valid_results) > 0,
                    }
                    
                    logger.info(
                        "Successfully crawled %s URLs on attempt %s (%s valid, %s filtered)",
                        len(urls),
                        attempt + 1,
                        len(valid_results),
                        len(invalid_results),
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
                    time.sleep(wait_time)
                    continue
                return self._try_firecrawl_fallback(query, urls, str(e))

            except requests.exceptions.Timeout as e:
                last_error = e
                logger.warning("Crawl4AI timeout on attempt %s/%s", attempt + 1, max_retries)
                if attempt < max_retries - 1:
                    time.sleep((attempt + 1) * 2)
                    continue
                return self._try_firecrawl_fallback(query, urls, f"Timeout: {str(e)}")

            except Exception as e:  # pragma: no cover - defensive
                last_error = e
                logger.error("Unexpected error crawling URLs: %s", str(e), exc_info=True)
                if attempt < max_retries - 1:
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
            firecrawl_base_url = os.getenv("FIRECRAWL_BASE_URL")
            
            # Check if self-hosted or cloud Firecrawl is configured
            if not firecrawl_base_url and not firecrawl_api_key:
                logger.warning("Firecrawl not configured for fallback")
                return json.dumps(
                    {
                        "error": f"Crawl4AI failed: {error}",
                        "query": query,
                        "urls": urls,
                        "fallback": "Firecrawl not configured (set FIRECRAWL_API_KEY or FIRECRAWL_BASE_URL)",
                    },
                    indent=2,
                )

            logger.info("Attempting Firecrawl fallback...")
            
            # Use self-hosted if base URL is set, otherwise use cloud
            if firecrawl_base_url:
                logger.info("Using self-hosted Firecrawl for fallback: %s", firecrawl_base_url)
                if not FIRECRAWL_SDK_AVAILABLE:
                    logger.warning("firecrawl-py SDK not available, using direct HTTP")
                    # Use direct HTTP call
                    try:
                        search_url = f"{firecrawl_base_url.rstrip('/')}/v0/search"
                        headers = {"Content-Type": "application/json"}
                        if firecrawl_api_key:
                            headers["Authorization"] = f"Bearer {firecrawl_api_key}"
                        
                        payload = {"query": query, "pageOptions": {"maxResults": 5}}
                        response = requests.post(search_url, json=payload, headers=headers, timeout=60)
                        
                        if response.status_code == 200:
                            result = response.json()
                            logger.info("Self-hosted Firecrawl fallback succeeded")
                            return json.dumps(
                                {
                                    "query": query,
                                    "urls_attempted": urls,
                                    "fallback_used": "Firecrawl (self-hosted)",
                                    "original_error": error,
                                    "results": result,
                                },
                                indent=2,
                            )
                    except Exception as http_error:
                        logger.error("Self-hosted Firecrawl HTTP fallback failed: %s", http_error)
                else:
                    # Use SDK
                    firecrawl_tool = SelfHostedFirecrawlSearchTool(
                        base_url=firecrawl_base_url,
                        api_key=firecrawl_api_key,
                    )
                    result = firecrawl_tool._run(query=query)
                    logger.info("Self-hosted Firecrawl fallback succeeded")
                    return json.dumps(
                        {
                            "query": query,
                            "urls_attempted": urls,
                            "fallback_used": "Firecrawl (self-hosted)",
                            "original_error": error,
                            "results": result,
                        },
                        indent=2,
                    )
            else:
                # Use cloud Firecrawl
                firecrawl_tool = FirecrawlSearchTool(api_key=firecrawl_api_key)
                result = firecrawl_tool._run(query=query)
                logger.info("Firecrawl (cloud) fallback succeeded")
                return json.dumps(
                    {
                        "query": query,
                        "urls_attempted": urls,
                        "fallback_used": "Firecrawl (cloud)",
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

