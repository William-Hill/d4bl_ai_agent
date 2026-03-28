# Sprint 2: Self-Hosted Search & Scrape Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Firecrawl + Serper with free self-hosted SearXNG + Crawl4AI. Build a content extraction library and three new ingestion scripts (RSS feeds, web scraping, news search). Add three new data source scripts. Remove Firecrawl entirely.

**Architecture:** SearXNG provides web search (replaces Serper). Crawl4AI provides JS rendering (replaces Firecrawl). A new `content_extractor` library provides tiered extraction: trafilatura for static HTML, Crawl4AI for JS pages, pypdf for PDFs. New ingestion scripts for RSS, web scraping, and news search use this library and plug into the existing `SCRIPT_REGISTRY` + APScheduler framework from Sprint 1.

**Tech Stack:** SearXNG (Docker), trafilatura, Crawl4AI, httpx, xml.etree.ElementTree

**Spec:** `docs/superpowers/specs/2026-03-27-self-hosted-scraping-pipeline-design.md` (Sprint 2 section)

**Prerequisite:** Sprint 1 (Dagster removal + scheduling) must be completed first.

---

## File Structure

**Create:**
- `docker-compose.searxng.yml` — SearXNG Docker overlay
- `searxng/settings.yml` — SearXNG engine configuration
- `src/d4bl/agents/tools/crawl_tools/searxng.py` — SearXNG search tool for CrewAI
- `scripts/ingestion/lib/__init__.py` — Shared library package
- `scripts/ingestion/lib/content_extractor.py` — Tiered content extraction
- `scripts/ingestion/ingest_rss_feeds.py` — RSS/Atom feed ingestion
- `scripts/ingestion/ingest_web_sources.py` — Web page scraping
- `scripts/ingestion/ingest_news_search.py` — SearXNG-powered news discovery
- `scripts/ingestion/ingest_county_health_rankings.py` — County Health Rankings data
- `scripts/ingestion/ingest_usaspending.py` — USASpending.gov federal spending
- `scripts/ingestion/ingest_vera_incarceration.py` — Vera Institute incarceration data
- `tests/test_content_extractor.py` — Content extractor tests
- `tests/test_searxng_tool.py` — SearXNG tool tests
- `tests/test_ingest_rss.py` — RSS ingestion tests
- `tests/test_ingest_news.py` — News search tests

**Modify:**
- `src/d4bl/settings.py` — Add `searxng_base_url`, `search_provider`; remove Firecrawl settings
- `src/d4bl/agents/crew.py` — Replace Firecrawl with SearXNG + Crawl4AI
- `src/d4bl/services/ingestion_runner.py` — Add new sources to `SCRIPT_REGISTRY`
- `docker-compose.base.yml` — Update env vars (remove Firecrawl, add SearXNG)
- `pyproject.toml` — Add `trafilatura`, remove `firecrawl-py`
- `CLAUDE.md` — Update crawl docs

**Delete:**
- `docker-compose.firecrawl.yml`
- `src/d4bl/agents/tools/crawl_tools/firecrawl.py`

---

### Task 1: Add SearXNG Docker Compose and Configuration

**Files:**
- Create: `docker-compose.searxng.yml`
- Create: `searxng/settings.yml`

- [ ] **Step 1: Create SearXNG settings file**

```bash
mkdir -p searxng
```

Create `searxng/settings.yml`:

```yaml
use_default_settings: true

general:
  instance_name: "D4BL Search"
  debug: false

search:
  safe_search: 0
  default_lang: "en"
  formats:
    - html
    - json

server:
  port: 8080
  bind_address: "0.0.0.0"
  secret_key: "d4bl-searxng-secret-change-in-prod"

engines:
  - name: google
    engine: google
    shortcut: g
    disabled: false

  - name: bing
    engine: bing
    shortcut: b
    disabled: false

  - name: duckduckgo
    engine: duckduckgo
    shortcut: ddg
    disabled: false

  - name: wikipedia
    engine: wikipedia
    shortcut: wp
    disabled: false

  - name: arxiv
    engine: arxiv
    shortcut: ar
    disabled: false
    categories: science

  - name: google news
    engine: google_news
    shortcut: gn
    disabled: false
    categories: news

  - name: bing news
    engine: bing_news
    shortcut: bn
    disabled: false
    categories: news

outgoing:
  request_timeout: 10
  max_request_timeout: 15
```

- [ ] **Step 2: Create Docker Compose overlay**

Create `docker-compose.searxng.yml`:

```yaml
services:
  searxng:
    image: searxng/searxng:latest
    container_name: d4bl-searxng
    ports:
      - "8080:8080"
    volumes:
      - ./searxng/settings.yml:/etc/searxng/settings.yml:ro
    environment:
      - SEARXNG_BASE_URL=http://localhost:8080
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "wget", "--spider", "-q", "http://localhost:8080/healthz"]
      interval: 30s
      timeout: 10s
      retries: 3
    networks:
      - default
```

- [ ] **Step 3: Verify compose file is valid**

```bash
docker compose -f docker-compose.searxng.yml config --quiet && echo "Valid" || echo "Invalid"
```

Expected: `Valid`

- [ ] **Step 4: Commit**

```bash
git add docker-compose.searxng.yml searxng/settings.yml
git commit -m "feat: add SearXNG Docker compose and configuration

Self-hosted meta-search engine replacing Serper. Configured with
Google, Bing, DuckDuckGo, Wikipedia, arXiv, and news engines."
```

---

### Task 2: Add trafilatura Dependency and Content Extractor Library

**Files:**
- Create: `scripts/ingestion/lib/__init__.py`
- Create: `scripts/ingestion/lib/content_extractor.py`
- Test: `tests/test_content_extractor.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: Add trafilatura dependency**

In `pyproject.toml`, add to the `dependencies` list:

```
"trafilatura>=1.6",
```

Install:

```bash
pip install -e ".[dev]"
```

- [ ] **Step 2: Write the failing tests**

Create `tests/test_content_extractor.py`:

```python
"""Tests for the content extraction library."""

import pytest
from unittest.mock import patch, MagicMock
from scripts.ingestion.lib.content_extractor import (
    ExtractedContent,
    extract_from_html,
    detect_content_type,
    extract,
)


def test_extracted_content_dataclass():
    """ExtractedContent has expected fields."""
    content = ExtractedContent(
        url="https://example.com",
        title="Test",
        author="Author",
        date="2026-01-01",
        text="Hello world",
        source_type="html",
        metadata={},
    )
    assert content.url == "https://example.com"
    assert content.text == "Hello world"
    assert content.source_type == "html"


def test_detect_content_type_pdf():
    """PDF URLs detected correctly."""
    assert detect_content_type("https://example.com/report.pdf") == "pdf"
    assert detect_content_type("https://example.com/report.PDF") == "pdf"


def test_detect_content_type_rss():
    """RSS URLs detected by common patterns."""
    assert detect_content_type("https://example.com/feed.xml") == "rss"
    assert detect_content_type("https://example.com/rss") == "rss"
    assert detect_content_type("https://example.com/atom.xml") == "rss"


def test_detect_content_type_html_default():
    """Default content type is html."""
    assert detect_content_type("https://example.com/article") == "html"
    assert detect_content_type("https://example.com/page.html") == "html"


def test_extract_from_html_with_trafilatura():
    """extract_from_html uses trafilatura for text extraction."""
    sample_html = """
    <html>
    <head><title>Test Article</title></head>
    <body>
    <nav>Navigation</nav>
    <article>
    <h1>Test Article</h1>
    <p>This is the main content of the article that should be extracted.</p>
    <p>It has multiple paragraphs with enough text for trafilatura to work.</p>
    </article>
    <footer>Footer content</footer>
    </body>
    </html>
    """
    result = extract_from_html(sample_html, "https://example.com/article")
    assert result is not None
    assert isinstance(result, ExtractedContent)
    assert result.source_type == "html"
    # trafilatura should extract article content, not nav/footer
    assert "main content" in result.text.lower() or len(result.text) > 0


def test_extract_from_html_empty_returns_none():
    """extract_from_html returns None for empty/minimal HTML."""
    result = extract_from_html("<html><body></body></html>", "https://example.com")
    assert result is None


@patch("scripts.ingestion.lib.content_extractor.httpx")
def test_extract_fetches_url(mock_httpx):
    """extract() fetches the URL and processes the response."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.headers = {"content-type": "text/html"}
    mock_response.text = """
    <html><body>
    <article><p>This is substantial content for testing the extraction pipeline.</p>
    <p>We need enough text here for trafilatura to consider it worth extracting.</p>
    </article></body></html>
    """
    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.get.return_value = mock_response
    mock_httpx.Client.return_value = mock_client

    result = extract("https://example.com/article")
    assert result is not None
    assert result.url == "https://example.com/article"
    mock_client.get.assert_called_once()
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
python -m pytest tests/test_content_extractor.py -v
```

Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 4: Create the lib package**

Create `scripts/ingestion/lib/__init__.py`:

```python
"""Shared libraries for ingestion scripts."""
```

- [ ] **Step 5: Create the content extractor**

Create `scripts/ingestion/lib/content_extractor.py`:

```python
"""Tiered content extraction library.

Extracts clean text from URLs using the best strategy for each content type:
1. RSS/Atom feeds → XML parsing
2. PDFs → pypdf extraction
3. Static HTML → trafilatura (boilerplate removal + metadata)
4. JS-rendered pages → Crawl4AI fallback
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

import httpx
import trafilatura

logger = logging.getLogger(__name__)

_PDF_PATTERN = re.compile(r"\.pdf$", re.IGNORECASE)
_RSS_PATTERNS = re.compile(
    r"(feed\.xml|/feed/?$|/rss/?$|atom\.xml|/atom/?$|\.rss$)", re.IGNORECASE
)


@dataclass
class ExtractedContent:
    """Result of content extraction from a URL."""

    url: str
    title: str | None
    author: str | None
    date: str | None
    text: str
    source_type: str  # 'rss', 'pdf', 'html', 'js_rendered'
    metadata: dict = field(default_factory=dict)


def detect_content_type(url: str) -> str:
    """Detect likely content type from URL pattern.

    Returns: 'pdf', 'rss', or 'html'
    """
    if _PDF_PATTERN.search(url):
        return "pdf"
    if _RSS_PATTERNS.search(url):
        return "rss"
    return "html"


def extract_from_html(html: str, url: str) -> ExtractedContent | None:
    """Extract content from HTML using trafilatura.

    Returns None if trafilatura cannot extract meaningful content.
    """
    text = trafilatura.extract(
        html,
        url=url,
        include_comments=False,
        include_tables=True,
        favor_recall=True,
    )
    if not text or len(text.strip()) < 50:
        return None

    metadata = trafilatura.extract(
        html,
        url=url,
        output_format="json",
        include_comments=False,
    )
    # trafilatura.extract with json format returns a JSON string
    meta_dict = {}
    title = None
    author = None
    date = None
    if metadata:
        import json

        try:
            meta_dict = json.loads(metadata)
            title = meta_dict.get("title")
            author = meta_dict.get("author")
            date = meta_dict.get("date")
        except (json.JSONDecodeError, TypeError):
            pass

    return ExtractedContent(
        url=url,
        title=title,
        author=author,
        date=date,
        text=text,
        source_type="html",
        metadata=meta_dict,
    )


def extract_from_pdf(content: bytes, url: str) -> ExtractedContent | None:
    """Extract text from PDF bytes using pypdf."""
    try:
        from pypdf import PdfReader
        import io

        reader = PdfReader(io.BytesIO(content))
        pages_text = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                pages_text.append(text)

        full_text = "\n\n".join(pages_text)
        if len(full_text.strip()) < 50:
            return None

        return ExtractedContent(
            url=url,
            title=None,
            author=None,
            date=None,
            text=full_text,
            source_type="pdf",
            metadata={"page_count": len(reader.pages)},
        )
    except Exception:
        logger.exception("PDF extraction failed for %s", url)
        return None


def extract_from_crawl4ai(url: str, base_url: str = "http://crawl4ai:11235") -> ExtractedContent | None:
    """Fallback: use Crawl4AI for JS-rendered pages."""
    try:
        with httpx.Client(timeout=60) as client:
            response = client.post(
                f"{base_url}/crawl",
                json={
                    "urls": [url],
                    "priority": 5,
                },
            )
            if response.status_code != 200:
                logger.warning("Crawl4AI returned %d for %s", response.status_code, url)
                return None

            data = response.json()
            results = data.get("results", [])
            if not results:
                return None

            result = results[0]
            text = result.get("markdown") or result.get("cleaned_html") or ""
            if len(text.strip()) < 50:
                return None

            return ExtractedContent(
                url=url,
                title=result.get("metadata", {}).get("title"),
                author=None,
                date=None,
                text=text,
                source_type="js_rendered",
                metadata=result.get("metadata", {}),
            )
    except Exception:
        logger.exception("Crawl4AI extraction failed for %s", url)
        return None


def extract(
    url: str,
    force_js: bool = False,
    crawl4ai_base_url: str = "http://crawl4ai:11235",
) -> ExtractedContent | None:
    """Extract content from a URL using the best available strategy.

    Strategy:
    1. If force_js, skip to Crawl4AI
    2. Detect content type from URL
    3. For PDFs, download and extract with pypdf
    4. For HTML, try trafilatura first
    5. If trafilatura returns nothing, fall back to Crawl4AI

    Returns None if all strategies fail.
    """
    if force_js:
        return extract_from_crawl4ai(url, crawl4ai_base_url)

    content_type = detect_content_type(url)

    try:
        with httpx.Client(
            timeout=60,
            follow_redirects=True,
            headers={"User-Agent": "D4BL-Research-Agent/1.0"},
        ) as client:
            response = client.get(url)

            if response.status_code != 200:
                logger.warning("HTTP %d for %s", response.status_code, url)
                return None

            # Check response content-type header too
            resp_ct = response.headers.get("content-type", "")
            if "pdf" in resp_ct.lower() or content_type == "pdf":
                return extract_from_pdf(response.content, url)

            # Try trafilatura for HTML
            result = extract_from_html(response.text, url)
            if result:
                return result

            # Fallback to Crawl4AI for JS-rendered content
            logger.info("trafilatura returned nothing for %s, trying Crawl4AI", url)
            return extract_from_crawl4ai(url, crawl4ai_base_url)

    except httpx.HTTPError:
        logger.exception("HTTP error fetching %s", url)
        return None
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
python -m pytest tests/test_content_extractor.py -v
```

Expected: All tests PASS.

- [ ] **Step 7: Commit**

```bash
git add scripts/ingestion/lib/ tests/test_content_extractor.py pyproject.toml
git commit -m "feat: add tiered content extraction library

Shared extraction library with strategy: trafilatura for static HTML,
pypdf for PDFs, Crawl4AI fallback for JS-rendered pages. Includes
URL-based content type detection."
```

---

### Task 3: Create SearXNG Search Tool for CrewAI

**Files:**
- Create: `src/d4bl/agents/tools/crawl_tools/searxng.py`
- Test: `tests/test_searxng_tool.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_searxng_tool.py`:

```python
"""Tests for SearXNG search tool."""

import pytest
import json
from unittest.mock import patch, MagicMock
from d4bl.agents.tools.crawl_tools.searxng import SearXNGSearchTool


def test_searxng_tool_has_name():
    """Tool has expected name and description."""
    tool = SearXNGSearchTool(base_url="http://localhost:8080")
    assert "searxng" in tool.name.lower() or "search" in tool.name.lower()
    assert tool.description


def test_searxng_tool_default_category():
    """Default category is general."""
    tool = SearXNGSearchTool(base_url="http://localhost:8080")
    assert tool.default_category == "general"


def test_searxng_tool_custom_category():
    """Category can be set to news."""
    tool = SearXNGSearchTool(base_url="http://localhost:8080", default_category="news")
    assert tool.default_category == "news"


@patch("d4bl.agents.tools.crawl_tools.searxng.httpx")
def test_searxng_tool_run_returns_results(mock_httpx):
    """_run queries SearXNG and returns formatted results."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "results": [
            {
                "title": "Racial Equity Report",
                "url": "https://example.com/report",
                "content": "A report on racial equity in housing.",
            },
            {
                "title": "Justice Data",
                "url": "https://example.com/data",
                "content": "Criminal justice data by race.",
            },
        ]
    }
    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.get.return_value = mock_response
    mock_httpx.Client.return_value = mock_client

    tool = SearXNGSearchTool(base_url="http://localhost:8080")
    result = tool._run("racial equity housing")

    parsed = json.loads(result)
    assert len(parsed) == 2
    assert parsed[0]["title"] == "Racial Equity Report"
    assert parsed[0]["url"] == "https://example.com/report"

    # Verify correct URL called
    call_args = mock_client.get.call_args
    assert "search" in call_args[0][0]


@patch("d4bl.agents.tools.crawl_tools.searxng.httpx")
def test_searxng_tool_handles_error(mock_httpx):
    """_run returns error message on failure."""
    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.get.side_effect = Exception("Connection refused")
    mock_httpx.Client.return_value = mock_client

    tool = SearXNGSearchTool(base_url="http://localhost:8080")
    result = tool._run("test query")

    assert "error" in result.lower() or "failed" in result.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_searxng_tool.py -v
```

Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Create the SearXNG search tool**

Create `src/d4bl/agents/tools/crawl_tools/searxng.py`:

```python
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

from .utils import filter_problematic_urls

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

                # Filter problematic URLs
                filtered = []
                for r in results:
                    url = r.get("url", "")
                    if filter_problematic_urls([{"url": url}]):
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_searxng_tool.py -v
```

Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/d4bl/agents/tools/crawl_tools/searxng.py tests/test_searxng_tool.py
git commit -m "feat: add SearXNG search tool for CrewAI

Self-hosted meta-search tool replacing Serper.dev. Queries SearXNG
JSON API with category filtering and problematic URL filtering."
```

---

### Task 4: Update Settings and CrewAI to Use SearXNG

**Files:**
- Modify: `src/d4bl/settings.py`
- Modify: `src/d4bl/agents/crew.py`

- [ ] **Step 1: Add SearXNG settings**

In `src/d4bl/settings.py`, add new fields to the dataclass:

```python
    searxng_base_url: str = field(init=False)
    search_provider: str = field(init=False)
```

In `__post_init__`, add the env var reads:

```python
        object.__setattr__(
            self,
            "searxng_base_url",
            os.getenv("SEARXNG_BASE_URL", "http://searxng:8080"),
        )
        object.__setattr__(
            self,
            "search_provider",
            os.getenv("SEARCH_PROVIDER", "searxng"),
        )
```

- [ ] **Step 2: Update CrewAI researcher agent**

In `src/d4bl/agents/crew.py`, replace the crawl provider selection in the `researcher` method.

Add the import at the top:

```python
from d4bl.agents.tools.crawl_tools.searxng import SearXNGSearchTool
```

Replace the researcher method's tool selection logic with:

```python
    @agent
    def researcher(self) -> Agent:
        settings = get_settings()

        # Search tool: SearXNG (default) or Serper
        if settings.search_provider == "searxng":
            logger.info("Using SearXNG at: %s", settings.searxng_base_url)
            search_tool = SearXNGSearchTool(
                base_url=settings.searxng_base_url,
            )
        else:
            # Legacy Serper path — kept for backward compatibility
            logger.info("Using Crawl4AI with Serper search")
            search_tool = Crawl4AISearchTool(
                base_url=settings.crawl4ai_base_url,
                api_key=settings.crawl4ai_api_key,
            )

        return Agent(
            config=self.agents_config['researcher'],
            llm=get_llm(),
            tools=[search_tool],
            verbose=True,
            allow_delegation=False,
        )
```

- [ ] **Step 3: Verify app imports cleanly**

```bash
python -c "from d4bl.agents.crew import D4BLCrew; print('Import OK')"
```

Expected: `Import OK`

- [ ] **Step 4: Commit**

```bash
git add src/d4bl/settings.py src/d4bl/agents/crew.py
git commit -m "feat: wire SearXNG as default search provider in settings and CrewAI

Add SEARXNG_BASE_URL and SEARCH_PROVIDER settings. Update researcher
agent to use SearXNG by default with Crawl4AI/Serper as fallback."
```

---

### Task 5: Remove Firecrawl

**Files:**
- Delete: `docker-compose.firecrawl.yml`
- Delete: `src/d4bl/agents/tools/crawl_tools/firecrawl.py`
- Modify: `src/d4bl/settings.py` — Remove `firecrawl_api_key`, `firecrawl_base_url`
- Modify: `src/d4bl/agents/tools/crawl_tools/crawl4ai.py` — Remove Firecrawl fallback
- Modify: `docker-compose.base.yml` — Remove Firecrawl env vars
- Modify: `pyproject.toml` — Remove `firecrawl-py`
- Modify: `CLAUDE.md` — Remove Firecrawl references

- [ ] **Step 1: Delete Firecrawl files**

```bash
rm docker-compose.firecrawl.yml
rm src/d4bl/agents/tools/crawl_tools/firecrawl.py
```

- [ ] **Step 2: Remove Firecrawl settings**

In `src/d4bl/settings.py`, remove the `firecrawl_api_key` and `firecrawl_base_url` fields and their `__post_init__` reads. Change the default `crawl_provider` to `crawl4ai`.

- [ ] **Step 3: Remove Firecrawl fallback from crawl4ai.py**

In `src/d4bl/agents/tools/crawl_tools/crawl4ai.py`, find and remove the Firecrawl fallback import and logic (the section that falls back to Firecrawl on Crawl4AI connection failure). Replace with a simple error return.

- [ ] **Step 4: Remove Firecrawl from __init__.py**

In `src/d4bl/agents/tools/crawl_tools/__init__.py`, remove any Firecrawl imports:

```python
# Remove lines like:
# from .firecrawl import FirecrawlSearchWrapper, SelfHostedFirecrawlSearchTool
```

- [ ] **Step 5: Remove firecrawl-py from pyproject.toml**

Remove the line:

```
"firecrawl-py>=4.8.0",
```

- [ ] **Step 6: Remove Firecrawl env vars from docker-compose.base.yml**

Remove these lines:

```yaml
FIRECRAWL_BASE_URL=${FIRECRAWL_BASE_URL:-http://firecrawl-api:3002}
FIRECRAWL_API_KEY=${FIRECRAWL_API_KEY:-}
```

Add SearXNG env var:

```yaml
SEARXNG_BASE_URL=${SEARXNG_BASE_URL:-http://searxng:8080}
SEARCH_PROVIDER=${SEARCH_PROVIDER:-searxng}
```

- [ ] **Step 7: Update CLAUDE.md**

Remove Firecrawl references:
1. Remove `CRAWL_PROVIDER=firecrawl|crawl4ai` (change to just `crawl4ai`)
2. Remove `FIRECRAWL_API_KEY` and `FIRECRAWL_BASE_URL` from Configuration section
3. Remove the Firecrawl Docker compose line under Docker section
4. Add SearXNG Docker compose line:
```
# Add SearXNG search
docker compose -f docker-compose.base.yml -f docker-compose.searxng.yml up --build
```
5. Add `SEARXNG_BASE_URL` and `SEARCH_PROVIDER` to Configuration section

- [ ] **Step 8: Grep for remaining Firecrawl references**

```bash
grep -ri "firecrawl" src/ scripts/ docker-compose*.yml CLAUDE.md pyproject.toml --include="*.py" --include="*.yml" --include="*.md" --include="*.toml"
```

Expected: No results.

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -m "feat: remove Firecrawl, default to Crawl4AI + SearXNG

Remove Firecrawl docker compose (5 containers), Python SDK, settings,
and all code paths. Default crawl provider is now crawl4ai. Default
search provider is now SearXNG. Net: remove 5 containers, add 1."
```

---

### Task 6: Create RSS Feed Ingestion Script

**Files:**
- Create: `scripts/ingestion/ingest_rss_feeds.py`
- Test: `tests/test_ingest_rss.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_ingest_rss.py`:

```python
"""Tests for RSS feed ingestion."""

import pytest
from unittest.mock import patch, MagicMock
from scripts.ingestion.ingest_rss_feeds import (
    parse_rss_feed,
    parse_atom_feed,
    parse_feed,
)


SAMPLE_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
  <title>Test Feed</title>
  <item>
    <title>Article One</title>
    <link>https://example.com/article-1</link>
    <guid>article-1-guid</guid>
    <pubDate>Mon, 01 Jan 2026 00:00:00 GMT</pubDate>
    <description>First article description.</description>
  </item>
  <item>
    <title>Article Two</title>
    <link>https://example.com/article-2</link>
    <guid>article-2-guid</guid>
    <description>Second article description.</description>
  </item>
</channel>
</rss>"""


SAMPLE_ATOM = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Test Atom Feed</title>
  <entry>
    <title>Atom Entry One</title>
    <link href="https://example.com/atom-1"/>
    <id>atom-entry-1</id>
    <summary>Atom entry summary.</summary>
  </entry>
</feed>"""


def test_parse_rss_feed():
    """parse_rss_feed extracts items from RSS XML."""
    entries = parse_rss_feed(SAMPLE_RSS)
    assert len(entries) == 2
    assert entries[0]["title"] == "Article One"
    assert entries[0]["url"] == "https://example.com/article-1"
    assert entries[0]["guid"] == "article-1-guid"


def test_parse_atom_feed():
    """parse_atom_feed extracts entries from Atom XML."""
    entries = parse_atom_feed(SAMPLE_ATOM)
    assert len(entries) == 1
    assert entries[0]["title"] == "Atom Entry One"
    assert entries[0]["url"] == "https://example.com/atom-1"
    assert entries[0]["guid"] == "atom-entry-1"


def test_parse_feed_auto_detects_rss():
    """parse_feed auto-detects RSS format."""
    entries = parse_feed(SAMPLE_RSS)
    assert len(entries) == 2


def test_parse_feed_auto_detects_atom():
    """parse_feed auto-detects Atom format."""
    entries = parse_feed(SAMPLE_ATOM)
    assert len(entries) == 1


def test_parse_feed_empty():
    """parse_feed returns empty list for invalid XML."""
    entries = parse_feed("<html><body>Not a feed</body></html>")
    assert entries == []
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_ingest_rss.py -v
```

Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Create the RSS ingestion script**

Create `scripts/ingestion/ingest_rss_feeds.py`:

```python
"""Ingest articles from RSS and Atom feeds.

Reads feed URLs from data_sources table (source_type='rss_feed'),
fetches each feed, parses entries, and upserts to ingested_records.
"""

from __future__ import annotations

import logging
import os
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import httpx

# Ensure scripts/ is on path for helpers import
_SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from ingestion.helpers import get_db_connection, upsert_batch, make_record_id

logger = logging.getLogger(__name__)

ATOM_NS = "http://www.w3.org/2005/Atom"

UPSERT_SQL = """
    INSERT INTO ingested_records
        (id, source_type, source_key, external_id, title, url, content,
         published_at, metadata, ingested_at)
    VALUES
        (CAST(%(id)s AS UUID), %(source_type)s, %(source_key)s, %(external_id)s,
         %(title)s, %(url)s, %(content)s, %(published_at)s,
         CAST(%(metadata)s AS JSONB), %(ingested_at)s)
    ON CONFLICT (source_type, external_id)
    DO UPDATE SET
        title = EXCLUDED.title,
        content = EXCLUDED.content,
        metadata = EXCLUDED.metadata,
        ingested_at = EXCLUDED.ingested_at
"""


def parse_rss_feed(xml_text: str) -> list[dict]:
    """Parse RSS 2.0 feed XML into a list of entry dicts."""
    entries = []
    try:
        root = ET.fromstring(xml_text)
        for item in root.iter("item"):
            title = item.findtext("title", "")
            link = item.findtext("link", "")
            guid = item.findtext("guid", link)
            pub_date = item.findtext("pubDate", "")
            description = item.findtext("description", "")

            entries.append({
                "title": title.strip(),
                "url": link.strip(),
                "guid": guid.strip(),
                "date": pub_date.strip(),
                "content": description.strip(),
            })
    except ET.ParseError:
        logger.warning("Failed to parse RSS XML")
    return entries


def parse_atom_feed(xml_text: str) -> list[dict]:
    """Parse Atom feed XML into a list of entry dicts."""
    entries = []
    try:
        root = ET.fromstring(xml_text)
        for entry in root.iter(f"{{{ATOM_NS}}}entry"):
            title_el = entry.find(f"{{{ATOM_NS}}}title")
            title = title_el.text.strip() if title_el is not None and title_el.text else ""

            link_el = entry.find(f"{{{ATOM_NS}}}link")
            url = link_el.get("href", "") if link_el is not None else ""

            id_el = entry.find(f"{{{ATOM_NS}}}id")
            guid = id_el.text.strip() if id_el is not None and id_el.text else url

            summary_el = entry.find(f"{{{ATOM_NS}}}summary")
            content = summary_el.text.strip() if summary_el is not None and summary_el.text else ""

            updated_el = entry.find(f"{{{ATOM_NS}}}updated")
            date = updated_el.text.strip() if updated_el is not None and updated_el.text else ""

            entries.append({
                "title": title,
                "url": url,
                "guid": guid,
                "date": date,
                "content": content,
            })
    except ET.ParseError:
        logger.warning("Failed to parse Atom XML")
    return entries


def parse_feed(xml_text: str) -> list[dict]:
    """Auto-detect feed format and parse entries."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []

    # Detect format by root tag
    tag = root.tag.lower()
    if "feed" in tag:
        return parse_atom_feed(xml_text)
    if "rss" in tag or root.find("channel") is not None:
        return parse_rss_feed(xml_text)

    return []


def main() -> int:
    """Fetch and ingest all configured RSS feeds. Returns records ingested."""
    conn = get_db_connection()
    conn.autocommit = False
    cur = conn.cursor()

    # Get RSS feed sources from data_sources table
    cur.execute(
        "SELECT id, name, config FROM data_sources WHERE source_type = 'rss_feed' AND enabled = true"
    )
    sources = cur.fetchall()

    if not sources:
        print("No RSS feed sources configured in data_sources table.")
        return 0

    records_ingested = 0
    now = datetime.now(timezone.utc).isoformat()

    with httpx.Client(timeout=60, follow_redirects=True) as client:
        for source_id, source_name, config in sources:
            feed_url = config.get("url") if config else None
            if not feed_url:
                print(f"  Skipping {source_name}: no URL in config")
                continue

            print(f"  Fetching feed: {source_name} ({feed_url})")
            try:
                response = client.get(feed_url)
                if response.status_code != 200:
                    print(f"  HTTP {response.status_code} for {feed_url}")
                    continue

                entries = parse_feed(response.text)
                print(f"  Found {len(entries)} entries in {source_name}")

                batch = []
                for entry in entries:
                    if not entry["url"] and not entry["guid"]:
                        continue

                    record_id = make_record_id("rss", source_name, entry["guid"])
                    batch.append({
                        "id": str(record_id),
                        "source_type": "rss",
                        "source_key": source_name,
                        "external_id": entry["guid"],
                        "title": entry["title"][:500] if entry["title"] else None,
                        "url": entry["url"],
                        "content": entry["content"],
                        "published_at": entry["date"] or None,
                        "metadata": "{}",
                        "ingested_at": now,
                    })

                if batch:
                    count = upsert_batch(conn, UPSERT_SQL, batch)
                    records_ingested += count
                    print(f"  Upserted {count} records from {source_name}")

            except Exception as exc:
                print(f"  Error fetching {source_name}: {exc}")
                continue

    cur.close()
    conn.close()
    print(f"RSS ingestion complete: {records_ingested} total records")
    return records_ingested


if __name__ == "__main__":
    sys.exit(0 if main() >= 0 else 1)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_ingest_rss.py -v
```

Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/ingestion/ingest_rss_feeds.py tests/test_ingest_rss.py
git commit -m "feat: add RSS/Atom feed ingestion script

Reads feed URLs from data_sources table, parses RSS 2.0 and Atom
formats, deduplicates by GUID, and upserts to ingested_records."
```

---

### Task 7: Create News Search Ingestion Script

**Files:**
- Create: `scripts/ingestion/ingest_news_search.py`
- Test: `tests/test_ingest_news.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_ingest_news.py`:

```python
"""Tests for news search ingestion."""

import pytest
from unittest.mock import patch, MagicMock
from scripts.ingestion.ingest_news_search import (
    search_news,
    deduplicate_urls,
)


def test_deduplicate_urls_removes_duplicates():
    """deduplicate_urls removes entries with duplicate URLs."""
    results = [
        {"url": "https://example.com/a", "title": "First"},
        {"url": "https://example.com/b", "title": "Second"},
        {"url": "https://example.com/a", "title": "Duplicate"},
    ]
    deduped = deduplicate_urls(results)
    assert len(deduped) == 2
    assert deduped[0]["title"] == "First"
    assert deduped[1]["title"] == "Second"


def test_deduplicate_urls_empty():
    """deduplicate_urls handles empty list."""
    assert deduplicate_urls([]) == []


@patch("scripts.ingestion.ingest_news_search.httpx")
def test_search_news_queries_searxng(mock_httpx):
    """search_news calls SearXNG with news category."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "results": [
            {"title": "News 1", "url": "https://news.com/1", "content": "snippet"},
        ]
    }
    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.get.return_value = mock_response
    mock_httpx.Client.return_value = mock_client

    results = search_news("racial equity", "http://localhost:8080")
    assert len(results) == 1
    assert results[0]["title"] == "News 1"

    call_kwargs = mock_client.get.call_args
    params = call_kwargs[1].get("params") or call_kwargs.kwargs.get("params")
    assert params["categories"] == "news"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_ingest_news.py -v
```

Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Create the news search script**

Create `scripts/ingestion/ingest_news_search.py`:

```python
"""Ingest news articles discovered via SearXNG search.

Reads search queries from keyword_monitors table, queries SearXNG
with news category, extracts article content, and upserts to
ingested_records.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone

import httpx

_SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from ingestion.helpers import get_db_connection, upsert_batch, make_record_id

logger = logging.getLogger(__name__)

SEARXNG_BASE_URL = os.environ.get("SEARXNG_BASE_URL", "http://searxng:8080")

UPSERT_SQL = """
    INSERT INTO ingested_records
        (id, source_type, source_key, external_id, title, url, content,
         published_at, metadata, ingested_at)
    VALUES
        (CAST(%(id)s AS UUID), %(source_type)s, %(source_key)s, %(external_id)s,
         %(title)s, %(url)s, %(content)s, %(published_at)s,
         CAST(%(metadata)s AS JSONB), %(ingested_at)s)
    ON CONFLICT (source_type, external_id)
    DO UPDATE SET
        title = EXCLUDED.title,
        content = EXCLUDED.content,
        metadata = EXCLUDED.metadata,
        ingested_at = EXCLUDED.ingested_at
"""


def search_news(query: str, base_url: str = SEARXNG_BASE_URL) -> list[dict]:
    """Query SearXNG for news results.

    Returns list of {"title", "url", "content"} dicts.
    """
    try:
        with httpx.Client(timeout=30) as client:
            response = client.get(
                f"{base_url}/search",
                params={
                    "q": query,
                    "format": "json",
                    "categories": "news",
                },
            )
            if response.status_code != 200:
                logger.warning("SearXNG returned %d for query: %s", response.status_code, query)
                return []

            data = response.json()
            return [
                {
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "content": r.get("content", ""),
                }
                for r in data.get("results", [])
                if r.get("url")
            ]
    except Exception:
        logger.exception("SearXNG search failed for: %s", query)
        return []


def deduplicate_urls(results: list[dict]) -> list[dict]:
    """Remove entries with duplicate URLs, keeping first occurrence."""
    seen: set[str] = set()
    deduped = []
    for r in results:
        url = r.get("url", "")
        if url and url not in seen:
            seen.add(url)
            deduped.append(r)
    return deduped


def main() -> int:
    """Search for news on monitored keywords and ingest results."""
    conn = get_db_connection()
    conn.autocommit = False
    cur = conn.cursor()

    # Read active keyword monitors
    cur.execute(
        "SELECT id, keyword, config FROM keyword_monitors WHERE enabled = true"
    )
    monitors = cur.fetchall()

    if not monitors:
        print("No active keyword monitors configured.")
        return 0

    records_ingested = 0
    now = datetime.now(timezone.utc).isoformat()

    for monitor_id, keyword, config in monitors:
        print(f"  Searching news for: {keyword}")
        results = search_news(keyword)
        results = deduplicate_urls(results)
        print(f"  Found {len(results)} unique results")

        batch = []
        for result in results:
            record_id = make_record_id("news_search", keyword, result["url"])
            batch.append({
                "id": str(record_id),
                "source_type": "news_search",
                "source_key": keyword,
                "external_id": result["url"],
                "title": result["title"][:500] if result["title"] else None,
                "url": result["url"],
                "content": result["content"],
                "published_at": None,
                "metadata": json.dumps({"keyword_monitor_id": str(monitor_id)}),
                "ingested_at": now,
            })

        if batch:
            count = upsert_batch(conn, UPSERT_SQL, batch)
            records_ingested += count
            print(f"  Upserted {count} records for keyword: {keyword}")

    cur.close()
    conn.close()
    print(f"News search complete: {records_ingested} total records")
    return records_ingested


if __name__ == "__main__":
    sys.exit(0 if main() >= 0 else 1)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_ingest_news.py -v
```

Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/ingestion/ingest_news_search.py tests/test_ingest_news.py
git commit -m "feat: add SearXNG-powered news search ingestion script

Reads keywords from keyword_monitors table, queries SearXNG news
category, deduplicates by URL, and upserts to ingested_records."
```

---

### Task 8: Create Web Sources Ingestion Script

**Files:**
- Create: `scripts/ingestion/ingest_web_sources.py`

- [ ] **Step 1: Create the web sources script**

Create `scripts/ingestion/ingest_web_sources.py`:

```python
"""Ingest content from configured web sources.

Reads target URLs from data_sources table (source_type='web_scrape'),
extracts content using the tiered content extractor, and upserts to
ingested_records.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone

_SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from ingestion.helpers import get_db_connection, upsert_batch, make_record_id
from ingestion.lib.content_extractor import extract

logger = logging.getLogger(__name__)

UPSERT_SQL = """
    INSERT INTO ingested_records
        (id, source_type, source_key, external_id, title, url, content,
         published_at, metadata, ingested_at)
    VALUES
        (CAST(%(id)s AS UUID), %(source_type)s, %(source_key)s, %(external_id)s,
         %(title)s, %(url)s, %(content)s, %(published_at)s,
         CAST(%(metadata)s AS JSONB), %(ingested_at)s)
    ON CONFLICT (source_type, external_id)
    DO UPDATE SET
        title = EXCLUDED.title,
        content = EXCLUDED.content,
        metadata = EXCLUDED.metadata,
        ingested_at = EXCLUDED.ingested_at
"""


def main() -> int:
    """Scrape all configured web sources. Returns records ingested."""
    conn = get_db_connection()
    conn.autocommit = False
    cur = conn.cursor()

    cur.execute(
        "SELECT id, name, config FROM data_sources WHERE source_type = 'web_scrape' AND enabled = true"
    )
    sources = cur.fetchall()

    if not sources:
        print("No web scrape sources configured in data_sources table.")
        return 0

    records_ingested = 0
    now = datetime.now(timezone.utc).isoformat()

    for source_id, source_name, config in sources:
        urls = config.get("urls", []) if config else []
        force_js = config.get("force_js", False) if config else False

        if not urls:
            print(f"  Skipping {source_name}: no URLs in config")
            continue

        print(f"  Scraping {source_name}: {len(urls)} URLs")
        batch = []

        for url in urls:
            print(f"    Extracting: {url}")
            result = extract(url, force_js=force_js)

            if not result:
                print(f"    No content extracted from {url}")
                continue

            record_id = make_record_id("web_scrape", source_name, url)
            batch.append({
                "id": str(record_id),
                "source_type": "web_scrape",
                "source_key": source_name,
                "external_id": url,
                "title": result.title[:500] if result.title else None,
                "url": url,
                "content": result.text,
                "published_at": result.date,
                "metadata": json.dumps({
                    "author": result.author,
                    "extraction_method": result.source_type,
                }),
                "ingested_at": now,
            })

        if batch:
            count = upsert_batch(conn, UPSERT_SQL, batch)
            records_ingested += count
            print(f"  Upserted {count} records from {source_name}")

    cur.close()
    conn.close()
    print(f"Web scrape complete: {records_ingested} total records")
    return records_ingested


if __name__ == "__main__":
    sys.exit(0 if main() >= 0 else 1)
```

- [ ] **Step 2: Commit**

```bash
git add scripts/ingestion/ingest_web_sources.py
git commit -m "feat: add web source scraping ingestion script

Reads target URLs from data_sources config, extracts content via
tiered extractor (trafilatura → Crawl4AI), upserts to ingested_records."
```

---

### Task 9: Add New Data Source Scripts (County Health Rankings, USASpending, Vera)

**Files:**
- Create: `scripts/ingestion/ingest_county_health_rankings.py`
- Create: `scripts/ingestion/ingest_usaspending.py`
- Create: `scripts/ingestion/ingest_vera_incarceration.py`

- [ ] **Step 1: Create County Health Rankings script**

Create `scripts/ingestion/ingest_county_health_rankings.py`:

```python
"""Ingest County Health Rankings data.

Downloads annual CSV from countyhealthrankings.org with 30+ health
measures per county. FIPS-coded.

Source: https://www.countyhealthrankings.org/
"""

from __future__ import annotations

import csv
import io
import os
import sys
from datetime import datetime, timezone

import httpx

_SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from ingestion.helpers import (
    get_db_connection,
    upsert_batch,
    make_record_id,
    safe_float,
    safe_int,
)

YEAR = os.environ.get("CHR_YEAR", "2025")

# County Health Rankings national data download URL
# The CSV contains one row per county with columns for each measure
DATA_URL = (
    f"https://www.countyhealthrankings.org/sites/default/files/media/document/"
    f"{YEAR}%20County%20Health%20Rankings%20Data%20-%20v2.csv"
)

# Fallback: analytic data URL (more structured)
ANALYTIC_URL = (
    "https://www.countyhealthrankings.org/sites/default/files/media/document/"
    f"analytic_data{YEAR}.csv"
)

UPSERT_SQL = """
    INSERT INTO ingested_records
        (id, source_type, source_key, external_id, title, url, content,
         metadata, ingested_at)
    VALUES
        (CAST(%(id)s AS UUID), %(source_type)s, %(source_key)s, %(external_id)s,
         %(title)s, %(url)s, %(content)s,
         CAST(%(metadata)s AS JSONB), %(ingested_at)s)
    ON CONFLICT (source_type, external_id)
    DO UPDATE SET
        content = EXCLUDED.content,
        metadata = EXCLUDED.metadata,
        ingested_at = EXCLUDED.ingested_at
"""


def main() -> int:
    """Download and ingest County Health Rankings data."""
    import json

    conn = get_db_connection()
    conn.autocommit = False
    cur = conn.cursor()

    records_ingested = 0
    now = datetime.now(timezone.utc).isoformat()

    with httpx.Client(timeout=120, follow_redirects=True) as client:
        print(f"Downloading County Health Rankings data for {YEAR}...")
        response = client.get(DATA_URL)

        if response.status_code != 200:
            print(f"Primary URL returned {response.status_code}, trying analytic URL...")
            response = client.get(ANALYTIC_URL)
            if response.status_code != 200:
                print(f"Failed to download data: HTTP {response.status_code}")
                return 0

        reader = csv.DictReader(io.StringIO(response.text))
        batch = []

        for row in reader:
            fips = row.get("FIPS", row.get("fipscode", "")).strip()
            county = row.get("County", row.get("county", "")).strip()
            state = row.get("State", row.get("state", "")).strip()

            if not fips or len(fips) < 5:
                continue

            record_id = make_record_id("county_health_rankings", YEAR, fips)

            # Extract available numeric measures
            measures = {}
            for key, value in row.items():
                if value and key not in ("FIPS", "fipscode", "County", "county", "State", "state"):
                    float_val = safe_float(value)
                    if float_val is not None:
                        measures[key] = float_val

            batch.append({
                "id": str(record_id),
                "source_type": "county_health_rankings",
                "source_key": "chr",
                "external_id": f"chr-{YEAR}-{fips}",
                "title": f"{county}, {state} - County Health Rankings {YEAR}",
                "url": f"https://www.countyhealthrankings.org/explore-health-rankings/county-health-rankings-model",
                "content": json.dumps(measures),
                "metadata": json.dumps({
                    "fips": fips,
                    "county": county,
                    "state": state,
                    "year": YEAR,
                    "measure_count": len(measures),
                }),
                "ingested_at": now,
            })

            if len(batch) >= 500:
                count = upsert_batch(conn, UPSERT_SQL, batch)
                records_ingested += count
                batch = []

        if batch:
            count = upsert_batch(conn, UPSERT_SQL, batch)
            records_ingested += count

    cur.close()
    conn.close()
    print(f"County Health Rankings: {records_ingested} county records ingested")
    return records_ingested


if __name__ == "__main__":
    sys.exit(0 if main() >= 0 else 1)
```

- [ ] **Step 2: Create USASpending script**

Create `scripts/ingestion/ingest_usaspending.py`:

```python
"""Ingest federal spending data from USASpending.gov.

Queries spending by county using the free REST API (no key required).

Source: https://api.usaspending.gov/
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

import httpx

_SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from ingestion.helpers import (
    get_db_connection,
    upsert_batch,
    make_record_id,
    safe_float,
    STATE_FIPS,
)

FISCAL_YEAR = os.environ.get("USASPENDING_YEAR", "2025")

API_BASE = "https://api.usaspending.gov/api/v2"

UPSERT_SQL = """
    INSERT INTO ingested_records
        (id, source_type, source_key, external_id, title, url, content,
         metadata, ingested_at)
    VALUES
        (CAST(%(id)s AS UUID), %(source_type)s, %(source_key)s, %(external_id)s,
         %(title)s, %(url)s, %(content)s,
         CAST(%(metadata)s AS JSONB), %(ingested_at)s)
    ON CONFLICT (source_type, external_id)
    DO UPDATE SET
        content = EXCLUDED.content,
        metadata = EXCLUDED.metadata,
        ingested_at = EXCLUDED.ingested_at
"""


def fetch_state_spending(client: httpx.Client, state_fips: str) -> list[dict]:
    """Fetch county-level spending for a state."""
    url = f"{API_BASE}/search/spending_by_geography/"
    payload = {
        "scope": "place_of_performance",
        "geo_layer": "county",
        "geo_layer_filters": [state_fips],
        "filters": {
            "time_period": [
                {"start_date": f"{FISCAL_YEAR}-01-01", "end_date": f"{FISCAL_YEAR}-12-31"}
            ]
        },
    }

    response = client.post(url, json=payload)
    if response.status_code != 200:
        return []

    data = response.json()
    return data.get("results", [])


def main() -> int:
    """Fetch and ingest USASpending data by county."""
    conn = get_db_connection()
    conn.autocommit = False
    cur = conn.cursor()

    records_ingested = 0
    now = datetime.now(timezone.utc).isoformat()

    with httpx.Client(timeout=60) as client:
        for state_name, state_fips in STATE_FIPS.items():
            print(f"  Fetching spending for {state_name} ({state_fips})...")
            results = fetch_state_spending(client, state_fips)

            batch = []
            for result in results:
                county_fips = result.get("shape_code", "")
                if not county_fips:
                    continue

                full_fips = f"{state_fips}{county_fips}"
                amount = safe_float(result.get("aggregated_amount"))
                per_capita = safe_float(result.get("per_capita"))

                record_id = make_record_id("usaspending", FISCAL_YEAR, full_fips)
                batch.append({
                    "id": str(record_id),
                    "source_type": "usaspending",
                    "source_key": "usaspending",
                    "external_id": f"usa-{FISCAL_YEAR}-{full_fips}",
                    "title": f"{result.get('display_name', county_fips)} - Federal Spending FY{FISCAL_YEAR}",
                    "url": f"https://www.usaspending.gov/search/?hash=county-{full_fips}",
                    "content": json.dumps({
                        "total_spending": amount,
                        "per_capita": per_capita,
                        "population": result.get("population"),
                    }),
                    "metadata": json.dumps({
                        "fips": full_fips,
                        "state_fips": state_fips,
                        "county_name": result.get("display_name"),
                        "fiscal_year": FISCAL_YEAR,
                    }),
                    "ingested_at": now,
                })

            if batch:
                count = upsert_batch(conn, UPSERT_SQL, batch)
                records_ingested += count

    cur.close()
    conn.close()
    print(f"USASpending: {records_ingested} county records ingested for FY{FISCAL_YEAR}")
    return records_ingested


if __name__ == "__main__":
    sys.exit(0 if main() >= 0 else 1)
```

- [ ] **Step 3: Create Vera Institute script**

Create `scripts/ingestion/ingest_vera_incarceration.py`:

```python
"""Ingest Vera Institute incarceration trends data.

Downloads county-level jail/prison population by race from the
vera-institute/incarceration-trends GitHub repository.

Source: https://github.com/vera-institute/incarceration-trends
"""

from __future__ import annotations

import csv
import io
import json
import os
import sys
from datetime import datetime, timezone

import httpx

_SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from ingestion.helpers import (
    get_db_connection,
    upsert_batch,
    make_record_id,
    safe_float,
    safe_int,
)

# Vera Institute GitHub raw CSV URL
DATA_URL = (
    "https://raw.githubusercontent.com/vera-institute/incarceration-trends/"
    "master/incarceration_trends.csv"
)

# Key columns with racial breakdowns
RACE_COLUMNS = [
    "black_jail_pop",
    "white_jail_pop",
    "latinx_jail_pop",
    "aapi_jail_pop",
    "native_jail_pop",
    "other_race_jail_pop",
    "black_prison_pop",
    "white_prison_pop",
    "latinx_prison_pop",
    "aapi_prison_pop",
    "native_prison_pop",
    "other_race_prison_pop",
    "total_jail_pop",
    "total_prison_pop",
    "total_pop",
    "black_pop_15to64",
    "white_pop_15to64",
    "latinx_pop_15to64",
]

UPSERT_SQL = """
    INSERT INTO ingested_records
        (id, source_type, source_key, external_id, title, url, content,
         metadata, ingested_at)
    VALUES
        (CAST(%(id)s AS UUID), %(source_type)s, %(source_key)s, %(external_id)s,
         %(title)s, %(url)s, %(content)s,
         CAST(%(metadata)s AS JSONB), %(ingested_at)s)
    ON CONFLICT (source_type, external_id)
    DO UPDATE SET
        content = EXCLUDED.content,
        metadata = EXCLUDED.metadata,
        ingested_at = EXCLUDED.ingested_at
"""


def main() -> int:
    """Download and ingest Vera incarceration trends data."""
    conn = get_db_connection()
    conn.autocommit = False
    cur = conn.cursor()

    records_ingested = 0
    now = datetime.now(timezone.utc).isoformat()

    with httpx.Client(timeout=120, follow_redirects=True) as client:
        print("Downloading Vera Institute incarceration trends CSV...")
        response = client.get(DATA_URL)

        if response.status_code != 200:
            print(f"Failed to download: HTTP {response.status_code}")
            return 0

        reader = csv.DictReader(io.StringIO(response.text))
        batch = []

        for row in reader:
            fips = row.get("fips", "").strip()
            year = row.get("year", "").strip()
            county = row.get("county_name", "").strip()
            state = row.get("state", "").strip()

            if not fips or not year:
                continue

            # Extract racial breakdown data
            measures = {}
            for col in RACE_COLUMNS:
                val = safe_float(row.get(col))
                if val is not None:
                    measures[col] = val

            if not measures:
                continue

            record_id = make_record_id("vera", year, fips)
            batch.append({
                "id": str(record_id),
                "source_type": "vera_incarceration",
                "source_key": "vera",
                "external_id": f"vera-{year}-{fips}",
                "title": f"{county}, {state} - Incarceration Trends {year}",
                "url": "https://github.com/vera-institute/incarceration-trends",
                "content": json.dumps(measures),
                "metadata": json.dumps({
                    "fips": fips,
                    "county": county,
                    "state": state,
                    "year": year,
                    "urbanicity": row.get("urbanicity", ""),
                    "region": row.get("region", ""),
                }),
                "ingested_at": now,
            })

            if len(batch) >= 1000:
                count = upsert_batch(conn, UPSERT_SQL, batch)
                records_ingested += count
                batch = []

        if batch:
            count = upsert_batch(conn, UPSERT_SQL, batch)
            records_ingested += count

    cur.close()
    conn.close()
    print(f"Vera Incarceration: {records_ingested} county-year records ingested")
    return records_ingested


if __name__ == "__main__":
    sys.exit(0 if main() >= 0 else 1)
```

- [ ] **Step 4: Commit**

```bash
git add scripts/ingestion/ingest_county_health_rankings.py scripts/ingestion/ingest_usaspending.py scripts/ingestion/ingest_vera_incarceration.py
git commit -m "feat: add 3 new data source ingestion scripts

- County Health Rankings: 30+ health measures per county (CSV)
- USASpending.gov: federal spending by county (REST API)
- Vera Institute: county-level incarceration by race (GitHub CSV)"
```

---

### Task 10: Register New Sources in SCRIPT_REGISTRY and Add Schedules

**Files:**
- Modify: `src/d4bl/services/ingestion_runner.py`
- Modify: `src/d4bl/services/scheduler.py`

- [ ] **Step 1: Add new sources to SCRIPT_REGISTRY**

In `src/d4bl/services/ingestion_runner.py`, add to the `SCRIPT_REGISTRY` dict:

```python
    # Web content sources (Sprint 2)
    "rss": "ingest_rss_feeds",
    "rss_feeds": "ingest_rss_feeds",
    "web": "ingest_web_sources",
    "web_scrape": "ingest_web_sources",
    "news": "ingest_news_search",
    "news_search": "ingest_news_search",
    # New data sources (Sprint 2)
    "county_health": "ingest_county_health_rankings",
    "chr": "ingest_county_health_rankings",
    "usaspending": "ingest_usaspending",
    "vera": "ingest_vera_incarceration",
    "vera_incarceration": "ingest_vera_incarceration",
```

- [ ] **Step 2: Add default schedules for new sources**

In `src/d4bl/services/scheduler.py`, add to `DEFAULT_SCHEDULES`:

```python
    # Web content (Sprint 2)
    "rss": "0 6 * * *",           # Daily at 6 AM
    "news": "0 6 * * *",          # Daily at 6 AM
    "web": "0 6 * * 1",           # Weekly Monday at 6 AM
    # New data sources (Sprint 2)
    "county_health": "0 0 15 3 *", # Annually March 15
    "usaspending": "0 0 1 * *",    # Monthly 1st
    "vera": "0 0 1 1,4,7,10 *",   # Quarterly
```

- [ ] **Step 3: Verify sources are listed**

```bash
python scripts/run_ingestion.py --list
```

Expected: All new sources (rss, web, news, county_health, usaspending, vera) appear in the list.

- [ ] **Step 4: Commit**

```bash
git add src/d4bl/services/ingestion_runner.py src/d4bl/services/scheduler.py
git commit -m "feat: register new sources in SCRIPT_REGISTRY and default schedules

Add RSS, web scrape, news search, County Health Rankings, USASpending,
and Vera incarceration to the ingestion registry and scheduler defaults."
```

---

### Task 11: Update CLAUDE.md with New Architecture

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update architecture diagram and docs**

Add SearXNG to the architecture section, update the data ingestion commands, and add new sources to the ingestion scripts list.

Key changes:
1. Add SearXNG to External Services list
2. Add `docker compose -f docker-compose.base.yml -f docker-compose.searxng.yml up --build` to Docker section
3. Add `SEARXNG_BASE_URL` and `SEARCH_PROVIDER` to Configuration section
4. Update ingestion scripts list to include RSS, web, news, County Health Rankings, USASpending, Vera
5. Add port 8080 for SearXNG to Service Ports table

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md with SearXNG and new data sources"
```

---

### Task 12: Final Verification

- [ ] **Step 1: Run all tests**

```bash
python -m pytest tests/test_content_extractor.py tests/test_searxng_tool.py tests/test_ingest_rss.py tests/test_ingest_news.py tests/test_scheduler.py -v
```

Expected: All tests PASS.

- [ ] **Step 2: Verify no Firecrawl references remain**

```bash
grep -ri "firecrawl" src/ scripts/ docker-compose*.yml CLAUDE.md pyproject.toml --include="*.py" --include="*.yml" --include="*.md" --include="*.toml"
```

Expected: No results.

- [ ] **Step 3: Verify all sources are registered**

```bash
python scripts/run_ingestion.py --list
```

Expected: All sources listed including new ones.

- [ ] **Step 4: Run full test suite**

```bash
python -m pytest tests/ -v --timeout=60 -x
```

Expected: All tests PASS.

- [ ] **Step 5: Build frontend**

```bash
cd ui-nextjs && npm run build
```

Expected: Build succeeds.

- [ ] **Step 6: Verify Docker compose files are valid**

```bash
docker compose -f docker-compose.base.yml -f docker-compose.searxng.yml config --quiet && echo "Valid"
docker compose -f docker-compose.base.yml -f docker-compose.crawl.yml config --quiet && echo "Valid"
```

Expected: Both report `Valid`.

- [ ] **Step 7: Final commit if any cleanup needed**

```bash
git status
```

If clean, Sprint 2 is complete.
