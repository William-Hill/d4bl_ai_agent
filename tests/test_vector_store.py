"""Tests for VectorStore embedding generation and search."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from d4bl.infra.vector_store import VectorStore, get_vector_store


class TestVectorStore:
    """Unit tests for VectorStore methods."""

    def setup_method(self):
        self.store = VectorStore(
            ollama_base_url="http://localhost:11434",
            embedder_model="mxbai-embed-large",
        )

    @staticmethod
    def _make_aiohttp_mocks(fake_embedding):
        """Build mock aiohttp session + response for generate_embedding tests."""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"embedding": fake_embedding})
        mock_response.text = AsyncMock(return_value="")
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.post.return_value = mock_response
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        return mock_session

    @pytest.mark.asyncio
    @patch("d4bl.infra.vector_store.aiohttp.ClientSession")
    async def test_generate_embedding_returns_vector(self, mock_session_cls):
        """generate_embedding should return a list of floats from Ollama."""
        fake_embedding = [0.1] * 1024
        mock_session = self._make_aiohttp_mocks(fake_embedding)
        mock_session_cls.return_value = mock_session

        result = await self.store.generate_embedding("test text")

        assert isinstance(result, list)
        assert len(result) == 1024

    @pytest.mark.asyncio
    @patch("d4bl.infra.vector_store.aiohttp.ClientSession")
    async def test_generate_embedding_truncates_long_text(self, mock_session_cls):
        """generate_embedding should truncate text longer than 6000 chars."""
        fake_embedding = [0.2] * 1024
        mock_session = self._make_aiohttp_mocks(fake_embedding)
        mock_session_cls.return_value = mock_session

        long_text = "x" * 10000
        result = await self.store.generate_embedding(long_text)
        assert len(result) == 1024

        # Verify the text sent was truncated
        call_kwargs = mock_session.post.call_args
        sent_json = call_kwargs[1]["json"]
        assert len(sent_json["prompt"]) <= 6000

    @pytest.mark.asyncio
    async def test_store_scraped_content_calls_generate_embedding(
        self, mock_db_session
    ):
        """store_scraped_content should generate embedding and insert."""
        job_id = uuid4()
        self.store.generate_embedding = AsyncMock(
            return_value=[0.1] * 1024
        )
        mock_db_session.execute = AsyncMock(
            return_value=MagicMock(scalar_one=MagicMock(return_value=uuid4()))
        )
        mock_db_session.commit = AsyncMock()

        result = await self.store.store_scraped_content(
            db=mock_db_session,
            job_id=job_id,
            url="https://example.com",
            content="Test content about NIL policies in Mississippi",
        )

        self.store.generate_embedding.assert_called_once()
        assert result is not None

    @pytest.mark.asyncio
    async def test_store_scraped_content_skips_short_content(
        self, mock_db_session
    ):
        """store_scraped_content should skip content that is too short."""
        job_id = uuid4()

        result = await self.store.store_scraped_content(
            db=mock_db_session,
            job_id=job_id,
            url="https://example.com",
            content="short",
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_search_similar_generates_query_embedding(
        self, mock_db_session
    ):
        """search_similar should generate embedding for the query text."""
        self.store.generate_embedding = AsyncMock(
            return_value=[0.1] * 1024
        )

        mock_result = MagicMock()
        mock_result.mappings.return_value = []
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        await self.store.search_similar(
            db=mock_db_session,
            query_text="NIL policies Mississippi",
            limit=5,
        )

        self.store.generate_embedding.assert_called_once_with(
            "NIL policies Mississippi"
        )

    @pytest.mark.asyncio
    async def test_store_batch_stores_multiple_items(self, mock_db_session):
        """store_batch should store each item and return count."""
        self.store.generate_embedding = AsyncMock(
            return_value=[0.1] * 1024
        )
        mock_db_session.execute = AsyncMock(
            return_value=MagicMock(scalar_one=MagicMock(return_value=uuid4()))
        )
        mock_db_session.commit = AsyncMock()

        items = [
            {"url": "https://example.com/1", "content": "Content about NIL policy one"},
            {"url": "https://example.com/2", "content": "Content about NIL policy two"},
        ]

        count = await self.store.store_batch(
            db=mock_db_session,
            job_id=uuid4(),
            items=items,
        )

        assert count == 2
        assert self.store.generate_embedding.call_count == 2

    @pytest.mark.asyncio
    async def test_store_staff_document_inserts_one_row_per_chunk(
        self, mock_db_session
    ):
        """store_staff_document embeds and inserts one row per chunk."""
        import json as _json

        self.store.generate_embedding = AsyncMock(return_value=[0.1] * 1024)
        returned_ids = [uuid4() for _ in range(3)]
        # First call is the idempotent DELETE for this upload_id, then 3 INSERTs.
        mock_db_session.execute = AsyncMock(
            side_effect=[
                MagicMock(),  # DELETE response (no rowcount needed)
                *[MagicMock(scalar_one=MagicMock(return_value=rid)) for rid in returned_ids],
            ]
        )
        mock_db_session.commit = AsyncMock()

        upload_id = uuid4()
        chunks = ["chunk one text", "chunk two text", "chunk three text"]
        metadata_base = {
            "title": "Overlooked: Women and Jails",
            "uploader_email": "alice@d4bl.org",
            "source_url": None,
            "original_filename": "vera_overlooked.pdf",
        }

        result = await self.store.store_staff_document(
            db=mock_db_session,
            upload_id=upload_id,
            chunks=chunks,
            metadata_base=metadata_base,
        )

        assert result == returned_ids
        assert self.store.generate_embedding.call_count == 3
        # 1 DELETE + 3 INSERTs
        assert mock_db_session.execute.call_count == 4
        mock_db_session.commit.assert_called_once()

        # First execute is the DELETE — confirm it targets this upload_id.
        delete_call_params = mock_db_session.execute.call_args_list[0][0][1]
        assert delete_call_params == {"upload_id": str(upload_id)}

        # Second execute is the first INSERT — inspect metadata enrichment.
        first_insert_params = mock_db_session.execute.call_args_list[1][0][1]
        metadata = _json.loads(first_insert_params["metadata"])
        assert metadata["title"] == "Overlooked: Women and Jails"
        assert metadata["upload_id"] == str(upload_id)
        assert metadata["chunk_index"] == 0
        assert metadata["total_chunks"] == 3
        assert metadata["source_type"] == "staff_upload"

    @pytest.mark.asyncio
    async def test_store_staff_document_deletes_existing_chunks_first(
        self, mock_db_session
    ):
        """Idempotency: DELETE runs before any INSERT so retries don't duplicate."""
        self.store.generate_embedding = AsyncMock(return_value=[0.1] * 1024)
        mock_db_session.execute = AsyncMock(
            side_effect=[
                MagicMock(),
                MagicMock(scalar_one=MagicMock(return_value=uuid4())),
            ]
        )
        mock_db_session.commit = AsyncMock()

        await self.store.store_staff_document(
            db=mock_db_session,
            upload_id=uuid4(),
            chunks=["only chunk"],
            metadata_base={"title": "Test"},
        )

        first_sql = str(mock_db_session.execute.call_args_list[0][0][0])
        assert "DELETE FROM scraped_content_vectors" in first_sql
        assert "'staff_upload'" in first_sql

    @pytest.mark.asyncio
    async def test_store_staff_document_empty_chunks_returns_empty(
        self, mock_db_session
    ):
        """Empty chunks list should short-circuit without DB calls."""
        self.store.generate_embedding = AsyncMock()
        mock_db_session.execute = AsyncMock()

        result = await self.store.store_staff_document(
            db=mock_db_session,
            upload_id=uuid4(),
            chunks=[],
            metadata_base={"title": "Empty doc"},
        )

        assert result == []
        self.store.generate_embedding.assert_not_called()
        mock_db_session.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_store_staff_document_rollback_on_error(self, mock_db_session):
        """If any chunk fails to insert, rollback and re-raise."""
        self.store.generate_embedding = AsyncMock(return_value=[0.1] * 1024)
        mock_db_session.execute = AsyncMock(side_effect=RuntimeError("db down"))
        mock_db_session.commit = AsyncMock()
        mock_db_session.rollback = AsyncMock()

        with pytest.raises(RuntimeError, match="db down"):
            await self.store.store_staff_document(
                db=mock_db_session,
                upload_id=uuid4(),
                chunks=["only chunk"],
                metadata_base={"title": "Test"},
            )

        mock_db_session.rollback.assert_called_once()
        mock_db_session.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_store_staff_document_uses_source_url_when_present(
        self, mock_db_session
    ):
        """URL-based uploads propagate source_url to the url column."""
        self.store.generate_embedding = AsyncMock(return_value=[0.1] * 1024)
        # First call is DELETE, second is INSERT.
        mock_db_session.execute = AsyncMock(
            side_effect=[
                MagicMock(),
                MagicMock(scalar_one=MagicMock(return_value=uuid4())),
            ]
        )
        mock_db_session.commit = AsyncMock()

        await self.store.store_staff_document(
            db=mock_db_session,
            upload_id=uuid4(),
            chunks=["some content"],
            metadata_base={
                "title": "ProPublica investigation",
                "source_url": "https://propublica.org/article",
            },
        )

        # INSERT is the second execute call (call_args_list[1]).
        insert_params = mock_db_session.execute.call_args_list[1][0][1]
        assert insert_params["url"] == "https://propublica.org/article"


class TestHelpers:
    """Tests for extracted helper methods."""

    def test_format_embedding_produces_pgvector_string(self):
        store = VectorStore(ollama_base_url="http://localhost:11434")
        result = store._format_embedding([0.1, 0.2, 0.3])
        assert result == "[0.1,0.2,0.3]"

    def test_format_embedding_empty_list(self):
        store = VectorStore(ollama_base_url="http://localhost:11434")
        result = store._format_embedding([])
        assert result == "[]"

    def test_row_to_content_dict_converts_mapping(self):
        """_row_to_content_dict should convert a mapping row to a dict."""
        from datetime import datetime, timezone
        from uuid import uuid4 as _uuid4

        store = VectorStore(ollama_base_url="http://localhost:11434")
        row_id = _uuid4()
        job_id = _uuid4()
        now = datetime(2025, 1, 1, tzinfo=timezone.utc)

        mapping = {
            "id": row_id,
            "job_id": job_id,
            "url": "https://example.com",
            "content": "test content",
            "content_type": "html",
            "metadata": {"key": "value"},
            "created_at": now,
        }

        result = store._row_to_content_dict(mapping)
        assert result["id"] == str(row_id)
        assert result["job_id"] == str(job_id)
        assert result["url"] == "https://example.com"
        assert result["metadata"] == {"key": "value"}
        assert result["created_at"] == now.isoformat()

    def test_row_to_content_dict_handles_none_values(self):
        store = VectorStore(ollama_base_url="http://localhost:11434")
        mapping = {
            "id": None,
            "job_id": None,
            "url": "https://example.com",
            "content": "test",
            "content_type": None,
            "metadata": None,
            "created_at": None,
        }
        result = store._row_to_content_dict(mapping)
        assert result["job_id"] is None
        assert result["metadata"] == {}
        assert result["created_at"] is None


class TestGetVectorStore:
    """Test the singleton factory."""

    def test_returns_vector_store_instance(self):
        store = get_vector_store()
        assert isinstance(store, VectorStore)

    def test_returns_same_instance(self):
        store1 = get_vector_store()
        store2 = get_vector_store()
        assert store1 is store2
