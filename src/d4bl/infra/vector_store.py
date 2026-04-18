"""
Vector storage service for saving scraped content to Supabase with embeddings.
"""
from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID

import aiohttp
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from d4bl.settings import get_settings

logger = logging.getLogger(__name__)


class VectorStore:
    """Service for storing and retrieving scraped content with vector embeddings."""

    def __init__(self, ollama_base_url: str | None = None, embedder_model: str = "mxbai-embed-large") -> None:
        """
        Initialize the vector store.
        
        Args:
            ollama_base_url: Base URL for Ollama API (defaults to env var or settings)
            embedder_model: Model name for embeddings (default: mxbai-embed-large)
        """
        settings = get_settings()
        self.ollama_base_url = (ollama_base_url or settings.ollama_base_url).rstrip("/")
        self.embedder_model = embedder_model
        self.embedding_dimension = 1024  # mxbai-embed-large produces 1024-dimensional vectors

    def _format_embedding(self, embedding: list[float]) -> str:
        """Format embedding list as a pgvector-compatible string."""
        return '[' + ','.join(str(x) for x in embedding) + ']'

    @staticmethod
    def _row_to_content_dict(row) -> dict[str, Any]:
        """Convert a scraped_content_vectors row (mapping) to a dict."""
        return {
            "id": str(row["id"]) if row["id"] else None,
            "job_id": str(row["job_id"]) if row["job_id"] else None,
            "url": row["url"],
            "content": row["content"],
            "content_type": row["content_type"],
            "metadata": row["metadata"] if row["metadata"] else {},
            "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        }

    async def generate_embedding(self, text_input: str) -> list[float]:
        """
        Generate embedding vector for the given text using Ollama.

        Args:
            text_input: Text to embed

        Returns:
            List of floats representing the embedding vector
        """
        try:
            if len(text_input) > 6000:
                text_input = text_input[:6000]
                logger.warning("Text truncated to 6000 characters for embedding")

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.ollama_base_url}/api/embeddings",
                    json={"model": self.embedder_model, "prompt": text_input},
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as response:
                    if response.status != 200:
                        body = await response.text()
                        error_msg = f"Ollama embedding API returned {response.status}: {body}"
                        logger.error(error_msg)
                        raise RuntimeError(error_msg)

                    result = await response.json()

            embedding = result.get("embedding")

            if not embedding:
                raise ValueError("No embedding in Ollama response")

            if len(embedding) != self.embedding_dimension:
                logger.warning(
                    "Embedding dimension mismatch: expected %s, got %s. "
                    "Check embedder model configuration.",
                    self.embedding_dimension,
                    len(embedding),
                )

            return embedding

        except aiohttp.ClientError as e:
            logger.error("Failed to generate embedding: %s", e)
            raise RuntimeError(f"Embedding generation failed: {str(e)}") from e
        except Exception as e:
            logger.error("Unexpected error generating embedding: %s", e)
            raise

    async def store_scraped_content(
        self,
        db: AsyncSession,
        job_id: UUID,
        url: str,
        content: str,
        content_type: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> UUID | None:
        """
        Store scraped content with its embedding in the vector database.
        
        Args:
            db: Database session
            job_id: Research job ID this content belongs to
            url: Source URL of the content
            content: Text content to store
            content_type: Type of content (e.g., 'html', 'pdf', 'markdown')
            metadata: Additional metadata to store
            
        Returns:
            UUID of the stored record, or None if storage failed
        """
        if not content or len(content.strip()) < 10:
            logger.warning("Skipping storage: content too short or empty for URL: %s", url)
            return None

        try:
            # Generate embedding
            logger.debug("Generating embedding for URL: %s", url)
            embedding = await self.generate_embedding(content)

            # Prepare metadata
            metadata_json = json.dumps(metadata or {})

            # Insert into database
            embedding_str = self._format_embedding(embedding)

            query = text("""
                INSERT INTO scraped_content_vectors
                (job_id, url, content, content_type, metadata, embedding, source)
                VALUES (:job_id, :url, :content, :content_type, CAST(:metadata AS jsonb), CAST(:embedding AS vector), 'research_job')
                RETURNING id
            """)

            result = await db.execute(
                query,
                {
                    "job_id": str(job_id),
                    "url": url,
                    "content": content,
                    "content_type": content_type,
                    "metadata": metadata_json,
                    "embedding": embedding_str,
                }
            )

            record_id = result.scalar_one()
            await db.commit()

            logger.info("Stored scraped content in vector DB: %s (URL: %s)", record_id, url)
            return record_id

        except Exception as e:
            logger.error("Failed to store scraped content in vector DB: %s", e, exc_info=True)
            await db.rollback()
            return None

    async def store_batch(
        self,
        db: AsyncSession,
        job_id: UUID,
        items: list[dict[str, Any]],
    ) -> int:
        """
        Store multiple scraped content items in batch.
        
        Args:
            db: Database session
            job_id: Research job ID
            items: List of dicts with keys: url, content, content_type (optional), metadata (optional)
            
        Returns:
            Number of successfully stored items
        """
        stored_count = 0

        for item in items:
            record_id = await self.store_scraped_content(
                db=db,
                job_id=job_id,
                url=item.get("url", ""),
                content=item.get("content", ""),
                content_type=item.get("content_type"),
                metadata=item.get("metadata"),
            )
            if record_id:
                stored_count += 1

        logger.info("Stored %s/%s items in vector DB", stored_count, len(items))
        return stored_count

    async def store_staff_document(
        self,
        db: AsyncSession,
        upload_id: UUID,
        chunks: list[str],
        metadata_base: dict[str, Any],
    ) -> list[UUID]:
        """Store staff-uploaded document chunks with embeddings.

        Each chunk becomes one row in scraped_content_vectors with
        source='staff_upload' and job_id=NULL. The per-chunk metadata
        merges metadata_base with chunk_index/total_chunks/upload_id so
        agents can cite the origin and reconstruct document order.

        Args:
            db: Database session
            upload_id: Upload row this document came from
            chunks: Output of chunker.chunk_text — one entry per chunk
            metadata_base: Shared metadata (title, uploader_email,
                source_url, original_filename, etc.)

        Returns:
            List of inserted row UUIDs in chunk order. Empty list if
            no chunks were provided.
        """
        if not chunks:
            return []

        url = metadata_base.get("source_url")
        content_type = metadata_base.get("content_type", "document")
        total = len(chunks)
        inserted: list[UUID] = []

        # Idempotent: drop any existing chunks for this upload before
        # inserting the new set. Protects against duplicates after a
        # partial failure (e.g., chunks committed, status update failed)
        # and makes retry safe without requiring caller cleanup.
        delete_existing = text("""
            DELETE FROM scraped_content_vectors
            WHERE source = 'staff_upload'
              AND metadata ->> 'upload_id' = :upload_id
        """)

        insert_chunk = text("""
            INSERT INTO scraped_content_vectors
            (job_id, url, content, content_type, metadata, embedding, source)
            VALUES (NULL, :url, :content, :content_type, CAST(:metadata AS jsonb), CAST(:embedding AS vector), 'staff_upload')
            RETURNING id
        """)

        try:
            await db.execute(delete_existing, {"upload_id": str(upload_id)})

            for i, chunk in enumerate(chunks):
                embedding = await self.generate_embedding(chunk)
                row_metadata = {
                    **metadata_base,
                    "upload_id": str(upload_id),
                    "chunk_index": i,
                    "total_chunks": total,
                    "source_type": "staff_upload",
                }
                result = await db.execute(
                    insert_chunk,
                    {
                        "url": url,
                        "content": chunk,
                        "content_type": content_type,
                        "metadata": json.dumps(row_metadata),
                        "embedding": self._format_embedding(embedding),
                    },
                )
                inserted.append(result.scalar_one())

            await db.commit()
            logger.info(
                "Stored staff document upload_id=%s as %d chunks",
                upload_id, total,
            )
            return inserted

        except Exception:
            logger.exception("Failed to store staff document upload_id=%s", upload_id)
            await db.rollback()
            raise

    async def search_similar(
        self,
        db: AsyncSession,
        query_text: str,
        job_id: UUID | str | None = None,
        limit: int = 10,
        similarity_threshold: float = 0.7,
    ) -> list[dict[str, Any]]:
        """
        Search for similar content using vector similarity.
        
        Args:
            db: Database session
            query_text: Text to search for
            job_id: Optional job ID to filter results
            limit: Maximum number of results
            similarity_threshold: Minimum cosine similarity (0-1)
            
        Returns:
            List of matching records with similarity scores
        """
        try:
            query_embedding = await self.generate_embedding(query_text)
            query_embedding_str = self._format_embedding(query_embedding)

            # Build query with optional job_id filter
            where_clauses = [
                "1 - (embedding <=> CAST(:query_embedding AS vector)) >= :threshold"
            ]
            params: dict[str, Any] = {
                "query_embedding": query_embedding_str,
                "threshold": similarity_threshold,
                "limit": limit,
            }

            if job_id:
                where_clauses.append("job_id = :job_id")
                params["job_id"] = str(job_id)

            where_sql = " AND ".join(where_clauses)

            query = text(f"""
                SELECT
                    id, job_id, url, content, content_type, metadata, created_at,
                    1 - (embedding <=> CAST(:query_embedding AS vector)) as similarity
                FROM scraped_content_vectors
                WHERE {where_sql}
                ORDER BY embedding <=> CAST(:query_embedding AS vector)
                LIMIT :limit
            """)

            result = await db.execute(query, params)

            results = []
            for row in result.mappings():
                d = self._row_to_content_dict(row)
                d["similarity"] = float(row["similarity"])
                results.append(d)

            logger.info("Found %s similar results for query", len(results))
            return results

        except Exception as e:
            logger.error("Failed to search similar content: %s", e, exc_info=True)
            return []

    async def get_by_job_id(
        self,
        db: AsyncSession,
        job_id: UUID,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """
        Get all scraped content for a specific job.
        
        Args:
            db: Database session
            job_id: Research job ID
            limit: Optional limit on number of results
            
        Returns:
            List of records
        """
        try:
            limit_clause = "LIMIT :limit" if limit is not None else ""
            query = text(f"""
                SELECT id, job_id, url, content, content_type, metadata, created_at
                FROM scraped_content_vectors
                WHERE job_id = :job_id
                ORDER BY created_at DESC
                {limit_clause}
            """)

            params: dict[str, Any] = {"job_id": str(job_id)}
            if limit is not None:
                params["limit"] = limit

            result = await db.execute(query, params)
            return [self._row_to_content_dict(row) for row in result.mappings()]

        except Exception as e:
            logger.error("Failed to get content by job_id: %s", e, exc_info=True)
            return []


# Global instance
_vector_store: VectorStore | None = None


def get_vector_store() -> VectorStore:
    """Get or create the global vector store instance."""
    global _vector_store
    if _vector_store is None:
        _vector_store = VectorStore()
    return _vector_store

