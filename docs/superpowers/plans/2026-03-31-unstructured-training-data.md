# Unstructured Training Data & Document Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a unified document layer (`documents` + `document_chunks`) and wire unstructured content into the training pipeline so v3 training data includes real-world prose alongside structured database records.

**Architecture:** New Supabase tables for documents and chunks, shared chunker/embedder utilities, migration of existing data (policy bills, research jobs, scraped content), then training pipeline changes to extract from the new schema and generate document-sourced evaluator pairs.

**Tech Stack:** PostgreSQL/Supabase (pgvector), psycopg2, Python, pytest, existing Ollama embeddings

---

## File Map

| Action | File | Responsibility |
|--------|------|---------------|
| Create | `supabase/migrations/20260331000001_add_document_tables.sql` | Schema migration: documents, document_chunks, compatibility view |
| Create | `scripts/training/chunker.py` | Sentence-aware text splitter |
| Create | `scripts/training/embedder.py` | Batch embedding via Ollama |
| Create | `scripts/training/migrate_documents.py` | One-time migration: policy bills, research jobs, scraped content → documents |
| Create | `scripts/training/flywheel_metrics.py` | Flywheel metrics query script |
| Create | `tests/test_training/test_chunker.py` | Tests for chunker |
| Create | `tests/test_training/test_embedder.py` | Tests for embedder |
| Create | `tests/test_training/test_migrate_documents.py` | Tests for migration logic |
| Create | `tests/test_training/test_extract_corpus_v3.py` | Tests for document extraction |
| Create | `tests/test_training/test_generate_pairs_v3.py` | Tests for document-sourced evaluator pairs and community_framing parser pairs |
| Create | `tests/test_training/test_flywheel_metrics.py` | Tests for flywheel metrics |
| Modify | `scripts/training/extract_corpus.py` | Add `documents` extractor to EXTRACTORS registry |
| Modify | `scripts/training/templates.py` | Add `render_document_passage` template |
| Modify | `scripts/training/generate_training_pairs.py` | Add document-sourced hallucination pairs and community_framing parser pairs |
| Modify | `scripts/training/prompts.py` | Add community_framing prompt templates |
| Modify | `scripts/training/config.py` | Add v3 constants (DOC_EVALUATOR_PAIRS, COMMUNITY_FRAMING_PAIRS) |
| Modify | `scripts/training/train.py:53,74` | Change explainer epochs 7→4, explainer LoRA r=32→16 |
| Modify | `src/d4bl/infra/database.py` | Add Document and DocumentChunk SQLAlchemy models |

---

### Task 1: Supabase Migration — Document Tables

**Files:**
- Create: `supabase/migrations/20260331000001_add_document_tables.sql`

- [ ] **Step 1: Write the migration SQL**

```sql
-- supabase/migrations/20260331000001_add_document_tables.sql

-- Ensure pgvector extension exists
CREATE EXTENSION IF NOT EXISTS vector;

-- Parent table: one row per source document
CREATE TABLE IF NOT EXISTS documents (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title               TEXT,
    source_url          TEXT,
    storage_path        TEXT,
    content_type        VARCHAR(50) NOT NULL,
    source_key          VARCHAR(100),
    job_id              UUID REFERENCES research_jobs(job_id),
    extraction_metadata JSONB DEFAULT '{}',
    metadata            JSONB DEFAULT '{}',
    created_at          TIMESTAMPTZ DEFAULT now(),
    updated_at          TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_documents_content_type ON documents(content_type);
CREATE INDEX IF NOT EXISTS idx_documents_source_key ON documents(source_key);
CREATE INDEX IF NOT EXISTS idx_documents_job_id ON documents(job_id) WHERE job_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_documents_source_url ON documents(source_url) WHERE source_url IS NOT NULL;

-- Child table: N chunks per document
CREATE TABLE IF NOT EXISTS document_chunks (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id     UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    content         TEXT NOT NULL,
    chunk_index     INTEGER NOT NULL,
    token_count     INTEGER,
    embedding       vector(1024),
    metadata        JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_chunks_document_id ON document_chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_chunks_embedding ON document_chunks
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
CREATE UNIQUE INDEX IF NOT EXISTS idx_chunks_doc_position ON document_chunks(document_id, chunk_index);
```

- [ ] **Step 2: Apply the migration**

Run:
```bash
supabase db push
```
Expected: Migration applies successfully, tables created.

- [ ] **Step 3: Verify tables exist**

Run:
```bash
psql "$DATABASE_URL" -c "\dt documents; \dt document_chunks;"
```
Expected: Both tables listed.

- [ ] **Step 4: Commit**

```bash
git add supabase/migrations/20260331000001_add_document_tables.sql
git commit -m "feat: add documents and document_chunks tables (#151)"
```

---

### Task 2: SQLAlchemy Models for Documents

**Files:**
- Modify: `src/d4bl/infra/database.py`

- [ ] **Step 1: Add Document and DocumentChunk models**

Add after the `ModelEvalRun` class (around line 142) in `src/d4bl/infra/database.py`:

```python
class Document(Base):
    """Parent document: one row per source file/article/report."""
    __tablename__ = "documents"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    title = Column(Text, nullable=True)
    source_url = Column(Text, nullable=True)
    storage_path = Column(Text, nullable=True)
    content_type = Column(String(50), nullable=False)
    source_key = Column(String(100), nullable=True)
    job_id = Column(PG_UUID(as_uuid=True), ForeignKey("research_jobs.job_id"), nullable=True)
    extraction_metadata = Column(JSONB, default=dict)
    metadata = Column(JSONB, default=dict)
    created_at = Column(DateTime, nullable=False, default=_utc_now)
    updated_at = Column(DateTime, nullable=False, default=_utc_now, onupdate=_utc_now)

    def to_dict(self):
        return {
            "id": str(self.id),
            "title": self.title,
            "source_url": self.source_url,
            "storage_path": self.storage_path,
            "content_type": self.content_type,
            "source_key": self.source_key,
            "job_id": str(self.job_id) if self.job_id else None,
            "extraction_metadata": self.extraction_metadata or {},
            "metadata": self.metadata or {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class DocumentChunk(Base):
    """Child chunk: N chunks per document, each with its own embedding."""
    __tablename__ = "document_chunks"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    document_id = Column(PG_UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    content = Column(Text, nullable=False)
    chunk_index = Column(Integer, nullable=False)
    token_count = Column(Integer, nullable=True)
    # Note: embedding column is vector(1024) in Postgres but not represented as a SQLAlchemy type here;
    # raw SQL is used for vector operations (same pattern as scraped_content_vectors).
    metadata = Column(JSONB, default=dict)
    created_at = Column(DateTime, nullable=False, default=_utc_now)

    def to_dict(self):
        return {
            "id": str(self.id),
            "document_id": str(self.document_id),
            "content": self.content,
            "chunk_index": self.chunk_index,
            "token_count": self.token_count,
            "metadata": self.metadata or {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
```

- [ ] **Step 2: Verify import works**

Run:
```bash
python -c "from d4bl.infra.database import Document, DocumentChunk; print('OK')"
```
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add src/d4bl/infra/database.py
git commit -m "feat: add Document and DocumentChunk SQLAlchemy models (#151)"
```

---

### Task 3: Sentence-Aware Chunker

**Files:**
- Create: `scripts/training/chunker.py`
- Create: `tests/test_training/test_chunker.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_training/test_chunker.py
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
        # ~5 tokens per sentence, target 10 tokens → ~2 sentences per chunk
        sentences = ["Sentence number one. ", "Sentence number two. ",
                     "Sentence number three. ", "Sentence number four. "]
        text = "".join(sentences)
        chunks = chunk_text(text, target_tokens=10)
        assert len(chunks) >= 2
        # Each chunk should end at a sentence boundary (period)
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
        # All original words present
        for word in ["Alpha", "bravo", "Charlie", "delta", "Echo", "foxtrot"]:
            assert word in reconstructed

    def test_overlap_adds_context(self):
        text = "First sentence. Second sentence. Third sentence. Fourth sentence."
        chunks_no_overlap = chunk_text(text, target_tokens=8, overlap_tokens=0)
        chunks_with_overlap = chunk_text(text, target_tokens=8, overlap_tokens=4)
        # With overlap, later chunks may start with content from the previous chunk
        if len(chunks_with_overlap) > 1:
            # Second chunk should contain some text from first chunk's end
            assert len(chunks_with_overlap) >= len(chunks_no_overlap)

    def test_metadata_includes_boundary_type(self):
        text = "First sentence. Second sentence.\n\nNew paragraph here."
        chunks = chunk_text(text, target_tokens=8)
        # At least check metadata key exists
        assert all("boundary" in c.get("metadata", {}) for c in chunks)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_training/test_chunker.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.training.chunker'`

- [ ] **Step 3: Implement the chunker**

```python
# scripts/training/chunker.py
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
    # Split on sentence-ending punctuation followed by whitespace or newline
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

        # If adding this sentence exceeds target and we have content, flush
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

            # Handle overlap: keep trailing sentences that fit in overlap budget
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

    # Flush remaining
    if current_sentences:
        content = " ".join(current_sentences)
        chunks.append({
            "content": content,
            "chunk_index": chunk_index,
            "token_count": _estimate_tokens(content),
            "metadata": {"boundary": "end"},
        })

    return chunks
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_training/test_chunker.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/training/chunker.py tests/test_training/test_chunker.py
git commit -m "feat: add sentence-aware text chunker (#151)"
```

---

### Task 4: Batch Embedder Utility

**Files:**
- Create: `scripts/training/embedder.py`
- Create: `tests/test_training/test_embedder.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_training/test_embedder.py
"""Tests for the batch embedder utility."""

from unittest.mock import AsyncMock, patch

import pytest

from scripts.training.embedder import batch_embed, format_embedding_for_pg


class TestFormatEmbedding:
    def test_formats_as_pgvector_string(self):
        vec = [1.0, 2.5, -3.0]
        result = format_embedding_for_pg(vec)
        assert result == "[1.0,2.5,-3.0]"

    def test_empty_vector(self):
        assert format_embedding_for_pg([]) == "[]"


class TestBatchEmbed:
    @pytest.mark.asyncio
    async def test_returns_embeddings_for_each_text(self):
        fake_embedding = [0.1] * 1024
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"embedding": fake_embedding})
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.post = AsyncMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            results = await batch_embed(["hello", "world"])

        assert len(results) == 2
        assert len(results[0]) == 1024

    @pytest.mark.asyncio
    async def test_truncates_long_text(self):
        """Verify text longer than 6000 chars is truncated before embedding."""
        long_text = "a " * 4000  # 8000 chars
        fake_embedding = [0.1] * 1024
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"embedding": fake_embedding})
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.post = AsyncMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            results = await batch_embed([long_text])

        assert len(results) == 1
        # Verify the text sent to Ollama was truncated
        call_args = mock_session.post.call_args
        sent_prompt = call_args[1]["json"]["prompt"]
        assert len(sent_prompt) <= 6000
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_training/test_embedder.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.training.embedder'`

- [ ] **Step 3: Implement the embedder**

```python
# scripts/training/embedder.py
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_training/test_embedder.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/training/embedder.py tests/test_training/test_embedder.py
git commit -m "feat: add batch embedding utility (#151)"
```

---

### Task 5: Document Migration Script

**Files:**
- Create: `scripts/training/migrate_documents.py`
- Create: `tests/test_training/test_migrate_documents.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_training/test_migrate_documents.py
"""Tests for document migration logic."""

import json

from scripts.training.migrate_documents import (
    extract_research_job_text,
    policy_bill_to_document,
)


class TestPolicyBillToDocument:
    def test_converts_bill_to_document_dict(self):
        bill = {
            "id": 1,
            "title": "Housing Protection Act",
            "summary": "Protects tenants from unfair eviction.",
            "state": "AL",
            "status": "introduced",
            "topic_tags": ["housing", "tenant_rights"],
            "session": "2025",
            "url": "https://openstates.org/al/bills/HB123",
            "bill_number": "HB 123",
        }
        doc = policy_bill_to_document(bill)
        assert doc["title"] == "Housing Protection Act"
        assert doc["content_type"] == "policy_bill"
        assert doc["source_url"] == "https://openstates.org/al/bills/HB123"
        assert doc["metadata"]["state"] == "AL"
        assert doc["metadata"]["topic_tags"] == ["housing", "tenant_rights"]
        assert doc["text"] == "Protects tenants from unfair eviction."

    def test_handles_missing_summary(self):
        bill = {"id": 1, "title": "Some Bill", "summary": None, "state": "AK",
                "status": "introduced", "topic_tags": [], "session": "2025",
                "url": None, "bill_number": "SB 1"}
        doc = policy_bill_to_document(bill)
        assert doc["text"] == ""


class TestExtractResearchJobText:
    def test_extracts_from_result_dict(self):
        result = {"final_report": "This is the research finding about housing disparities."}
        text = extract_research_job_text(result, research_data=None)
        assert "housing disparities" in text

    def test_extracts_from_research_data(self):
        research_data = {"research_findings": "Incarceration rates are disproportionate."}
        text = extract_research_job_text(result=None, research_data=research_data)
        assert "Incarceration rates" in text

    def test_handles_none_gracefully(self):
        text = extract_research_job_text(result=None, research_data=None)
        assert text == ""

    def test_combines_result_and_research_data(self):
        result = {"final_report": "Report text."}
        research_data = {"research_findings": "Finding text."}
        text = extract_research_job_text(result, research_data)
        assert "Report text" in text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_training/test_migrate_documents.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.training.migrate_documents'`

- [ ] **Step 3: Implement the migration helpers and main script**

```python
# scripts/training/migrate_documents.py
"""One-time migration: populate documents + document_chunks from existing tables.

Sources:
  - policy_bills → documents (content_type='policy_bill')
  - research_jobs (completed) → documents (content_type='research_report')
  - scraped_content_vectors → documents + chunks (preserving embeddings)

Usage:
    python -m scripts.training.migrate_documents
    python -m scripts.training.migrate_documents --source policy_bills
    python -m scripts.training.migrate_documents --source research_jobs
    python -m scripts.training.migrate_documents --source scraped_content
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import uuid
from typing import Any

from scripts.training.chunker import chunk_text
from scripts.training.embedder import batch_embed, format_embedding_for_pg

logger = logging.getLogger(__name__)


def policy_bill_to_document(bill: dict) -> dict:
    """Convert a policy_bills row to a document dict.

    Args:
        bill: Dict with keys from the policy_bills table.

    Returns:
        Dict with keys: title, content_type, source_url, metadata, text,
        extraction_metadata.
    """
    return {
        "title": bill.get("title") or "",
        "content_type": "policy_bill",
        "source_url": bill.get("url"),
        "source_key": "openstates",
        "metadata": {
            "state": bill.get("state"),
            "status": bill.get("status"),
            "topic_tags": bill.get("topic_tags") or [],
            "session": bill.get("session"),
            "bill_number": bill.get("bill_number"),
        },
        "extraction_metadata": {"source_table": "policy_bills"},
        "text": bill.get("summary") or "",
    }


def extract_research_job_text(
    result: dict | None,
    research_data: dict | None,
) -> str:
    """Extract narrative text from research job JSON fields.

    Checks result['final_report'] and research_data['research_findings'].

    Args:
        result: The research_jobs.result JSON column.
        research_data: The research_jobs.research_data JSON column.

    Returns:
        Combined narrative text, or empty string if no text found.
    """
    parts: list[str] = []

    if isinstance(result, dict):
        # Try common keys where narrative text lives
        for key in ("final_report", "summary", "report", "output"):
            val = result.get(key)
            if isinstance(val, str) and val.strip():
                parts.append(val.strip())
                break

    if isinstance(research_data, dict):
        findings = research_data.get("research_findings")
        if isinstance(findings, str) and findings.strip():
            parts.append(findings.strip())

    return "\n\n".join(parts)


def _migrate_policy_bills(conn: Any, dry_run: bool = False) -> int:
    """Migrate policy_bills rows to documents + document_chunks."""
    import psycopg2.extras

    count = 0
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM policy_bills")
        rows = cur.fetchall()

    logger.info("Found %d policy bills to migrate", len(rows))

    for row in rows:
        doc = policy_bill_to_document(dict(row))
        if not doc["text"]:
            logger.debug("Skipping bill %s — no summary text", row.get("bill_number"))
            continue

        if dry_run:
            count += 1
            continue

        chunks = chunk_text(doc["text"], target_tokens=500)
        doc_id = str(uuid.uuid4())

        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO documents (id, title, source_url, content_type, source_key,
                   extraction_metadata, metadata, created_at, updated_at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, now(), now())
                   ON CONFLICT (source_url) WHERE source_url IS NOT NULL DO NOTHING
                   RETURNING id""",
                (doc_id, doc["title"], doc["source_url"], doc["content_type"],
                 doc["source_key"], json.dumps(doc["extraction_metadata"]),
                 json.dumps(doc["metadata"])),
            )
            result = cur.fetchone()
            if result is None:
                logger.debug("Bill %s already exists, skipping", doc["source_url"])
                continue

            for chunk in chunks:
                cur.execute(
                    """INSERT INTO document_chunks
                       (document_id, content, chunk_index, token_count, metadata, created_at)
                       VALUES (%s, %s, %s, %s, %s, now())""",
                    (doc_id, chunk["content"], chunk["chunk_index"],
                     chunk["token_count"], json.dumps(chunk.get("metadata", {}))),
                )
        conn.commit()
        count += 1

    logger.info("Migrated %d policy bills", count)
    return count


def _migrate_research_jobs(conn: Any, dry_run: bool = False) -> int:
    """Migrate completed research_jobs to documents + document_chunks."""
    import psycopg2.extras

    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            "SELECT job_id, query, result, research_data FROM research_jobs WHERE status = 'completed'"
        )
        rows = cur.fetchall()

    logger.info("Found %d completed research jobs to migrate", len(rows))
    count = 0

    for row in rows:
        text = extract_research_job_text(row.get("result"), row.get("research_data"))
        if not text:
            logger.debug("Skipping job %s — no narrative text", row["job_id"])
            continue

        if dry_run:
            count += 1
            continue

        chunks = chunk_text(text, target_tokens=500)
        doc_id = str(uuid.uuid4())
        job_id = str(row["job_id"])

        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO documents (id, title, content_type, job_id,
                   extraction_metadata, metadata, created_at, updated_at)
                   VALUES (%s, %s, %s, %s, %s, %s, now(), now())
                   ON CONFLICT DO NOTHING
                   RETURNING id""",
                (doc_id, row.get("query", ""), "research_report", job_id,
                 json.dumps({"source_table": "research_jobs"}),
                 json.dumps({"query": row.get("query", "")})),
            )
            result = cur.fetchone()
            if result is None:
                continue

            for chunk in chunks:
                cur.execute(
                    """INSERT INTO document_chunks
                       (document_id, content, chunk_index, token_count, metadata, created_at)
                       VALUES (%s, %s, %s, %s, %s, now())""",
                    (doc_id, chunk["content"], chunk["chunk_index"],
                     chunk["token_count"], json.dumps(chunk.get("metadata", {}))),
                )
        conn.commit()
        count += 1

    logger.info("Migrated %d research jobs", count)
    return count


def _migrate_scraped_content(conn: Any, dry_run: bool = False) -> int:
    """Migrate scraped_content_vectors to documents + document_chunks.

    Preserves existing embeddings — no re-computation needed.
    """
    import psycopg2.extras

    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            "SELECT id, job_id, url, content, content_type, metadata, embedding "
            "FROM scraped_content_vectors"
        )
        rows = cur.fetchall()

    logger.info("Found %d scraped content rows to migrate", len(rows))
    count = 0

    for row in rows:
        if not row.get("content") or not row["content"].strip():
            continue

        if dry_run:
            count += 1
            continue

        doc_id = str(uuid.uuid4())
        job_id = str(row["job_id"]) if row.get("job_id") else None
        metadata = row.get("metadata") or {}

        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO documents (id, title, source_url, content_type, job_id,
                   extraction_metadata, metadata, created_at, updated_at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, now(), now())
                   ON CONFLICT (source_url) WHERE source_url IS NOT NULL DO NOTHING
                   RETURNING id""",
                (doc_id, metadata.get("title", ""), row.get("url"),
                 row.get("content_type") or "html", job_id,
                 json.dumps({"source_table": "scraped_content_vectors"}),
                 json.dumps(metadata)),
            )
            result = cur.fetchone()
            if result is None:
                continue

            # Preserve existing embedding — insert as-is
            embedding_str = row.get("embedding")
            cur.execute(
                """INSERT INTO document_chunks
                   (document_id, content, chunk_index, token_count, embedding, created_at)
                   VALUES (%s, %s, 0, %s, %s, now())""",
                (doc_id, row["content"], len(row["content"].split()),
                 embedding_str),
            )
        conn.commit()
        count += 1

    logger.info("Migrated %d scraped content rows", count)
    return count


ALL_SOURCES = {
    "policy_bills": _migrate_policy_bills,
    "research_jobs": _migrate_research_jobs,
    "scraped_content": _migrate_scraped_content,
}


def main(sources: list[str] | None = None, dry_run: bool = False) -> dict[str, int]:
    """Run migration for specified sources (or all).

    Args:
        sources: List of source keys to migrate, or None for all.
        dry_run: If True, count without inserting.

    Returns:
        Dict mapping source key to count of migrated records.
    """
    from scripts.ingestion.helpers import get_db_connection

    if sources is None:
        sources = list(ALL_SOURCES.keys())

    conn = get_db_connection()
    results: dict[str, int] = {}
    try:
        for source in sources:
            migrate_fn = ALL_SOURCES.get(source)
            if migrate_fn is None:
                logger.warning("Unknown source %r, skipping", source)
                continue
            logger.info("Migrating %s%s...", source, " (dry run)" if dry_run else "")
            results[source] = migrate_fn(conn, dry_run=dry_run)
    finally:
        conn.close()

    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description="Migrate existing data to documents schema.")
    parser.add_argument(
        "--source",
        choices=list(ALL_SOURCES.keys()),
        help="Specific source to migrate (default: all).",
    )
    parser.add_argument("--dry-run", action="store_true", help="Count without inserting.")
    args = parser.parse_args()

    sources = [args.source] if args.source else None
    results = main(sources=sources, dry_run=args.dry_run)
    for source, count in results.items():
        print(f"  {source}: {count} records")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_training/test_migrate_documents.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/training/migrate_documents.py tests/test_training/test_migrate_documents.py
git commit -m "feat: add document migration script (#151)"
```

---

### Task 6: Corpus Extraction — Add Documents Extractor

**Files:**
- Modify: `scripts/training/templates.py`
- Modify: `scripts/training/extract_corpus.py`
- Create: `tests/test_training/test_extract_corpus_v3.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_training/test_extract_corpus_v3.py
"""Tests for document corpus extraction (v3)."""

from scripts.training.templates import render_document_passage
from scripts.training.extract_corpus import EXTRACTORS


class TestRenderDocumentPassage:
    def test_wraps_with_metadata(self):
        row = {
            "content": "Eviction rates in Georgia increased 15% in 2023.",
            "title": "Georgia Housing Report",
            "content_type": "research_report",
        }
        passage = render_document_passage(row)
        assert "Georgia Housing Report" in passage
        assert "research_report" in passage
        assert "Eviction rates in Georgia" in passage

    def test_handles_missing_title(self):
        row = {"content": "Some content.", "title": None, "content_type": "news"}
        passage = render_document_passage(row)
        assert "Some content." in passage
        assert "news" in passage

    def test_returns_empty_for_no_content(self):
        row = {"content": "", "title": "Empty", "content_type": "pdf"}
        passage = render_document_passage(row)
        assert passage == ""


class TestDocumentsExtractor:
    def test_documents_in_registry(self):
        assert "documents" in EXTRACTORS

    def test_documents_extractor_has_required_keys(self):
        ext = EXTRACTORS["documents"]
        assert "query" in ext
        assert "template" in ext
        assert callable(ext["template"])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_training/test_extract_corpus_v3.py -v`
Expected: FAIL — `ImportError: cannot import name 'render_document_passage'`

- [ ] **Step 3: Add render_document_passage to templates.py**

Add at the end of `scripts/training/templates.py`:

```python
def render_document_passage(row: dict) -> str:
    """Render a document_chunks row as a training passage.

    Wraps the chunk text with light metadata context. No heavy templating
    needed since the text is already natural prose.

    Args:
        row: Dict with keys: content, title, content_type.

    Returns:
        A passage string, or empty string if content is missing.
    """
    content = (row.get("content") or "").strip()
    if not content:
        return ""

    title = row.get("title") or ""
    content_type = row.get("content_type") or "document"

    header = f"Source: {content_type}"
    if title:
        header += f' — "{title}"'

    return f"{header}\n{content}"
```

- [ ] **Step 4: Add documents extractor to extract_corpus.py**

Add to the `EXTRACTORS` dict in `scripts/training/extract_corpus.py` (after the `fbi_crime_stats` entry at line 88):

```python
    "documents": {
        "query": (
            "SELECT dc.content, d.title, d.content_type "
            "FROM document_chunks dc "
            "JOIN documents d ON dc.document_id = d.id "
            "ORDER BY random() LIMIT %(limit)s"
        ),
        "template": render_document_passage,
    },
```

Also add the import at the top of the file (with the other template imports):

```python
from scripts.training.templates import (
    render_bjs_passage,
    render_cdc_passage,
    render_census_passage,
    render_document_passage,
    render_epa_passage,
    render_fbi_passage,
    render_police_violence_passage,
)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_training/test_extract_corpus_v3.py tests/test_training/test_extract_corpus.py -v`
Expected: All tests PASS (both new and existing).

- [ ] **Step 6: Commit**

```bash
git add scripts/training/templates.py scripts/training/extract_corpus.py tests/test_training/test_extract_corpus_v3.py
git commit -m "feat: add documents extractor to corpus pipeline (#151)"
```

---

### Task 7: Document-Sourced Evaluator Pairs

**Files:**
- Modify: `scripts/training/config.py`
- Modify: `scripts/training/generate_training_pairs.py`
- Create: `tests/test_training/test_generate_pairs_v3.py`

- [ ] **Step 1: Add v3 constants to config.py**

Add after the V2 expansion constants (line 34) in `scripts/training/config.py`:

```python
# V3: document-sourced evaluator pairs (issue #151)
DOC_EVALUATOR_PAIRS_PER_SUBTASK = 175  # ~50% of total when combined with structured
COMMUNITY_FRAMING_PAIRS = 200  # parser pairs with populated community_framing
```

- [ ] **Step 2: Write the failing tests**

```python
# tests/test_training/test_generate_pairs_v3.py
"""Tests for v3 training pair generation: document-sourced evaluator pairs
and community_framing parser pairs."""

import json

from scripts.training.generate_training_pairs import (
    build_doc_hallucination_pair,
    build_community_framing_pair,
    format_as_chatml,
    format_eval_user_message,
)


class TestBuildDocHallucinationPair:
    def test_returns_factual_and_hallucinated(self):
        chunk = {
            "content": "In 2023, Georgia had an eviction rate of 5.2%.",
            "title": "Housing Report",
            "content_type": "research_report",
        }
        hallucinated_text = "In 2023, Georgia had an eviction rate of 12.8%."
        factual_pair, hall_pair = build_doc_hallucination_pair(chunk, hallucinated_text)

        # Both are ChatML format
        assert "messages" in factual_pair
        assert "messages" in hall_pair
        assert len(factual_pair["messages"]) == 3
        assert len(hall_pair["messages"]) == 3

        # Factual pair labels FACTUAL
        factual_label = json.loads(factual_pair["messages"][2]["content"])
        assert factual_label["label"] == "FACTUAL"

        # Hallucinated pair labels HALLUCINATED
        hall_label = json.loads(hall_pair["messages"][2]["content"])
        assert hall_label["label"] == "HALLUCINATED"

    def test_context_contains_chunk_content(self):
        chunk = {
            "content": "Specific eviction data here.",
            "title": "Report",
            "content_type": "policy_bill",
        }
        factual_pair, _ = build_doc_hallucination_pair(chunk, "Fake data.")
        user_msg = factual_pair["messages"][1]["content"]
        assert "Specific eviction data here." in user_msg


class TestBuildCommunityFramingPair:
    def test_returns_chatml_with_community_framing(self):
        question = "Our community is fighting eviction rates — what does HB 432 do?"
        expected_framing = {
            "detected": True,
            "issue_domain": "housing",
            "structural_frame": "economic_displacement",
        }
        pair = build_community_framing_pair(
            question=question,
            entities=["Georgia"],
            data_sources=["census_indicators", "policy_bills"],
            community_framing=expected_framing,
        )
        assert "messages" in pair
        assert len(pair["messages"]) == 3

        # Assistant response should contain the framing
        assistant_json = json.loads(pair["messages"][2]["content"])
        assert assistant_json["community_framing"]["detected"] is True
        assert assistant_json["community_framing"]["issue_domain"] == "housing"

    def test_user_message_is_the_question(self):
        pair = build_community_framing_pair(
            question="Why are people being pushed out?",
            entities=["Atlanta"],
            data_sources=["census_indicators"],
            community_framing={"detected": True, "issue_domain": "housing",
                               "structural_frame": "gentrification"},
        )
        assert pair["messages"][1]["content"] == "Why are people being pushed out?"
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/test_training/test_generate_pairs_v3.py -v`
Expected: FAIL — `ImportError: cannot import name 'build_doc_hallucination_pair'`

- [ ] **Step 4: Implement the new pair builders**

Add to `scripts/training/generate_training_pairs.py` after the `build_evaluator_v2_pair` function (around line 332):

```python
def build_doc_hallucination_pair(
    chunk: dict,
    hallucinated_text: str,
) -> tuple[dict, dict]:
    """Build a (FACTUAL, HALLUCINATED) pair from a document chunk.

    The chunk content itself is the factual reference — no Claude call needed
    for the factual side. Only the hallucinated version requires generation.

    Args:
        chunk: Dict with keys: content, title, content_type.
        hallucinated_text: The perturbed/hallucinated version of the content.

    Returns:
        Tuple of (factual_pair, hallucinated_pair) in ChatML format.
    """
    system = STUDENT_EVALUATOR_SYSTEMS["hallucination"]
    # Use chunk metadata as context for the evaluator
    context = json.dumps(
        {"title": chunk.get("title", ""), "content_type": chunk.get("content_type", ""),
         "source_text": chunk["content"]},
        ensure_ascii=False,
    )

    factual_pair = format_as_chatml(
        system=system,
        user=format_eval_user_message(context, chunk["content"]),
        assistant=json.dumps({"label": "FACTUAL"}),
    )
    hallucinated_pair = format_as_chatml(
        system=system,
        user=format_eval_user_message(context, hallucinated_text),
        assistant=json.dumps({"label": "HALLUCINATED"}),
    )
    return factual_pair, hallucinated_pair


def build_community_framing_pair(
    question: str,
    entities: list[str],
    data_sources: list[str],
    community_framing: dict,
) -> dict:
    """Build a parser training pair with a populated community_framing field.

    Args:
        question: The community-voiced research question.
        entities: Geographic/demographic entities in the question.
        data_sources: Relevant data source keys.
        community_framing: Dict with detected, issue_domain, structural_frame.

    Returns:
        ChatML-formatted training pair.
    """
    assistant_response = json.dumps({
        "entities": entities,
        "search_queries": [question],
        "data_sources": data_sources,
        "community_framing": community_framing,
    }, ensure_ascii=False)

    return format_as_chatml(
        system=_STUDENT_QUERY_PARSER_SYSTEM,
        user=question,
        assistant=assistant_response,
    )
```

Also add the import for `DOC_EVALUATOR_PAIRS_PER_SUBTASK` and `COMMUNITY_FRAMING_PAIRS` at the top of the file alongside the other config imports:

```python
from scripts.training.config import (
    COMMUNITY_FRAMING_PAIRS,
    DISTILLATION_MODEL,
    DOC_EVALUATOR_PAIRS_PER_SUBTASK,
    EVALUATOR_PAIRS_PER_SUBTASK,
    EVALUATOR_V2_PAIRS_PER_SUBTASK,
    PAIRS_DIR,
    PAIRS_PER_TASK,
    PARSER_V2_ENTITY_PAIRS,
    write_jsonl,
)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_training/test_generate_pairs_v3.py tests/test_training/test_generate_pairs.py -v`
Expected: All tests PASS (both new and existing).

- [ ] **Step 6: Commit**

```bash
git add scripts/training/config.py scripts/training/generate_training_pairs.py tests/test_training/test_generate_pairs_v3.py
git commit -m "feat: add document-sourced evaluator pairs and community_framing parser pairs (#151)"
```

---

### Task 8: Community Framing Prompt Templates

**Files:**
- Modify: `scripts/training/prompts.py`

- [ ] **Step 1: Add community_framing templates and topic_tag mapping**

Add to the end of `scripts/training/prompts.py`:

```python
# ---------------------------------------------------------------------------
# Community framing: topic_tags → issue_domain mapping
# ---------------------------------------------------------------------------

TOPIC_TAG_TO_ISSUE_DOMAIN: dict[str, str] = {
    "housing": "housing",
    "rent": "housing",
    "tenant": "housing",
    "eviction": "housing",
    "affordable housing": "housing",
    "criminal justice": "criminal_justice",
    "police": "criminal_justice",
    "prison": "criminal_justice",
    "incarceration": "criminal_justice",
    "sentencing": "criminal_justice",
    "voting rights": "voting_rights",
    "ballot": "voting_rights",
    "redistricting": "voting_rights",
    "gerrymandering": "voting_rights",
    "education": "education",
    "school": "education",
    "student": "education",
    "health care": "health",
    "medicaid": "health",
    "hospital": "health",
    "mental health": "health",
    "income": "economic_justice",
    "poverty": "economic_justice",
    "economic inequality": "economic_justice",
    "wealth": "economic_justice",
    "environment": "environmental_justice",
    "pollution": "environmental_justice",
    "climate": "environmental_justice",
}

STRUCTURAL_FRAMES: dict[str, list[str]] = {
    "housing": ["economic_displacement", "gentrification", "redlining", "disinvestment"],
    "criminal_justice": ["over_policing", "mass_incarceration", "sentencing_disparity"],
    "voting_rights": ["voter_suppression", "gerrymandering", "disenfranchisement"],
    "education": ["school_to_prison_pipeline", "funding_disparity", "segregation"],
    "health": ["healthcare_access", "environmental_racism", "insurance_disparity"],
    "economic_justice": ["wealth_gap", "wage_disparity", "hiring_discrimination"],
    "environmental_justice": ["toxic_exposure", "environmental_racism", "climate_injustice"],
}

COMMUNITY_FRAMING_QUESTION_TEMPLATES: list[str] = [
    "Our community in {state} is fighting {issue} — what does the data show?",
    "As an organizer, I need to understand {issue} disparities for {race} families in {state}.",
    "What policies could address {issue} in {state}? Show me the data.",
    "Why is {issue} so much worse for {race} residents in {state} compared to white residents?",
    "Help me explain {issue} data to my neighbors in {state} — what should they know?",
    "What structural factors drive {issue} in {state}?",
    "How has {issue} changed in {state} over the past decade for {race} communities?",
    "Is there data connecting {issue} to {related_issue} in {state}?",
    "What does {bill_number} do about {issue}? Does the data support it?",
    "Our {race} community in {state} is being displaced — what does {issue} data reveal?",
]
```

- [ ] **Step 2: Verify existing tests still pass**

Run: `python -m pytest tests/test_training/test_prompts.py tests/test_training/test_prompts_v2.py -v`
Expected: All existing tests PASS.

- [ ] **Step 3: Commit**

```bash
git add scripts/training/prompts.py
git commit -m "feat: add community_framing prompt templates and topic tag mapping (#151)"
```

---

### Task 9: Explainer Quick Wins — Epochs and LoRA Rank

**Files:**
- Modify: `scripts/training/train.py:53,67-74`

- [ ] **Step 1: Change explainer epochs from 7 to 4**

In `scripts/training/train.py`, in the `ADAPTER_CONFIGS["explainer"]` dict (line 74), change:

```python
        "epochs": 7,
```
to:
```python
        "epochs": 4,
```

- [ ] **Step 2: Change explainer LoRA rank from r=32 to r=16**

In the same `ADAPTER_CONFIGS["explainer"]` dict (line 67), change:

```python
        "r": 32,
```
to:
```python
        "r": 16,
```

And update `lora_alpha` proportionally (line 72) from 64 to 32:

```python
        "lora_alpha": 64,
```
to:
```python
        "lora_alpha": 32,
```

- [ ] **Step 3: Verify no tests break**

Run: `python -m pytest tests/test_training/ -v`
Expected: All existing tests PASS.

- [ ] **Step 4: Commit**

```bash
git add scripts/training/train.py
git commit -m "fix: reduce explainer epochs 7→4 and LoRA rank 32→16 to combat overfitting (#151)"
```

---

### Task 10: Flywheel Metrics Script

**Files:**
- Create: `scripts/training/flywheel_metrics.py`
- Create: `tests/test_training/test_flywheel_metrics.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_training/test_flywheel_metrics.py
"""Tests for flywheel metrics query functions."""

from scripts.training.flywheel_metrics import (
    build_corpus_stats,
)


class TestBuildCorpusStats:
    def test_computes_stats_from_rows(self):
        rows = [
            {"content_type": "policy_bill", "chunk_count": 100, "total_tokens": 5000},
            {"content_type": "research_report", "chunk_count": 50, "total_tokens": 25000},
            {"content_type": "html", "chunk_count": 200, "total_tokens": 100000},
        ]
        stats = build_corpus_stats(rows)
        assert stats["total_documents"] == 350
        assert stats["total_tokens"] == 130000
        assert stats["content_types"]["policy_bill"] == 100
        assert stats["content_types"]["research_report"] == 50
        assert stats["content_types"]["html"] == 200

    def test_empty_rows(self):
        stats = build_corpus_stats([])
        assert stats["total_documents"] == 0
        assert stats["total_tokens"] == 0
        assert stats["content_types"] == {}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_training/test_flywheel_metrics.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.training.flywheel_metrics'`

- [ ] **Step 3: Implement the flywheel metrics script**

```python
# scripts/training/flywheel_metrics.py
"""Flywheel metrics: query document, training, and research quality stats.

Usage:
    python -m scripts.training.flywheel_metrics
    python -m scripts.training.flywheel_metrics --json
"""

from __future__ import annotations

import argparse
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


def build_corpus_stats(rows: list[dict]) -> dict:
    """Build corpus stats from document_chunks aggregation rows.

    Args:
        rows: List of dicts with content_type, chunk_count, total_tokens.

    Returns:
        Dict with total_documents, total_tokens, and content_types breakdown.
    """
    content_types: dict[str, int] = {}
    total_docs = 0
    total_tokens = 0

    for row in rows:
        ct = row["content_type"]
        count = row["chunk_count"]
        tokens = row["total_tokens"]
        content_types[ct] = count
        total_docs += count
        total_tokens += tokens

    return {
        "total_documents": total_docs,
        "total_tokens": total_tokens,
        "content_types": content_types,
    }


def query_corpus_metrics(conn: Any) -> dict:
    """Query document corpus statistics from the database."""
    import psycopg2.extras

    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("""
            SELECT d.content_type,
                   COUNT(dc.id) AS chunk_count,
                   COALESCE(SUM(dc.token_count), 0) AS total_tokens
            FROM document_chunks dc
            JOIN documents d ON dc.document_id = d.id
            GROUP BY d.content_type
            ORDER BY chunk_count DESC
        """)
        rows = [dict(r) for r in cur.fetchall()]

    return build_corpus_stats(rows)


def query_training_metrics(conn: Any) -> list[dict]:
    """Query model evaluation runs ordered by version."""
    import psycopg2.extras

    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("""
            SELECT model_version, task, metrics, ship_decision, created_at
            FROM model_eval_runs
            ORDER BY created_at DESC
            LIMIT 20
        """)
        return [dict(r) for r in cur.fetchall()]


def query_research_quality(conn: Any) -> dict:
    """Query average evaluation scores across recent completed jobs."""
    import psycopg2.extras

    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("""
            SELECT eval_name, AVG(score) AS avg_score, COUNT(*) AS eval_count
            FROM evaluation_results
            WHERE score IS NOT NULL
            GROUP BY eval_name
            ORDER BY eval_name
        """)
        rows = [dict(r) for r in cur.fetchall()]

    return {row["eval_name"]: {"avg_score": float(row["avg_score"]),
                                "count": int(row["eval_count"])} for row in rows}


def main(as_json: bool = False) -> dict:
    """Collect and display all flywheel metrics."""
    from scripts.ingestion.helpers import get_db_connection

    conn = get_db_connection()
    try:
        corpus = query_corpus_metrics(conn)
        training = query_training_metrics(conn)
        research = query_research_quality(conn)
    finally:
        conn.close()

    metrics = {
        "corpus": corpus,
        "training_runs": training,
        "research_quality": research,
    }

    if as_json:
        print(json.dumps(metrics, indent=2, default=str))
    else:
        print("\n=== D4BL Data Flywheel Metrics ===\n")
        print("1. Corpus (Documents In)")
        print(f"   Total chunks: {corpus['total_documents']}")
        print(f"   Total tokens: {corpus['total_tokens']:,}")
        for ct, count in corpus["content_types"].items():
            print(f"     {ct}: {count}")

        print("\n2. Training (Model Quality)")
        for run in training[:5]:
            print(f"   {run['model_version']} / {run['task']}: {run['ship_decision']}")

        print("\n3. Research Quality")
        for name, data in research.items():
            print(f"   {name}: avg={data['avg_score']:.2f} (n={data['count']})")

    return metrics


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Display D4BL data flywheel metrics.")
    parser.add_argument("--json", action="store_true", help="Output as JSON.")
    args = parser.parse_args()
    main(as_json=args.json)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_training/test_flywheel_metrics.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/training/flywheel_metrics.py tests/test_training/test_flywheel_metrics.py
git commit -m "feat: add flywheel metrics query script (#151)"
```

---

### Task 11: Corpus Composition Tagging

When running a training iteration, the corpus stats should be recorded in `model_eval_runs.metrics` so each training run is traceable to its data composition.

**Files:**
- Modify: `scripts/training/flywheel_metrics.py`

- [ ] **Step 1: Add a function to generate corpus stats for training runs**

Add to `scripts/training/flywheel_metrics.py`:

```python
def corpus_stats_for_training(conn: Any) -> dict:
    """Generate corpus composition stats for tagging a training run.

    Returns a dict suitable for embedding in model_eval_runs.metrics:
    {
        "corpus_version": "v3.0",
        "corpus_stats": {
            "structured_passages": <int>,
            "unstructured_passages": <int>,
            "content_types": {"research_report": N, "policy_bill": N, ...},
            "total_tokens": <int>,
        }
    }
    """
    import psycopg2.extras

    doc_stats = query_corpus_metrics(conn)

    # Count structured passages from existing extractors
    structured_tables = [
        "census_indicators", "cdc_health_outcomes", "epa_environmental_justice",
        "police_violence_incidents", "bjs_incarceration", "fbi_crime_stats",
    ]
    structured_count = 0
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        for table in structured_tables:
            try:
                cur.execute(f"SELECT COUNT(*) AS cnt FROM {table}")  # noqa: S608 — allowlisted tables
                structured_count += cur.fetchone()["cnt"]
            except Exception:
                pass

    return {
        "corpus_version": "v3.0",
        "corpus_stats": {
            "structured_passages": structured_count,
            "unstructured_passages": doc_stats["total_documents"],
            "content_types": doc_stats["content_types"],
            "total_tokens": doc_stats["total_tokens"],
        },
    }
```

- [ ] **Step 2: Verify tests pass**

Run: `python -m pytest tests/test_training/test_flywheel_metrics.py -v`
Expected: Existing tests PASS (new function doesn't break anything).

- [ ] **Step 3: Commit**

```bash
git add scripts/training/flywheel_metrics.py
git commit -m "feat: add corpus composition tagging for training runs (#151)"
```

---

### Task 12: Compatibility View Migration (apply AFTER running migrate_documents.py)

This task creates the SQL for replacing `scraped_content_vectors` with a view after data migration. This is a separate migration file applied AFTER running `migrate_documents.py`.

**Files:**
- Create: `supabase/migrations/20260331000002_scraped_content_compatibility_view.sql`

- [ ] **Step 1: Write the migration SQL**

```sql
-- supabase/migrations/20260331000002_scraped_content_compatibility_view.sql
--
-- Step 1: Rename the original table to legacy (preserving data for rollback)
-- Step 2: Create a view with the same name for backward compatibility
--
-- IMPORTANT: Run migrate_documents.py BEFORE applying this migration.
-- Rollback: DROP VIEW scraped_content_vectors;
--           ALTER TABLE scraped_content_vectors_legacy RENAME TO scraped_content_vectors;

ALTER TABLE IF EXISTS scraped_content_vectors
    RENAME TO scraped_content_vectors_legacy;

CREATE OR REPLACE VIEW scraped_content_vectors AS
SELECT
    dc.id,
    d.job_id,
    d.source_url AS url,
    dc.content,
    d.content_type,
    d.metadata,
    dc.embedding,
    d.created_at,
    d.updated_at
FROM document_chunks dc
JOIN documents d ON dc.document_id = d.id;
```

- [ ] **Step 2: Commit**

```bash
git add supabase/migrations/20260331000002_scraped_content_compatibility_view.sql
git commit -m "feat: add scraped_content_vectors compatibility view migration (#151)"
```

---

### Task 13: Run Full Test Suite and Final Commit

**Files:**
- No new files

- [ ] **Step 1: Run the full training test suite**

Run: `python -m pytest tests/test_training/ -v`
Expected: All tests PASS — both new and existing.

- [ ] **Step 2: Run the full project test suite**

Run: `python -m pytest tests/ -v --ignore=tests/test_training/test_integration_models.py`
Expected: All tests PASS (integration tests excluded — they require a live model).

- [ ] **Step 3: Verify all new files are tracked**

Run: `git status`
Expected: No untracked files from this issue. All changes committed in prior tasks.

- [ ] **Step 4: Verify commit history**

Run: `git log --oneline -12`
Expected: Clean sequence of commits for each task, all referencing #151.
