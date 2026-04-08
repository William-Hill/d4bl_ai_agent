"""Persist crawled content from research jobs into documents/document_chunks.

After a research job completes, this module extracts crawled page content
from research_data, normalizes URLs, deduplicates, chunks text, and
creates Document + DocumentChunk records with best-effort embeddings.
"""

from __future__ import annotations

import json
import logging
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse
from uuid import UUID

from sqlalchemy import select
from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession

from d4bl.infra.database import Document, DocumentChunk

logger = logging.getLogger(__name__)

__all__ = ["normalize_url", "chunk_text", "persist_research_documents"]

_TRACKING_PARAMS = frozenset({
    "utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term",
    "fbclid", "gclid", "ref",
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


def chunk_text(content: str, max_chars: int = 2000) -> list[tuple[str, int]]:
    """Split text into chunks by paragraph boundaries with a size cap.

    Returns list of (content, token_count) tuples. Token count estimated as len // 4.
    """
    stripped = content.strip()
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


async def _try_embed(content: str) -> list[float] | None:
    """Best-effort embedding via Ollama. Returns None on failure."""
    try:
        from d4bl.infra.vector_store import get_vector_store
        return await get_vector_store().generate_embedding(content)
    except Exception:
        logger.warning("Embedding generation failed, chunk will have NULL embedding", exc_info=True)
        return None


def _extract_crawl_items(research_data: dict) -> list[dict]:
    """Extract individual crawl result items from research_data findings."""
    items: list[dict] = []
    for finding in research_data.get("research_findings", []):
        content = finding.get("content", "")
        if not content or not content.strip().startswith("{"):
            continue
        try:
            crawl_data = json.loads(content)
            for result in crawl_data.get("results", []):
                url = result.get("url", "").strip()
                page_text = result.get("extracted_content") or result.get("content", "")
                if url and page_text and page_text.strip():
                    items.append({
                        "url": url,
                        "content": page_text.strip(),
                        "title": result.get("title"),
                        "metadata": result.get("metadata") or {},
                    })
        except (json.JSONDecodeError, TypeError, KeyError):
            continue
    return items


async def persist_research_documents(
    job_id: UUID,
    research_data: dict,
    db: AsyncSession,
) -> int:
    """Extract and persist documents from a completed research job.

    Returns count of new documents created.
    """
    try:
        return await _persist_documents(job_id, research_data, db)
    except Exception:
        logger.warning("Failed to persist research documents for job %s", job_id, exc_info=True)
        return 0


async def _persist_documents(
    job_id: UUID,
    research_data: dict,
    db: AsyncSession,
) -> int:
    """Internal implementation — caller handles exceptions."""
    items = _extract_crawl_items(research_data)
    if not items:
        return 0

    # Deduplicate within batch
    seen: dict[str, dict] = {}
    for item in items:
        normalized = normalize_url(item["url"])
        if normalized not in seen:
            seen[normalized] = item

    if not seen:
        return 0

    # Deduplicate against existing documents
    normalized_urls = list(seen.keys())
    result = await db.execute(
        select(Document.source_url).where(Document.source_url.in_(normalized_urls))
    )
    existing_urls = set(result.scalars().all())
    new_items = {url: item for url, item in seen.items() if url not in existing_urls}

    if not new_items:
        return 0

    doc_count = 0
    for normalized, item in new_items.items():
        doc = Document(
            title=item.get("title"),
            source_url=normalized,
            content_type="scraped",
            source_key="research_job",
            job_id=job_id,
            extra_metadata=item.get("metadata") or {},
        )
        db.add(doc)
        await db.flush()

        chunks = chunk_text(item["content"])
        embeddings: list[tuple[int, list[float]]] = []
        chunk_objs: list[DocumentChunk] = []
        for idx, (chunk_content, token_count) in enumerate(chunks):
            embedding = await _try_embed(chunk_content)
            chunk_obj = DocumentChunk(
                document_id=doc.id,
                content=chunk_content,
                chunk_index=idx,
                token_count=token_count,
            )
            db.add(chunk_obj)
            chunk_objs.append(chunk_obj)
            if embedding:
                embeddings.append((idx, embedding))

        await db.flush()  # Single flush for all chunks

        for idx, embedding in embeddings:
            formatted = "[" + ",".join(str(x) for x in embedding) + "]"
            await db.execute(
                sa_text("UPDATE document_chunks SET embedding = CAST(:emb AS vector) WHERE id = CAST(:id AS uuid)"),
                {"emb": formatted, "id": str(chunk_objs[idx].id)},
            )

        doc_count += 1

    await db.commit()
    return doc_count
