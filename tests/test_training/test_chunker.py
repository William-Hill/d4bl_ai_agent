"""Tests for sentence-aware text chunker."""

from scripts.training.chunker import chunk_text


class TestChunkText:
    def test_short_text_single_chunk(self):
        text = "This is a short sentence."
        chunks = chunk_text(text, target_tokens=500)
        assert len(chunks) == 1
        assert chunks[0]["content"] == "This is a short sentence."
        assert chunks[0]["chunk_index"] == 0
        assert chunks[0]["token_count"] > 0

    def test_splits_on_sentence_boundary(self):
        sentences = [
            "Sentence number one. ",
            "Sentence number two. ",
            "Sentence number three. ",
            "Sentence number four. ",
        ]
        text = "".join(sentences)
        chunks = chunk_text(text, target_tokens=10)
        assert len(chunks) >= 2
        for chunk in chunks:
            content = chunk["content"].strip()
            assert content.endswith("."), f"Chunk does not end at sentence boundary: {content!r}"

    def test_chunk_indices_sequential(self):
        text = "First sentence. Second sentence. Third sentence. Fourth sentence. Fifth sentence."
        chunks = chunk_text(text, target_tokens=8)
        indices = [c["chunk_index"] for c in chunks]
        assert indices == list(range(len(chunks)))

    def test_token_count_populated(self):
        text = "Hello world. This is a test."
        chunks = chunk_text(text, target_tokens=500)
        assert all(c["token_count"] > 0 for c in chunks)

    def test_empty_text_returns_empty(self):
        assert chunk_text("", target_tokens=500) == []
        assert chunk_text("   ", target_tokens=500) == []

    def test_preserves_all_content(self):
        text = "Alpha bravo. Charlie delta. Echo foxtrot."
        chunks = chunk_text(text, target_tokens=8)
        reconstructed = " ".join(c["content"] for c in chunks)
        for word in ["Alpha", "bravo", "Charlie", "delta", "Echo", "foxtrot"]:
            assert word in reconstructed

    def test_overlap_adds_context(self):
        text = "First sentence. Second sentence. Third sentence. Fourth sentence."
        chunks_no_overlap = chunk_text(text, target_tokens=8, overlap_tokens=0)
        chunks_with_overlap = chunk_text(text, target_tokens=8, overlap_tokens=4)
        if len(chunks_with_overlap) > 1:
            assert len(chunks_with_overlap) >= len(chunks_no_overlap)

    def test_metadata_includes_boundary_type(self):
        text = "First sentence. Second sentence. Third sentence. Fourth sentence."
        chunks = chunk_text(text, target_tokens=8)
        assert all("boundary" in c.get("metadata", {}) for c in chunks)
        # Boundary is "sentence" for mid-chunks, "end" for the last chunk
        if len(chunks) > 1:
            assert chunks[-1]["metadata"]["boundary"] == "end"
            assert chunks[0]["metadata"]["boundary"] == "sentence"
