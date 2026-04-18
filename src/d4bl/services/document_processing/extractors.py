"""Text extractors for staff-uploaded documents.

Each extractor returns the raw text. Empty or near-empty results raise
``ExtractionError`` so the caller can surface a clear message to the admin.
"""

from __future__ import annotations

import io
import logging

import httpx
import trafilatura
from docx import Document as DocxDocument
from pypdf import PdfReader

logger = logging.getLogger(__name__)

MIN_TEXT_LENGTH = 50
URL_FETCH_TIMEOUT = 30.0


class ExtractionError(Exception):
    """Raised when a document cannot be extracted to usable text."""


def extract_pdf(content: bytes) -> str:
    """Extract text from PDF bytes using pypdf.

    Raises ExtractionError if the PDF yields fewer than MIN_TEXT_LENGTH
    characters (likely scanned/image-based and needs OCR).
    """
    try:
        reader = PdfReader(io.BytesIO(content))
    except Exception as exc:
        raise ExtractionError(f"Could not open PDF: {exc}") from exc

    pages_text: list[str] = []
    for page in reader.pages:
        text = page.extract_text() or ""
        if text.strip():
            pages_text.append(text)

    full_text = "\n\n".join(pages_text).strip()
    if len(full_text) < MIN_TEXT_LENGTH:
        raise ExtractionError(
            "PDF yielded no usable text. It may be scanned/image-based; OCR is not supported."
        )
    return full_text


def extract_docx(content: bytes) -> str:
    """Extract text from DOCX bytes using python-docx."""
    try:
        doc = DocxDocument(io.BytesIO(content))
    except Exception as exc:
        raise ExtractionError(f"Could not open DOCX: {exc}") from exc

    paragraphs = [p.text for p in doc.paragraphs if p.text and p.text.strip()]
    full_text = "\n\n".join(paragraphs).strip()
    if len(full_text) < MIN_TEXT_LENGTH:
        raise ExtractionError("DOCX contained no extractable text.")
    return full_text


def extract_url(url: str, *, timeout: float = URL_FETCH_TIMEOUT) -> str:
    """Fetch a URL and extract the main content as plain text.

    Uses httpx to fetch and trafilatura to strip boilerplate. PDF URLs are
    routed through extract_pdf. Falls back to ExtractionError on failure;
    JS-rendered pages are not retried via Crawl4AI in this path — staff
    contributors can upload the PDF directly if trafilatura cannot extract.
    """
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            response = client.get(url)
            response.raise_for_status()
    except httpx.HTTPError as exc:
        raise ExtractionError(f"Could not fetch URL: {exc}") from exc

    content_type = response.headers.get("content-type", "").lower()
    if "application/pdf" in content_type or url.lower().endswith(".pdf"):
        return extract_pdf(response.content)

    text = trafilatura.extract(
        response.text,
        url=url,
        include_comments=False,
        include_tables=True,
        favor_recall=True,
    )
    if not text or len(text.strip()) < MIN_TEXT_LENGTH:
        raise ExtractionError(
            "Could not extract readable content from URL. "
            "If the page is JavaScript-heavy, upload the document as a file instead."
        )
    return text.strip()
