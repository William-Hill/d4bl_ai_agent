"""Text chunking for embedding.

Documents are split into overlapping chunks so that semantically related
passages stay contiguous and retrieval returns enough context around a hit.
"""

from __future__ import annotations

DEFAULT_CHUNK_SIZE = 500
DEFAULT_OVERLAP = 100
MIN_CHUNK_SIZE = 50


def chunk_text(
    text: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_OVERLAP,
) -> list[str]:
    """Split text into overlapping chunks suitable for embedding.

    Args:
        text: The full document text (post-extraction).
        chunk_size: Target characters per chunk. mxbai-embed-large handles
            up to ~6000 chars, but smaller chunks give more precise retrieval.
        overlap: Characters of tail from the previous chunk prepended to the
            next, so a sentence split across chunk boundaries still appears
            in full in at least one chunk.

    Returns:
        A list of chunks. Empty or whitespace-only input returns [].
        Input shorter than MIN_CHUNK_SIZE is returned as a single chunk.
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if overlap < 0:
        raise ValueError("overlap must be non-negative")
    # Reject degenerate overlap. overlap >= chunk_size forces stride = 1 in
    # hard-split mode, producing O(n) chunks — almost certainly misconfig.
    if overlap >= chunk_size:
        raise ValueError("overlap must be strictly less than chunk_size")

    if not text or not text.strip():
        return []

    stripped = text.strip()
    if len(stripped) <= MIN_CHUNK_SIZE:
        return [stripped]

    paragraphs = [p.strip() for p in stripped.split("\n\n") if p.strip()]

    chunks: list[str] = []
    buffer = ""
    # carryover holds the tail of the last hard-split chunk so the next
    # paragraph can start with that context — but it's never emitted as a
    # standalone chunk (that would create overlap-only duplicates).
    carryover = ""

    for para in paragraphs:
        if carryover:
            para = carryover + "\n\n" + para
            carryover = ""

        if len(para) > chunk_size:
            if buffer:
                chunks.append(buffer)
                buffer = ""
            hard_chunks = _hard_split(para, chunk_size, overlap)
            chunks.extend(hard_chunks)
            carryover = hard_chunks[-1][-overlap:] if overlap and hard_chunks else ""
            continue

        if buffer and len(buffer) + 2 + len(para) > chunk_size:
            chunks.append(buffer)
            buffer = buffer[-overlap:] + "\n\n" + para if overlap else para
        elif buffer:
            buffer = buffer + "\n\n" + para
        else:
            buffer = para

    if buffer:
        chunks.append(buffer)

    return chunks


def _hard_split(text: str, chunk_size: int, overlap: int) -> list[str]:
    """Character-window split for paragraphs larger than chunk_size."""
    stride = max(chunk_size - overlap, 1)
    return [text[i : i + chunk_size] for i in range(0, len(text), stride)]
