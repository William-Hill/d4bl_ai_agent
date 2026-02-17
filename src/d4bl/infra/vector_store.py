"""
Vector storage service for saving scraped content to Supabase with embeddings.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional
from uuid import UUID

import requests
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from d4bl.settings import get_settings

logger = logging.getLogger(__name__)


class VectorStore:
    """Service for storing and retrieving scraped content with vector embeddings."""

    def __init__(self, ollama_base_url: Optional[str] = None, embedder_model: str = "mxbai-embed-large"):
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

    async def generate_embedding(self, text: str) -> List[float]:
        """
        Generate embedding vector for the given text using Ollama.
        
        Args:
            text: Text to embed
            
        Returns:
            List of floats representing the embedding vector
        """
        try:
            # Truncate text if too long (most embedding models have token limits)
            # mxbai-embed-large can handle up to ~8192 tokens, so we'll limit to ~6000 chars
            if len(text) > 6000:
                text = text[:6000]
                logger.warning("Text truncated to 6000 characters for embedding")

            response = requests.post(
                f"{self.ollama_base_url}/api/embeddings",
                json={
                    "model": self.embedder_model,
                    "prompt": text,
                },
                timeout=30,
            )

            if response.status_code != 200:
                error_msg = f"Ollama embedding API returned {response.status_code}: {response.text}"
                logger.error(error_msg)
                raise RuntimeError(error_msg)

            result = response.json()
            embedding = result.get("embedding")
            
            if not embedding:
                raise ValueError("No embedding in Ollama response")
            
            if len(embedding) != self.embedding_dimension:
                logger.warning(
                    "Embedding dimension mismatch: expected %s, got %s",
                    self.embedding_dimension,
                    len(embedding)
                )
                # Adjust dimension if needed (though this shouldn't happen)
                self.embedding_dimension = len(embedding)

            return embedding

        except requests.exceptions.RequestException as e:
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
        content_type: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[UUID]:
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
            # pgvector expects the embedding as a string in format: '[0.1, 0.2, ...]'
            embedding_str = '[' + ','.join(str(x) for x in embedding) + ']'
            
            query = text("""
                INSERT INTO scraped_content_vectors
                (job_id, url, content, content_type, metadata, embedding)
                VALUES (:job_id, :url, :content, :content_type, CAST(:metadata AS jsonb), CAST(:embedding AS vector))
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
        items: List[Dict[str, Any]],
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

    async def search_similar(
        self,
        db: AsyncSession,
        query_text: str,
        job_id: Optional[UUID] = None,
        limit: int = 10,
        similarity_threshold: float = 0.7,
    ) -> List[Dict[str, Any]]:
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
            # Generate embedding for query
            query_embedding = await self.generate_embedding(query_text)
            
            # Format embedding for pgvector
            query_embedding_str = '[' + ','.join(str(x) for x in query_embedding) + ']'

            # Build query
            if job_id:
                query = text("""
                    SELECT 
                        id,
                        job_id,
                        url,
                        content,
                        content_type,
                        metadata,
                        created_at,
                        1 - (embedding <=> CAST(:query_embedding AS vector)) as similarity
                    FROM scraped_content_vectors
                    WHERE job_id = :job_id
                        AND 1 - (embedding <=> CAST(:query_embedding AS vector)) >= :threshold
                    ORDER BY embedding <=> CAST(:query_embedding AS vector)
                    LIMIT :limit
                """)
                params = {
                    "query_embedding": query_embedding_str,
                    "job_id": str(job_id),
                    "threshold": similarity_threshold,
                    "limit": limit,
                }
            else:
                query = text("""
                    SELECT 
                        id,
                        job_id,
                        url,
                        content,
                        content_type,
                        metadata,
                        created_at,
                        1 - (embedding <=> CAST(:query_embedding AS vector)) as similarity
                    FROM scraped_content_vectors
                    WHERE 1 - (embedding <=> CAST(:query_embedding AS vector)) >= :threshold
                    ORDER BY embedding <=> CAST(:query_embedding AS vector)
                    LIMIT :limit
                """)
                params = {
                    "query_embedding": query_embedding_str,
                    "threshold": similarity_threshold,
                    "limit": limit,
                }

            result = await db.execute(query, params)
            rows = result.fetchall()

            # Convert to list of dicts
            results = []
            for row in rows:
                results.append({
                    "id": str(row[0]),
                    "job_id": str(row[1]) if row[1] else None,
                    "url": row[2],
                    "content": row[3],
                    "content_type": row[4],
                    "metadata": row[5] if row[5] else {},
                    "created_at": row[6].isoformat() if row[6] else None,
                    "similarity": float(row[7]),
                })

            logger.info("Found %s similar results for query", len(results))
            return results

        except Exception as e:
            logger.error("Failed to search similar content: %s", e, exc_info=True)
            return []

    async def get_by_job_id(
        self,
        db: AsyncSession,
        job_id: UUID,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
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
            query = text("""
                SELECT 
                    id,
                    job_id,
                    url,
                    content,
                    content_type,
                    metadata,
                    created_at
                FROM scraped_content_vectors
                WHERE job_id = :job_id
                ORDER BY created_at DESC
            """)
            
            params = {"job_id": str(job_id)}
            if limit:
                query = text(str(query) + " LIMIT :limit")
                params["limit"] = limit

            result = await db.execute(query, params)
            rows = result.fetchall()

            results = []
            for row in rows:
                results.append({
                    "id": str(row[0]),
                    "job_id": str(row[1]) if row[1] else None,
                    "url": row[2],
                    "content": row[3],
                    "content_type": row[4],
                    "metadata": row[5] if row[5] else {},
                    "created_at": row[6].isoformat() if row[6] else None,
                })

            return results

        except Exception as e:
            logger.error("Failed to get content by job_id: %s", e, exc_info=True)
            return []


# Global instance
_vector_store: Optional[VectorStore] = None


def get_vector_store() -> VectorStore:
    """Get or create the global vector store instance."""
    global _vector_store
    if _vector_store is None:
        _vector_store = VectorStore()
    return _vector_store

