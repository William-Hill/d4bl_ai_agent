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
        paras = [
            "A" * 200,
            "B" * 200,
            "C" * 200,
        ]
        chunks = chunk_text("\n\n".join(paras), chunk_size=250, overlap=50)
        assert len(chunks) >= 2
        tail_of_first = chunks[0][-50:]
        assert tail_of_first in chunks[1]

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
