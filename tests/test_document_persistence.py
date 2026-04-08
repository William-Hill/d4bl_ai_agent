"""Tests for document persistence from research jobs."""

from __future__ import annotations

import pytest

from d4bl.services.document_persistence import normalize_url


class TestNormalizeUrl:
    """URL normalization strips tracking params, normalizes scheme/host/path."""

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("http://Example.COM/path", "https://example.com/path"),
            ("https://example.com/path/", "https://example.com/path"),
            (
                "https://example.com/page?utm_source=google&utm_medium=cpc&id=123",
                "https://example.com/page?id=123",
            ),
            ("https://example.com/page?fbclid=abc123", "https://example.com/page"),
            ("https://example.com/page?gclid=xyz&ref=twitter", "https://example.com/page"),
            ("https://example.com/page?z=1&a=2", "https://example.com/page?a=2&z=1"),
            (
                "https://api.census.gov/data?get=NAME&for=county:*",
                "https://api.census.gov/data?for=county%3A%2A&get=NAME",
            ),
            ("https://example.com/report", "https://example.com/report"),
            ("https://example.com", "https://example.com"),
            ("https://example.com/", "https://example.com"),
        ],
    )
    def test_normalize_url(self, raw: str, expected: str):
        assert normalize_url(raw) == expected


from d4bl.services.document_persistence import chunk_text


class TestChunkText:
    """Paragraph-based chunking with size cap."""

    def test_empty_content(self):
        assert chunk_text("") == []
        assert chunk_text("   ") == []

    def test_single_short_paragraph(self):
        result = chunk_text("Hello world.")
        assert len(result) == 1
        assert result[0][0] == "Hello world."
        assert result[0][1] == len("Hello world.") // 4

    def test_multiple_paragraphs_under_limit(self):
        text = "Paragraph one.\n\nParagraph two.\n\nParagraph three."
        result = chunk_text(text, max_chars=2000)
        assert len(result) == 1
        assert "Paragraph one." in result[0][0]
        assert "Paragraph three." in result[0][0]

    def test_paragraphs_exceed_limit(self):
        para = "A" * 1200
        text = f"{para}\n\n{para}\n\n{para}"
        result = chunk_text(text, max_chars=2000)
        assert len(result) >= 2
        for content, token_count in result:
            assert len(content) <= 2500
            assert token_count == len(content) // 4

    def test_single_oversized_paragraph_splits_on_sentences(self):
        sentences = ". ".join(f"Sentence {i} with some words" for i in range(80))
        result = chunk_text(sentences, max_chars=500)
        assert len(result) >= 3
        for content, _ in result:
            assert len(content) <= 600

    def test_preserves_all_content(self):
        text = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."
        result = chunk_text(text, max_chars=30)
        reassembled = "\n\n".join(content for content, _ in result)
        assert "First paragraph." in reassembled
        assert "Second paragraph." in reassembled
        assert "Third paragraph." in reassembled


from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from d4bl.services.document_persistence import persist_research_documents


class TestPersistResearchDocuments:
    """Extract crawl results and persist as documents + chunks."""

    @pytest.mark.asyncio
    async def test_empty_research_data(self):
        db = AsyncMock()
        count = await persist_research_documents(uuid4(), {}, db)
        assert count == 0

    @pytest.mark.asyncio
    async def test_no_json_findings(self):
        db = AsyncMock()
        research_data = {
            "research_findings": [
                {"agent": "researcher", "content": "plain text, not JSON"},
            ],
        }
        count = await persist_research_documents(uuid4(), research_data, db)
        assert count == 0

    @pytest.mark.asyncio
    async def test_extracts_and_persists_documents(self):
        job_id = uuid4()
        research_data = {
            "research_findings": [
                {
                    "agent": "researcher",
                    "content": '{"results": [{"url": "https://example.com/report", "extracted_content": "Report content here. Another sentence.", "title": "Test Report"}]}',
                },
            ],
        }

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch(
            "d4bl.services.document_persistence._try_embed",
            new_callable=AsyncMock,
            return_value=None,
        ):
            count = await persist_research_documents(job_id, research_data, mock_db)

        assert count == 1
        assert mock_db.add.call_count >= 2
        assert mock_db.commit.called

    @pytest.mark.asyncio
    async def test_skips_duplicate_urls_within_batch(self):
        job_id = uuid4()
        research_data = {
            "research_findings": [
                {
                    "agent": "researcher",
                    "content": '{"results": [{"url": "https://example.com/page", "extracted_content": "Content A.", "title": "A"}]}',
                },
                {
                    "agent": "researcher",
                    "content": '{"results": [{"url": "https://example.com/page", "extracted_content": "Content B.", "title": "B"}]}',
                },
            ],
        }

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch(
            "d4bl.services.document_persistence._try_embed",
            new_callable=AsyncMock,
            return_value=None,
        ):
            count = await persist_research_documents(job_id, research_data, mock_db)

        assert count == 1

    @pytest.mark.asyncio
    async def test_skips_urls_already_in_db(self):
        job_id = uuid4()
        research_data = {
            "research_findings": [
                {
                    "agent": "researcher",
                    "content": '{"results": [{"url": "https://example.com/existing", "extracted_content": "Some content.", "title": "Old"}]}',
                },
            ],
        }

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = ["https://example.com/existing"]
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch(
            "d4bl.services.document_persistence._try_embed",
            new_callable=AsyncMock,
            return_value=None,
        ):
            count = await persist_research_documents(job_id, research_data, mock_db)

        assert count == 0

    @pytest.mark.asyncio
    async def test_embedding_failure_still_persists_document(self):
        job_id = uuid4()
        research_data = {
            "research_findings": [
                {
                    "agent": "researcher",
                    "content": '{"results": [{"url": "https://example.com/new", "extracted_content": "Content here.", "title": "New"}]}',
                },
            ],
        }

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        # _try_embed returns None when Ollama is down (it catches internally)
        with patch(
            "d4bl.services.document_persistence._try_embed",
            new_callable=AsyncMock,
            return_value=None,
        ):
            count = await persist_research_documents(job_id, research_data, mock_db)

        assert count == 1
        assert mock_db.add.called
        assert mock_db.commit.called
