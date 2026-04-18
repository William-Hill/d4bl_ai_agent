"""Tests for document_processing extractors and chunker."""

from __future__ import annotations

import io

import pytest
from docx import Document as DocxDocument
from pypdf import PdfWriter
from reportlab.pdfgen import canvas

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


def _make_pdf_bytes(lines: list[str]) -> bytes:
    """Build a real PDF in memory using reportlab so pypdf can parse it."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    y = 800
    for line in lines:
        c.drawString(100, y, line)
        y -= 20
    c.save()
    return buf.getvalue()


def _make_docx_bytes(paragraphs: list[str]) -> bytes:
    buf = io.BytesIO()
    doc = DocxDocument()
    for p in paragraphs:
        doc.add_paragraph(p)
    doc.save(buf)
    return buf.getvalue()


class TestExtractPdf:
    def test_extracts_text_from_valid_pdf(self):
        pdf_bytes = _make_pdf_bytes([
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
