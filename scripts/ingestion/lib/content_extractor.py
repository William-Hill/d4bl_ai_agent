"""Tiered content extraction library.

Extracts clean text from URLs using the best strategy for each content type:
1. RSS/Atom feeds → XML parsing
2. PDFs → pypdf extraction
3. Static HTML → trafilatura (boilerplate removal + metadata)
4. JS-rendered pages → Crawl4AI fallback
"""

from __future__ import annotations

import io
import json
import logging
import os
import re
from dataclasses import dataclass, field

import httpx
import trafilatura
from pypdf import PdfReader

_CRAWL4AI_BASE_URL = os.getenv("CRAWL4AI_BASE_URL", "http://crawl4ai:11235")

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
    Parses once with JSON output to get both text and metadata.
    """
    raw_json = trafilatura.extract(
        html,
        url=url,
        output_format="json",
        include_comments=False,
        include_tables=True,
        favor_recall=True,
    )
    if not raw_json:
        return None

    meta_dict = {}
    title = None
    author = None
    date = None
    text = ""
    try:
        meta_dict = json.loads(raw_json)
        text = meta_dict.get("text", "")
        title = meta_dict.get("title")
        author = meta_dict.get("author")
        date = meta_dict.get("date")
    except (json.JSONDecodeError, TypeError):
        return None

    if len(text.strip()) < 50:
        return None

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


def extract_from_crawl4ai(
    url: str, base_url: str = _CRAWL4AI_BASE_URL,
) -> ExtractedContent | None:
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
    crawl4ai_base_url: str = _CRAWL4AI_BASE_URL,
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
    # RSS feeds are handled by ingest_rss_feeds.py, not this extractor.
    # If detected as RSS, treat as HTML and let trafilatura attempt extraction.

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
