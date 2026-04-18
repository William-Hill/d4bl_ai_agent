"""Tests for document_processing extractors, chunker, and approve flow."""

from __future__ import annotations

import io
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from docx import Document as DocxDocument
from pypdf import PdfWriter

from d4bl.services.document_processing.approve import (
    ProcessingError,
    process_document_upload,
)
from d4bl.services.document_processing.chunker import (
    DEFAULT_CHUNK_SIZE,
    DEFAULT_OVERLAP,
    MIN_CHUNK_SIZE,
    chunk_text,
)
from d4bl.services.document_processing.extractors import (
    ExtractionError,
    extract_docx,
    extract_pdf,
)


def _make_docx_bytes(paragraphs: list[str]) -> bytes:
    buf = io.BytesIO()
    doc = DocxDocument()
    for p in paragraphs:
        doc.add_paragraph(p)
    doc.save(buf)
    return buf.getvalue()


class TestExtractPdf:
    def test_extracts_text_from_valid_pdf(self, make_pdf_bytes):
        pdf_bytes = make_pdf_bytes([
            "The racial wealth gap has widened over the past decade.",
            "Black homeownership rates trail white homeownership by 30 points.",
        ])
        text = extract_pdf(pdf_bytes)
        assert "racial wealth gap" in text
        assert "homeownership" in text

    def test_rejects_malformed_pdf(self):
        with pytest.raises(ExtractionError, match="Could not open PDF"):
            extract_pdf(b"not a pdf")

    def test_rejects_pdf_with_no_text(self):
        writer = PdfWriter()
        writer.add_blank_page(width=72, height=72)
        buf = io.BytesIO()
        writer.write(buf)
        with pytest.raises(ExtractionError, match="no usable text"):
            extract_pdf(buf.getvalue())


class TestExtractDocx:
    def test_extracts_text_from_valid_docx(self):
        docx_bytes = _make_docx_bytes([
            "Environmental racism concentrates hazardous waste near Black communities.",
            "Policy levers include zoning reform and cumulative impact analysis.",
        ])
        text = extract_docx(docx_bytes)
        assert "Environmental racism" in text
        assert "zoning reform" in text

    def test_rejects_malformed_docx(self):
        with pytest.raises(ExtractionError, match="Could not open DOCX"):
            extract_docx(b"not a docx")

    def test_rejects_empty_docx(self):
        docx_bytes = _make_docx_bytes([])
        with pytest.raises(ExtractionError, match="no extractable text"):
            extract_docx(docx_bytes)


class TestChunkText:
    def test_empty_input_returns_empty_list(self):
        assert chunk_text("") == []
        assert chunk_text("   \n\n  ") == []

    def test_short_input_returns_single_chunk(self):
        text = "one short paragraph"
        assert chunk_text(text) == [text]

    def test_respects_chunk_size_for_long_paragraphs(self):
        para = "a" * 2000
        chunks = chunk_text(para, chunk_size=500, overlap=100)
        assert all(len(c) <= 500 for c in chunks)
        assert len(chunks) >= 4

    def test_packs_short_paragraphs_together(self):
        paras = ["paragraph one.", "paragraph two.", "paragraph three."]
        chunks = chunk_text("\n\n".join(paras), chunk_size=500, overlap=100)
        assert len(chunks) == 1
        assert "paragraph one" in chunks[0]
        assert "paragraph three" in chunks[0]

    def test_overlap_preserves_context_across_chunks(self):
        """Rolled-over chunks carry as much tail context as fits within
        chunk_size. The full overlap is ideal; a shorter tail is acceptable
        when the next paragraph would push the chunk over the limit."""
        paras = [
            "A" * 200,
            "B" * 200,
            "C" * 200,
        ]
        chunks = chunk_text("\n\n".join(paras), chunk_size=250, overlap=50)
        assert len(chunks) >= 2
        # Some As from the end of chunk 0 must appear at the start of chunk 1.
        assert chunks[1].startswith("A")
        assert chunks[0][-1] == "A"

    def test_preserves_chunk_ordering(self):
        parts = ["alpha", "beta", "gamma", "delta", "epsilon"]
        text = "\n\n".join(p * 100 for p in parts)
        chunks = chunk_text(text, chunk_size=300, overlap=50)
        joined = " ".join(chunks)
        for i in range(len(parts) - 1):
            assert joined.find(parts[i]) < joined.find(parts[i + 1])

    def test_exactly_min_chunk_size_is_single_chunk(self):
        text = "x" * MIN_CHUNK_SIZE
        assert chunk_text(text) == [text]

    def test_defaults_are_reasonable(self):
        assert DEFAULT_CHUNK_SIZE > DEFAULT_OVERLAP > 0

    def test_rejects_non_positive_chunk_size(self):
        with pytest.raises(ValueError, match="chunk_size must be positive"):
            chunk_text("some text", chunk_size=0, overlap=0)

    def test_rejects_negative_overlap(self):
        with pytest.raises(ValueError, match="overlap must be non-negative"):
            chunk_text("some text", chunk_size=100, overlap=-1)

    def test_rejects_overlap_geq_chunk_size(self):
        """overlap >= chunk_size raises instead of exploding to O(n) chunks."""
        with pytest.raises(ValueError, match="strictly less than chunk_size"):
            chunk_text("x" * 2000, chunk_size=100, overlap=500)

    def test_overlap_carries_across_hard_split_seam(self):
        """After hard-splitting a big paragraph, the next paragraph's chunk
        carries the tail of the hard-split chunk so context isn't lost."""
        big_para = "A" * 1000
        follow = "B paragraph content that continues the discussion"
        text = big_para + "\n\n" + follow
        chunks = chunk_text(text, chunk_size=400, overlap=80)
        # The follow-up chunk should contain some trailing As from the
        # hard-split tail in addition to the new paragraph text.
        assert any("A" * 20 in c and "B paragraph" in c for c in chunks)

    def test_no_overlap_only_chunk_at_eof_after_hard_split(self):
        """A document ending on a hard-split paragraph must not emit a
        trailing chunk that is just the overlap tail — that would be an
        embedded duplicate that skews retrieval."""
        big_para = "A" * 1000
        chunks = chunk_text(big_para, chunk_size=400, overlap=80)
        # No chunk should be purely the overlap tail from a previous chunk
        # (that would mean the carryover leaked into the output).
        for i in range(len(chunks) - 1):
            tail = chunks[i][-80:]
            assert chunks[i + 1] != tail, (
                f"Chunk {i + 1} is just the overlap tail of chunk {i}"
            )

    def test_no_overlap_only_chunk_between_back_to_back_hard_splits(self):
        """Two oversized paragraphs in a row must not produce an overlap-only
        chunk between them."""
        big_a = "A" * 1000
        big_b = "B" * 1000
        chunks = chunk_text(big_a + "\n\n" + big_b, chunk_size=400, overlap=80)
        # No chunk should consist purely of one character repeated for
        # exactly overlap chars (which is what the old bug would produce).
        overlap_only = [c for c in chunks if c == "A" * 80 or c == "B" * 80]
        assert overlap_only == []

    def test_rollover_chunk_never_exceeds_chunk_size(self):
        """Flushing a near-full buffer before a near-full paragraph must not
        emit a chunk larger than chunk_size even with overlap carried."""
        # buffer fills with 3 paragraphs of ~100 chars (under 400), then a
        # 300-char paragraph triggers flush; carried overlap + 300 should be
        # capped at chunk_size.
        text = "\n\n".join([
            "A" * 100,
            "A" * 100,
            "A" * 100,
            "B" * 300,
        ])
        chunks = chunk_text(text, chunk_size=400, overlap=100)
        assert all(len(c) <= 400 for c in chunks), [len(c) for c in chunks]

    def test_hard_split_does_not_emit_redundant_trailing_window(self):
        """_hard_split must stop once a window reaches EOF — otherwise a
        40-char tail fully covered by the previous window gets duplicated."""
        text = "A" * 1000
        chunks = chunk_text(text, chunk_size=400, overlap=80)
        # With stride=320 and chunk_size=400, we expect 3 windows
        # [0:400], [320:720], [640:1000]. A 4th window [960:1000] would be
        # a 40-char duplicate — fully contained in the previous window.
        assert len(chunks) == 3
        assert chunks[-1] == text[640:1000]


def _mock_upload_row(
    *,
    upload_type: str = "document",
    full_text: str | None = "Some extracted text about racial equity.\n\nMore content.",
    title: str = "Test Doc",
    uploader_email: str = "alice@d4bl.org",
    filename: str = "doc.pdf",
):
    mapping = {
        "id": uuid4(),
        "upload_type": upload_type,
        "original_filename": filename,
        "metadata": {
            "title": title,
            "document_type": "report",
            "topic_tags": ["equity"],
            "url": None,
            "full_text": full_text,
        },
        "uploader_email": uploader_email,
    }
    result = MagicMock()
    result.mappings.return_value.first.return_value = mapping
    return result


class TestProcessDocumentUpload:

    @pytest.mark.asyncio
    @patch("d4bl.services.document_processing.approve.get_vector_store")
    async def test_happy_path_chunks_and_indexes(self, mock_get_store):
        fake_store = MagicMock()
        fake_store.store_staff_document = AsyncMock(return_value=[uuid4(), uuid4()])
        mock_get_store.return_value = fake_store

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_mock_upload_row())

        count = await process_document_upload(db, uuid4())

        assert count == 2
        fake_store.store_staff_document.assert_awaited_once()
        call_kwargs = fake_store.store_staff_document.await_args.kwargs
        assert call_kwargs["metadata_base"]["title"] == "Test Doc"
        assert call_kwargs["metadata_base"]["uploader_email"] == "alice@d4bl.org"
        assert call_kwargs["chunks"]  # non-empty

    @pytest.mark.asyncio
    async def test_missing_upload_raises(self):
        db = AsyncMock()
        result = MagicMock()
        result.mappings.return_value.first.return_value = None
        db.execute = AsyncMock(return_value=result)

        with pytest.raises(ProcessingError, match="not found"):
            await process_document_upload(db, uuid4())

    @pytest.mark.asyncio
    async def test_non_document_upload_raises(self):
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_mock_upload_row(upload_type="datasource"))

        with pytest.raises(ProcessingError, match="not a document"):
            await process_document_upload(db, uuid4())

    @pytest.mark.asyncio
    async def test_missing_full_text_raises(self):
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_mock_upload_row(full_text=None))

        with pytest.raises(ProcessingError, match="no extracted text"):
            await process_document_upload(db, uuid4())

    @pytest.mark.asyncio
    async def test_whitespace_only_full_text_raises(self):
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_mock_upload_row(full_text="   \n\n  "))

        with pytest.raises(ProcessingError, match="no extracted text"):
            await process_document_upload(db, uuid4())
