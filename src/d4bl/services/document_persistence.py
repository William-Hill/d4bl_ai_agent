"""Persist crawled content from research jobs into documents/document_chunks.

After a research job completes, this module extracts crawled page content
from research_data, normalizes URLs, deduplicates, chunks text, and
creates Document + DocumentChunk records with best-effort embeddings.
"""

from __future__ import annotations

import logging
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

logger = logging.getLogger(__name__)

__all__ = ["normalize_url", "chunk_text"]

_TRACKING_PARAMS = frozenset({
    "utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term",
    "fbclid", "gclid", "ref", "source", "sessionid",
})


def normalize_url(raw_url: str) -> str:
    """Normalize a URL for deduplication.

    Lowercases scheme/host, upgrades http to https, strips trailing slash,
    removes tracking query params, and sorts remaining params.
    """
    parsed = urlparse(raw_url)
    scheme = "https"
    netloc = parsed.netloc.lower()
    path = parsed.path.rstrip("/") if parsed.path != "/" else ""
    params = parse_qs(parsed.query, keep_blank_values=True)
    filtered = {
        k: v for k, v in sorted(params.items()) if k.lower() not in _TRACKING_PARAMS
    }
    query = urlencode(filtered, doseq=True)
    return urlunparse((scheme, netloc, path, "", query, ""))


def chunk_text(text: str, max_chars: int = 2000) -> list[tuple[str, int]]:
    """Split text into chunks by paragraph boundaries with a size cap.

    Returns list of (content, token_count) tuples. Token count estimated as len // 4.
    """
    stripped = text.strip()
    if not stripped:
        return []

    paragraphs = stripped.split("\n\n")
    chunks: list[tuple[str, int]] = []
    current: list[str] = []
    current_len = 0

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        if current_len + len(para) > max_chars and current:
            chunk_content = "\n\n".join(current)
            chunks.append((chunk_content, len(chunk_content) // 4))
            current = []
            current_len = 0

        if len(para) > max_chars:
            if current:
                chunk_content = "\n\n".join(current)
                chunks.append((chunk_content, len(chunk_content) // 4))
                current = []
                current_len = 0
            sentences = para.replace(". ", ".\n").split("\n")
            sent_buf: list[str] = []
            sent_len = 0
            for sent in sentences:
                sent = sent.strip()
                if not sent:
                    continue
                if sent_len + len(sent) > max_chars and sent_buf:
                    chunk_content = " ".join(sent_buf)
                    chunks.append((chunk_content, len(chunk_content) // 4))
                    sent_buf = []
                    sent_len = 0
                sent_buf.append(sent)
                sent_len += len(sent) + 1
            if sent_buf:
                chunk_content = " ".join(sent_buf)
                chunks.append((chunk_content, len(chunk_content) // 4))
        else:
            current.append(para)
            current_len += len(para) + 2

    if current:
        chunk_content = "\n\n".join(current)
        chunks.append((chunk_content, len(chunk_content) // 4))

    return chunks
