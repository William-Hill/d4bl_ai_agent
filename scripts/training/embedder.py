"""Batch embedding utility for the document layer.

Calls Ollama mxbai-embed-large to generate 1024-dim vectors.
Reuses the same model and truncation logic as VectorStore.
"""

from __future__ import annotations

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

    response = await session.post(
        f"{ollama_url}/api/embeddings",
        json={"model": EMBEDDING_MODEL, "prompt": text},
        timeout=aiohttp.ClientTimeout(total=30),
    )
    if response.status != 200:
        body = await response.text()
        raise RuntimeError(f"Ollama embedding API returned {response.status}: {body}")
    result = await response.json()

    embedding = result.get("embedding")
    if not embedding:
        raise ValueError("No embedding in Ollama response")
    return embedding


async def batch_embed(
    texts: list[str],
    ollama_url: str | None = None,
) -> list[list[float]]:
    """Generate embeddings for a list of texts.

    Args:
        texts: List of text strings to embed.
        ollama_url: Ollama base URL (defaults to OLLAMA_BASE_URL env or localhost:11434).

    Returns:
        List of embedding vectors (same order as input texts).
    """
    if ollama_url is None:
        ollama_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")

    embeddings: list[list[float]] = []
    async with aiohttp.ClientSession() as session:
        for text in texts:
            embedding = await _embed_single(session, text, ollama_url)
            embeddings.append(embedding)
    return embeddings
