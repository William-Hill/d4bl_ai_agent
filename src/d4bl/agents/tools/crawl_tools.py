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
import tempfile
from typing import List, Type, Union, Optional

import requests
from crewai.tools import BaseTool
from crewai_tools import FirecrawlSearchTool
from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)

# Try to import firecrawl-py SDK for self-hosted support
try:
    from firecrawl import FirecrawlApp
    FIRECRAWL_SDK_AVAILABLE = True
except ImportError:
    FIRECRAWL_SDK_AVAILABLE = False
    # Log warning will be handled when the SDK is actually needed

# Try to import PDF extraction library for fallback
try:
    from pypdf import PdfReader
    PDF_EXTRACTION_AVAILABLE = True
except ImportError:
    try:
        from PyPDF2 import PdfReader
        PDF_EXTRACTION_AVAILABLE = True
    except ImportError:
        PDF_EXTRACTION_AVAILABLE = False
        logger.warning(
            "PDF extraction libraries (pypdf or PyPDF2) not available. "
            "Install pypdf for client-side PDF extraction fallback."
        )


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


def _filter_problematic_urls(result: dict) -> dict:
    """Filter out URLs that are likely paywalled, require auth, or timed out.
    
    This is a shared helper function used by both FirecrawlSearchWrapper
    and SelfHostedFirecrawlSearchTool to filter problematic URLs.
    """
    if not isinstance(result, dict):
        return result
    
    # Known problematic domains (paywalled, require auth, etc.)
    problematic_domains = {
        'jstor.org', 'sciencedirect.com', 'ieee.org', 'acm.org',
        'springer.com', 'nature.com', 'elsevier.com', 'wiley.com',
        'tandfonline.com', 'sagepub.com', 'oup.com', 'cambridge.org',
        'pubmed.ncbi.nlm.nih.gov', 'arxiv.org/pdf', 'researchgate.net',
        'academia.edu', 'semanticscholar.org'
    }
    
    # Filter data array if present
    if 'data' in result and isinstance(result['data'], list):
        original_count = len(result['data'])
        filtered_data = []
        for item in result['data']:
            if isinstance(item, dict):
                url = item.get('url', '') or item.get('link', '') or item.get('source', '')
                # Skip if URL is from problematic domain
                if url and any(domain in url.lower() for domain in problematic_domains):
                    logger.info(f"Skipping paywalled/problematic URL: {url}")
                    continue
                # Skip if there's an error or timeout
                error_msg = item.get('error', '') or item.get('errorMessage', '') or ''
                if error_msg or 'timeout' in str(error_msg).lower() or 'timed out' in str(error_msg).lower():
                    logger.info(f"Skipping failed URL (error/timeout): {url}")
                    continue
                # Skip if content is empty or too short (likely failed scrape)
                content = item.get('content', '') or item.get('markdown', '') or item.get('text', '') or item.get('description', '')
                if not content or len(str(content).strip()) < 50:
                    logger.info(f"Skipping URL with insufficient content: {url}")
                    continue
            filtered_data.append(item)
        result['data'] = filtered_data
        if original_count > len(filtered_data):
            result['filtered_count'] = original_count - len(filtered_data)
            logger.info(f"Filtered {result['filtered_count']} problematic URLs from {original_count} results")
    
    return result


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
                    filtered = _filter_problematic_urls(result_dict)
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
                filtered_result = _filter_problematic_urls(result)
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
                filtered_result = _filter_problematic_urls(result)
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
            logger.info("Serper.dev results: %s", urls)
            logger.info("Serper.dev results: %s", urls[:3])
            logger.info("Serper.dev results: %s", urls[:2])
            logger.info("Serper.dev results: %s", urls[:1])
            logger.info("Serper.dev results: %s", urls[0])
            logger.info("Serper.dev results: %s", urls[1])
            logger.info("Serper.dev results: %s", urls[2])
            logger.info("Serper.dev results: %s", urls[3])
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

    def _is_valid_content(self, result: dict) -> bool:
        """Check if a crawl result has valid, extractable content."""
        # Check for extracted content
        extracted = result.get("extracted_content", "")
        if extracted and len(str(extracted).strip()) > 50:
            return True
        
        # Check for cleaned HTML (must have actual content, not just structure)
        cleaned_html = result.get("cleaned_html", "")
        if cleaned_html:
            # Remove HTML tags and check text length
            import re
            text_content = re.sub(r'<[^>]+>', '', str(cleaned_html))
            if len(text_content.strip()) > 50:
                return True
        
        # Check for raw HTML (must have substantial text content)
        html = result.get("html", "")
        if html:
            import re
            text_content = re.sub(r'<[^>]+>', '', str(html))
            # Filter out common empty HTML patterns
            empty_patterns = [
                r'^<html></html>$',
                r'^<html><head></head><body></body></html>$',
                r'^<html><body[^>]*></body></html>$',
            ]
            for pattern in empty_patterns:
                if re.match(pattern, str(html).strip(), re.IGNORECASE):
                    return False
            if len(text_content.strip()) > 50:
                return True
        
        # PDF files might have null extracted_content but should be flagged
        url = result.get("url", "")
        if url and url.lower().endswith('.pdf'):
            logger.warning(
                "PDF file %s has no extracted content. PDF extraction may have failed.",
                url
            )
        
        return False

    def _extract_pdf_client_side(self, url: str) -> Optional[dict]:
        """
        Fallback: Extract PDF content client-side if Crawl4AI fails.
        Downloads the PDF and extracts text using pypdf.
        """
        if not PDF_EXTRACTION_AVAILABLE:
            logger.warning("PDF extraction library not available, skipping client-side extraction")
            return None
        
        try:
            logger.info("Attempting client-side PDF extraction for: %s", url)
            
            # Download PDF with proper headers to handle various servers
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'application/pdf,application/octet-stream,*/*',
            }
            
            # Download PDF with redirect handling
            response = requests.get(
                url, 
                timeout=self._timeout * 2,  # PDFs may take longer
                stream=True,
                headers=headers,
                allow_redirects=True
            )
            response.raise_for_status()
            
            # Check content type
            content_type = response.headers.get('Content-Type', '').lower()
            if 'pdf' not in content_type and not url.lower().endswith('.pdf'):
                logger.warning("URL does not appear to be a PDF (Content-Type: %s)", content_type)
                # Continue anyway, might still be a PDF
            
            # Save to temporary file
            with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
                tmp_file.write(response.content)
                tmp_path = tmp_file.name
            
            try:
                # Extract text from PDF
                reader = PdfReader(tmp_path)
                text_content = []
                metadata = {}
                
                # Extract metadata if available
                if reader.metadata:
                    metadata = {
                        "title": reader.metadata.get("/Title", ""),
                        "author": reader.metadata.get("/Author", ""),
                        "subject": reader.metadata.get("/Subject", ""),
                        "creator": reader.metadata.get("/Creator", ""),
                    }
                
                # Extract text from all pages
                for page_num, page in enumerate(reader.pages, start=1):
                    try:
                        page_text = page.extract_text()
                        if page_text and page_text.strip():
                            text_content.append(f"--- Page {page_num} ---\n{page_text}")
                    except Exception as page_error:
                        logger.warning("Error extracting text from page %s: %s", page_num, page_error)
                        continue
                
                extracted_text = "\n\n".join(text_content)
                
                if not extracted_text or len(extracted_text.strip()) < 50:
                    logger.warning("PDF extraction produced minimal content (%s chars)", len(extracted_text))
                    return None
                
                logger.info(
                    "Successfully extracted %s characters from PDF (%s pages)",
                    len(extracted_text),
                    len(reader.pages)
                )
                
                # Return in Crawl4AI-compatible format
                return {
                    "url": url,
                    "extracted_content": extracted_text,
                    "cleaned_html": f"<html><body><pre>{extracted_text[:1000]}...</pre></body></html>",
                    "html": f"<html><body><pre>{extracted_text[:1000]}...</pre></body></html>",
                    "metadata": metadata,
                    "success": True,
                    "extraction_method": "client_side_pypdf",
                    "page_count": len(reader.pages),
                }
            
            finally:
                # Clean up temporary file
                try:
                    os.unlink(tmp_path)
                except Exception as cleanup_error:
                    logger.warning("Error cleaning up temp PDF file: %s", cleanup_error)
        
        except requests.exceptions.RequestException as e:
            logger.error("Failed to download PDF for client-side extraction: %s", e)
            logger.debug("PDF URL: %s, Error type: %s", url, type(e).__name__)
            return None
        except Exception as e:
            logger.error("Error during client-side PDF extraction: %s", e, exc_info=True)
            logger.debug("PDF URL: %s, Error details: %s", url, str(e))
            return None

    def _filter_valid_results(self, results: List[dict]) -> tuple[List[dict], List[dict]]:
        """Filter crawl results into valid and invalid groups."""
        valid_results = []
        invalid_results = []
        
        for result in results:
            url = result.get("url", "")
            is_pdf = url.lower().endswith('.pdf') if url else False
            
            if self._is_valid_content(result):
                valid_results.append(result)
            else:
                # For PDFs with no content, try client-side extraction as fallback
                if is_pdf and PDF_EXTRACTION_AVAILABLE:
                    logger.info("PDF extraction failed via API, trying client-side extraction: %s", url)
                    client_extracted = self._extract_pdf_client_side(url)
                    if client_extracted and self._is_valid_content(client_extracted):
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
                extracted = self._extract_pdf_client_side(pdf_url)
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
                            extracted = self._extract_pdf_client_side(pdf_url)
                            if extracted and self._is_valid_content(extracted):
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

