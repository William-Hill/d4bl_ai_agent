"""Sentence-aware text chunker for the document layer.

Splits text on sentence boundaries with configurable target token count
and optional overlap for context continuity in RAG.
"""

from __future__ import annotations

import re


def _estimate_tokens(text: str) -> int:
    """Estimate token count using whitespace splitting (≈1.3 tokens per word)."""
    return max(1, int(len(text.split()) * 1.3))


def _split_sentences(text: str) -> list[str]:
    """Split text into sentences, preserving trailing whitespace."""
    parts = re.split(r'(?<=[.!?])\s+', text.strip())
    return [p for p in parts if p.strip()]


def chunk_text(
    text: str,
    target_tokens: int = 500,
    overlap_tokens: int = 0,
) -> list[dict]:
    """Split text into chunks at sentence boundaries.

    Args:
        text: Input text to chunk.
        target_tokens: Target token count per chunk (approximate).
        overlap_tokens: Number of tokens to overlap between consecutive chunks.

    Returns:
        List of chunk dicts with keys: content, chunk_index, token_count, metadata.
    """
    if not text or not text.strip():
        return []

    sentences = _split_sentences(text)
    if not sentences:
        return []

    chunks: list[dict] = []
    current_sentences: list[str] = []
    current_tokens = 0
    chunk_index = 0

    for sentence in sentences:
        sent_tokens = _estimate_tokens(sentence)

        if current_sentences and current_tokens + sent_tokens > target_tokens:
            content = " ".join(current_sentences)
            is_paragraph = "\n\n" in content
            chunks.append({
                "content": content,
                "chunk_index": chunk_index,
                "token_count": _estimate_tokens(content),
                "metadata": {"boundary": "paragraph" if is_paragraph else "sentence"},
            })
            chunk_index += 1

            if overlap_tokens > 0:
                overlap_sents: list[str] = []
                overlap_count = 0
                for s in reversed(current_sentences):
                    s_tokens = _estimate_tokens(s)
                    if overlap_count + s_tokens > overlap_tokens:
                        break
                    overlap_sents.insert(0, s)
                    overlap_count += s_tokens
                current_sentences = overlap_sents
                current_tokens = overlap_count
            else:
                current_sentences = []
                current_tokens = 0

        current_sentences.append(sentence)
        current_tokens += sent_tokens

    if current_sentences:
        content = " ".join(current_sentences)
        chunks.append({
            "content": content,
            "chunk_index": chunk_index,
            "token_count": _estimate_tokens(content),
            "metadata": {"boundary": "end"},
        })

    return chunks
