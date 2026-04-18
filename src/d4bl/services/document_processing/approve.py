"""Approval-time processing for staff document uploads.

When an admin approves a ``document`` upload, this module reads the
extracted full text that was stashed in metadata at submit time, chunks
it, embeds each chunk via Ollama, and writes one row per chunk into the
vector store.
"""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from d4bl.infra.vector_store import get_vector_store

from .chunker import chunk_text

logger = logging.getLogger(__name__)


class ProcessingError(Exception):
    """Raised when a document upload cannot be processed into the vector store."""


async def process_document_upload(db: AsyncSession, upload_id: UUID) -> int:
    """Chunk, embed, and index a document upload.

    Reads the upload row + uploader email (via profiles join), pulls the
    full extracted text out of ``metadata.full_text``, chunks it, and
    calls ``VectorStore.store_staff_document`` to embed and write one
    row per chunk.

    Args:
        db: Database session.
        upload_id: The Upload.id to process.

    Returns:
        The number of chunks written to the vector store.

    Raises:
        ProcessingError: If the upload is missing, is not a document, or
            has no extractable text. Vector-store and embedding errors
            propagate as-is so the caller can distinguish input problems
            from infrastructure problems.
    """
    result = await db.execute(
        text(
            """
            SELECT u.id, u.upload_type, u.original_filename, u.metadata,
                   p.email AS uploader_email
            FROM uploads u
            LEFT JOIN profiles p ON p.id = u.user_id
            WHERE u.id = CAST(:uid AS uuid)
            """
        ),
        {"uid": str(upload_id)},
    )
    row = result.mappings().first()
    if not row:
        raise ProcessingError(f"Upload {upload_id} not found")
    if row["upload_type"] != "document":
        raise ProcessingError(
            f"Upload {upload_id} is not a document (type={row['upload_type']})"
        )

    metadata = row["metadata"] or {}
    full_text = metadata.get("full_text")
    if not full_text or not full_text.strip():
        raise ProcessingError(
            f"Upload {upload_id} has no extracted text to index"
        )

    chunks = chunk_text(full_text)
    if not chunks:
        raise ProcessingError(
            f"Upload {upload_id} produced no chunks — text may be too short"
        )

    metadata_base = {
        "title": metadata.get("title"),
        "document_type": metadata.get("document_type"),
        "topic_tags": metadata.get("topic_tags"),
        "source_url": metadata.get("url"),
        "original_filename": row["original_filename"],
        "uploader_email": row["uploader_email"],
    }

    store = get_vector_store()
    inserted = await store.store_staff_document(
        db=db,
        upload_id=upload_id,
        chunks=chunks,
        metadata_base=metadata_base,
    )

    logger.info(
        "Processed document upload %s into %d chunks", upload_id, len(inserted)
    )
    return len(inserted)
