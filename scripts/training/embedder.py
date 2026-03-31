"""Batch embedding utility for the document layer.

Calls Ollama mxbai-embed-large to generate 1024-dim vectors.
Reuses the same model and truncation logic as VectorStore.
"""

from __future__ import annotations

import asyncio
import logging
import os

import aiohttp

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "mxbai-embed-large"
EMBEDDING_DIM = 1024
MAX_TEXT_LENGTH = 6000


def format_embedding_for_pg(embedding: list[float]) -> str:
    """Format an embedding list as a pgvector-compatible string."""
    return "[" + ",".join(str(x) for x in embedding) + "]"


async def _embed_single(
    session: aiohttp.ClientSession,
    text: str,
    ollama_url: str,
) -> list[float]:
    """Generate a single embedding via Ollama API."""
    if len(text) > MAX_TEXT_LENGTH:
        text = text[:MAX_TEXT_LENGTH]

    async with session.post(
        f"{ollama_url}/api/embeddings",
        json={"model": EMBEDDING_MODEL, "prompt": text},
        timeout=aiohttp.ClientTimeout(total=30),
    ) as response:
        if response.status != 200:
            body = await response.text()
            raise RuntimeError(f"Ollama embedding API returned {response.status}: {body}")
        result = await response.json()

    embedding = result.get("embedding")
    if not embedding:
        raise ValueError("No embedding in Ollama response")
    if len(embedding) != EMBEDDING_DIM:
        raise ValueError(
            f"Embedding dimension mismatch: expected {EMBEDDING_DIM}, got {len(embedding)}"
        )
    return embedding


async def batch_embed(
    texts: list[str],
    ollama_url: str | None = None,
    max_concurrency: int = 8,
) -> list[list[float]]:
    """Generate embeddings for a list of texts with bounded concurrency.

    Args:
        texts: List of text strings to embed.
        ollama_url: Ollama base URL (defaults to OLLAMA_BASE_URL env or localhost:11434).
        max_concurrency: Maximum concurrent Ollama requests.

    Returns:
        List of embedding vectors (same order as input texts).
    """
    if max_concurrency <= 0:
        raise ValueError(f"max_concurrency must be positive, got {max_concurrency}")

    if ollama_url is None:
        ollama_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")

    sem = asyncio.Semaphore(max_concurrency)

    async def _limited(session: aiohttp.ClientSession, text: str) -> list[float]:
        async with sem:
            return await _embed_single(session, text, ollama_url)

    async with aiohttp.ClientSession() as session:
        return list(await asyncio.gather(*[_limited(session, t) for t in texts]))
