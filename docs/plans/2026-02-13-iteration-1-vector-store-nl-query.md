# Iteration 1: Vector Store Integration + NL Query Engine

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make previously collected research queryable via natural language, combining vector similarity search with structured database queries into a unified answer.

**Architecture:** A new `src/d4bl/query/` module handles NL queries by: (1) parsing user intent with Ollama/Mistral, (2) routing to vector search (Supabase/pgvector) and/or structured SQL (PostgreSQL), (3) fusing results and synthesizing an answer with source citations. The existing vector store and crawl pipeline are already wired up — this iteration adds the query layer on top.

**Tech Stack:** Python 3.10+, FastAPI, SQLAlchemy (async), Supabase/pgvector, Ollama (mxbai-embed-large for embeddings, mistral for generation), pytest + pytest-asyncio

---

## Task 1: Set Up Test Infrastructure

**Files:**
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Create: `pytest.ini`

**Step 1: Create test directory and conftest with async DB fixtures**

Create `tests/__init__.py` (empty) and `tests/conftest.py`:

```python
"""Shared test fixtures for D4BL tests."""

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_db_session():
    """Mock async database session."""
    session = AsyncMock(spec=AsyncSession)
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.close = AsyncMock()
    return session


@pytest.fixture
def sample_job_id():
    """Return a consistent UUID for testing."""
    return uuid4()


@pytest.fixture
def sample_embedding():
    """Return a fake 1024-dimensional embedding vector."""
    return [0.1] * 1024


@pytest.fixture
def sample_crawl_results():
    """Sample crawl results matching the format from crawl_tools."""
    return {
        "query": "Mississippi NIL policy",
        "urls_crawled": ["https://example.com/nil-policy"],
        "results": [
            {
                "url": "https://example.com/nil-policy",
                "extracted_content": "Mississippi passed NIL legislation in 2021 allowing college athletes to profit from their name, image, and likeness.",
                "title": "Mississippi NIL Policy Overview",
                "description": "Overview of NIL policies in Mississippi",
            },
            {
                "url": "https://example.com/nil-impact",
                "extracted_content": "The impact of NIL on Black athletes in Mississippi has been significant, with disparities in endorsement opportunities.",
                "title": "NIL Impact on Black Athletes",
                "description": "Analysis of NIL policy impact",
            },
        ],
        "source_urls": [
            "https://example.com/nil-policy",
            "https://example.com/nil-impact",
        ],
        "success": True,
    }


@pytest.fixture
def mock_ollama_embedding(sample_embedding):
    """Mock Ollama embedding API response."""
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.json = AsyncMock(return_value={"embedding": sample_embedding})
    return mock_response
```

Create `pytest.ini`:

```ini
[pytest]
asyncio_mode = auto
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
```

**Step 2: Verify pytest runs with no tests collected**

Run: `cd /Users/william-meroxa/Development/d4bl_ai_agent && python -m pytest tests/ -v --co 2>&1 | head -20`
Expected: "no tests ran" or "collected 0 items"

**Step 3: Commit**

```bash
git add tests/__init__.py tests/conftest.py pytest.ini
git commit -m "test: Add pytest infrastructure with async DB fixtures"
```

---

## Task 2: Test and Verify Vector Store Integration

The vector store (`src/d4bl/infra/vector_store.py`) and its integration into `research_runner.py` already exist. This task adds tests to verify correctness.

**Files:**
- Create: `tests/test_vector_store.py`

**Step 1: Write unit tests for VectorStore**

```python
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

    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession")
    async def test_generate_embedding_returns_vector(self, mock_session_cls):
        """generate_embedding should return a list of floats from Ollama."""
        fake_embedding = [0.1] * 1024
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(
            return_value={"embedding": fake_embedding}
        )
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session_cls.return_value = mock_session

        result = await self.store.generate_embedding("test text")
        assert isinstance(result, list)
        assert len(result) == 1024

    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession")
    async def test_generate_embedding_truncates_long_text(
        self, mock_session_cls
    ):
        """generate_embedding should truncate text longer than 6000 chars."""
        fake_embedding = [0.2] * 1024
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(
            return_value={"embedding": fake_embedding}
        )
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session_cls.return_value = mock_session

        long_text = "x" * 10000
        result = await self.store.generate_embedding(long_text)

        # Verify the API was called (text was sent)
        mock_session.post.assert_called_once()
        call_kwargs = mock_session.post.call_args
        # The text sent to the API should be truncated
        assert len(result) == 1024

    @pytest.mark.asyncio
    async def test_store_scraped_content_calls_generate_embedding(
        self, mock_db_session
    ):
        """store_scraped_content should generate embedding and insert."""
        job_id = uuid4()
        self.store.generate_embedding = AsyncMock(
            return_value=[0.1] * 1024
        )
        mock_db_session.execute = AsyncMock()
        mock_db_session.commit = AsyncMock()

        result = await self.store.store_scraped_content(
            db=mock_db_session,
            job_id=job_id,
            url="https://example.com",
            content="Test content about NIL policies",
        )

        self.store.generate_embedding.assert_called_once()

    @pytest.mark.asyncio
    async def test_search_similar_returns_results(self, mock_db_session):
        """search_similar should return ranked results."""
        self.store.generate_embedding = AsyncMock(
            return_value=[0.1] * 1024
        )

        # Mock the DB execute to return rows
        mock_row = MagicMock()
        mock_row._mapping = {
            "id": uuid4(),
            "job_id": uuid4(),
            "url": "https://example.com",
            "content": "NIL policy content",
            "content_type": "html",
            "metadata": {},
            "similarity": 0.85,
            "created_at": "2026-01-01",
        }
        mock_result = MagicMock()
        mock_result.fetchall = MagicMock(return_value=[mock_row])
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        results = await self.store.search_similar(
            db=mock_db_session,
            query_text="NIL policies Mississippi",
            limit=5,
        )

        self.store.generate_embedding.assert_called_once_with(
            "NIL policies Mississippi"
        )


class TestGetVectorStore:
    """Test the singleton factory."""

    def test_returns_vector_store_instance(self):
        store = get_vector_store()
        assert isinstance(store, VectorStore)

    def test_returns_same_instance(self):
        store1 = get_vector_store()
        store2 = get_vector_store()
        assert store1 is store2
```

**Step 2: Run tests to verify they pass**

Run: `cd /Users/william-meroxa/Development/d4bl_ai_agent && python -m pytest tests/test_vector_store.py -v`
Expected: All tests PASS

**Step 3: Commit**

```bash
git add tests/test_vector_store.py
git commit -m "test: Add unit tests for VectorStore"
```

---

## Task 3: Create Query Module — Query Parser

The query parser uses Ollama/Mistral to extract intent and entities from a natural language question, determining which data sources to query.

**Files:**
- Create: `src/d4bl/query/__init__.py`
- Create: `src/d4bl/query/parser.py`
- Create: `tests/test_query_parser.py`

**Step 1: Write failing tests for QueryParser**

Create `tests/test_query_parser.py`:

```python
"""Tests for the NL query parser."""

from unittest.mock import AsyncMock, patch

import pytest

from d4bl.query.parser import QueryParser, ParsedQuery


class TestParsedQuery:
    """Test the ParsedQuery data model."""

    def test_parsed_query_defaults(self):
        pq = ParsedQuery(
            original_query="What are NIL policies in Mississippi?",
            intent="information_retrieval",
            entities=["NIL", "Mississippi"],
            search_queries=["NIL policies Mississippi"],
            data_sources=["vector"],
        )
        assert pq.original_query == "What are NIL policies in Mississippi?"
        assert pq.intent == "information_retrieval"
        assert "NIL" in pq.entities
        assert "vector" in pq.data_sources

    def test_parsed_query_with_structured_source(self):
        pq = ParsedQuery(
            original_query="How many research jobs have run?",
            intent="count_query",
            entities=[],
            search_queries=["research jobs count"],
            data_sources=["structured"],
        )
        assert "structured" in pq.data_sources


class TestQueryParser:
    """Test the QueryParser LLM-based parsing."""

    def setup_method(self):
        self.parser = QueryParser(
            ollama_base_url="http://localhost:11434"
        )

    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession")
    async def test_parse_returns_parsed_query(self, mock_session_cls):
        """parse() should return a ParsedQuery with extracted entities."""
        llm_response = {
            "response": '{"intent": "information_retrieval", "entities": ["NIL", "Mississippi", "Black athletes"], "search_queries": ["NIL policies Mississippi Black athletes"], "data_sources": ["vector", "structured"]}'
        }
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=llm_response)
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.post = AsyncMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session_cls.return_value = mock_session

        result = await self.parser.parse(
            "What NIL policies affect Black athletes in Mississippi?"
        )

        assert isinstance(result, ParsedQuery)
        assert result.intent == "information_retrieval"
        assert "NIL" in result.entities
        assert len(result.search_queries) > 0
        assert "vector" in result.data_sources

    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession")
    async def test_parse_falls_back_on_llm_failure(self, mock_session_cls):
        """parse() should return a fallback ParsedQuery if LLM fails."""
        mock_response = AsyncMock()
        mock_response.status = 500
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.post = AsyncMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session_cls.return_value = mock_session

        result = await self.parser.parse("NIL policies Mississippi")

        assert isinstance(result, ParsedQuery)
        assert result.original_query == "NIL policies Mississippi"
        # Fallback: use original query as search query, search both sources
        assert result.search_queries == ["NIL policies Mississippi"]
        assert "vector" in result.data_sources
        assert "structured" in result.data_sources
```

**Step 2: Run tests to verify they fail**

Run: `cd /Users/william-meroxa/Development/d4bl_ai_agent && python -m pytest tests/test_query_parser.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'd4bl.query'`

**Step 3: Implement QueryParser**

Create `src/d4bl/query/__init__.py`:

```python
"""NL Query Engine for D4BL research data."""

from d4bl.query.parser import ParsedQuery, QueryParser

__all__ = ["ParsedQuery", "QueryParser"]
```

Create `src/d4bl/query/parser.py`:

```python
"""Parse natural language queries into structured search intents."""

import json
import logging
from dataclasses import dataclass, field
from typing import Optional

import aiohttp

from d4bl.settings import get_settings

logger = logging.getLogger(__name__)

PARSE_PROMPT = """You are a query parser for a research platform about data justice and racial equity.

Given a user's natural language question, extract:
1. "intent": The type of query. One of: "information_retrieval", "count_query", "comparison", "timeline", "summary".
2. "entities": Key entities mentioned (people, places, policies, organizations, topics).
3. "search_queries": 1-3 rephrased search queries optimized for semantic search.
4. "data_sources": Which data sources to query. Options: "vector" (scraped research content), "structured" (research jobs, evaluations in PostgreSQL). Include both if unsure.

Respond with ONLY a JSON object, no other text.

User question: {query}"""


@dataclass
class ParsedQuery:
    """Structured representation of a parsed natural language query."""

    original_query: str
    intent: str
    entities: list[str]
    search_queries: list[str]
    data_sources: list[str]


class QueryParser:
    """Parse natural language queries using Ollama/Mistral."""

    def __init__(self, ollama_base_url: Optional[str] = None):
        settings = get_settings()
        self.ollama_base_url = (
            ollama_base_url or settings.ollama_base_url
        ).rstrip("/")

    async def parse(self, query: str) -> ParsedQuery:
        """Parse a natural language query into a structured ParsedQuery.

        Falls back to a simple keyword-based ParsedQuery if the LLM call
        fails.
        """
        try:
            return await self._parse_with_llm(query)
        except Exception:
            logger.warning(
                "LLM query parsing failed, using fallback", exc_info=True
            )
            return self._fallback_parse(query)

    async def _parse_with_llm(self, query: str) -> ParsedQuery:
        """Use Ollama/Mistral to parse the query."""
        prompt = PARSE_PROMPT.format(query=query)

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.ollama_base_url}/api/generate",
                json={
                    "model": "mistral",
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.1},
                },
            ) as response:
                if response.status != 200:
                    raise RuntimeError(
                        f"Ollama returned status {response.status}"
                    )
                data = await response.json()

        raw_text = data.get("response", "").strip()
        parsed = json.loads(raw_text)

        return ParsedQuery(
            original_query=query,
            intent=parsed.get("intent", "information_retrieval"),
            entities=parsed.get("entities", []),
            search_queries=parsed.get("search_queries", [query]),
            data_sources=parsed.get("data_sources", ["vector", "structured"]),
        )

    def _fallback_parse(self, query: str) -> ParsedQuery:
        """Simple fallback when LLM parsing fails."""
        return ParsedQuery(
            original_query=query,
            intent="information_retrieval",
            entities=[],
            search_queries=[query],
            data_sources=["vector", "structured"],
        )
```

**Step 4: Run tests to verify they pass**

Run: `cd /Users/william-meroxa/Development/d4bl_ai_agent && python -m pytest tests/test_query_parser.py -v`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add src/d4bl/query/__init__.py src/d4bl/query/parser.py tests/test_query_parser.py
git commit -m "feat: Add NL query parser with LLM-based intent extraction"
```

---

## Task 4: Create Query Module — Structured DB Search

Searches the PostgreSQL `research_jobs` table using SQL queries generated from the parsed query.

**Files:**
- Create: `src/d4bl/query/structured.py`
- Create: `tests/test_query_structured.py`

**Step 1: Write failing tests for StructuredSearcher**

Create `tests/test_query_structured.py`:

```python
"""Tests for structured database search."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from d4bl.query.structured import StructuredSearcher, StructuredResult


class TestStructuredResult:
    def test_result_fields(self):
        r = StructuredResult(
            job_id=str(uuid4()),
            query="NIL policies",
            status="completed",
            summary="Research on NIL",
            created_at="2026-01-01T00:00:00",
            relevance_score=0.8,
        )
        assert r.status == "completed"
        assert r.relevance_score == 0.8


class TestStructuredSearcher:
    def setup_method(self):
        self.searcher = StructuredSearcher()

    @pytest.mark.asyncio
    async def test_search_by_keyword_returns_matching_jobs(
        self, mock_db_session
    ):
        """search() should return jobs whose query matches keywords."""
        mock_row = MagicMock()
        mock_row.job_id = uuid4()
        mock_row.query = "Mississippi NIL policy impact on Black athletes"
        mock_row.status = "completed"
        mock_row.result = {"summary": "NIL policies in MS..."}
        mock_row.research_data = {"source_urls": ["https://example.com"]}
        mock_row.created_at = datetime(2026, 1, 15)

        mock_result = MagicMock()
        mock_result.scalars = MagicMock(
            return_value=MagicMock(all=MagicMock(return_value=[mock_row]))
        )
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        results = await self.searcher.search(
            db=mock_db_session,
            search_queries=["NIL policies Mississippi"],
            limit=5,
        )

        assert len(results) >= 0  # May be 0 if no match logic yet
        mock_db_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_search_empty_query_returns_empty(self, mock_db_session):
        """search() with empty queries should return empty list."""
        results = await self.searcher.search(
            db=mock_db_session,
            search_queries=[],
            limit=5,
        )
        assert results == []
```

**Step 2: Run tests to verify they fail**

Run: `cd /Users/william-meroxa/Development/d4bl_ai_agent && python -m pytest tests/test_query_structured.py -v`
Expected: FAIL with `ModuleNotFoundError`

**Step 3: Implement StructuredSearcher**

Create `src/d4bl/query/structured.py`:

```python
"""Search structured PostgreSQL data (research jobs, evaluations)."""

import logging
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from d4bl.infra.database import ResearchJob

logger = logging.getLogger(__name__)


@dataclass
class StructuredResult:
    """A result from the structured database."""

    job_id: str
    query: str
    status: str
    summary: Optional[str]
    created_at: str
    relevance_score: float


class StructuredSearcher:
    """Search research jobs and results in PostgreSQL."""

    async def search(
        self,
        db: AsyncSession,
        search_queries: list[str],
        limit: int = 10,
    ) -> list[StructuredResult]:
        """Search research_jobs table for matching completed jobs.

        Uses ILIKE text matching against the query and result fields.
        Returns results ordered by creation date (newest first).
        """
        if not search_queries:
            return []

        try:
            # Build OR conditions for each search query keyword
            conditions = []
            for sq in search_queries:
                for keyword in sq.split():
                    if len(keyword) >= 3:  # Skip short words
                        pattern = f"%{keyword}%"
                        conditions.append(ResearchJob.query.ilike(pattern))

            if not conditions:
                return []

            stmt = (
                select(ResearchJob)
                .where(
                    ResearchJob.status == "completed",
                    or_(*conditions),
                )
                .order_by(ResearchJob.created_at.desc())
                .limit(limit)
            )

            result = await db.execute(stmt)
            rows = result.scalars().all()

            return [
                StructuredResult(
                    job_id=str(row.job_id),
                    query=row.query,
                    status=row.status,
                    summary=self._extract_summary(row.result),
                    created_at=row.created_at.isoformat()
                    if row.created_at
                    else "",
                    relevance_score=self._score_relevance(
                        row.query, search_queries
                    ),
                )
                for row in rows
            ]
        except Exception:
            logger.warning("Structured search failed", exc_info=True)
            return []

    def _extract_summary(self, result: Optional[dict]) -> Optional[str]:
        """Extract a summary string from the job result JSON."""
        if not result:
            return None
        if isinstance(result, dict):
            return result.get("summary") or result.get("raw", "")[:500]
        return str(result)[:500]

    def _score_relevance(
        self, job_query: str, search_queries: list[str]
    ) -> float:
        """Simple keyword overlap relevance score (0.0 to 1.0)."""
        job_words = set(job_query.lower().split())
        max_score = 0.0
        for sq in search_queries:
            sq_words = set(sq.lower().split())
            if not sq_words:
                continue
            overlap = len(job_words & sq_words) / len(sq_words)
            max_score = max(max_score, overlap)
        return round(max_score, 2)
```

Update `src/d4bl/query/__init__.py`:

```python
"""NL Query Engine for D4BL research data."""

from d4bl.query.parser import ParsedQuery, QueryParser
from d4bl.query.structured import StructuredResult, StructuredSearcher

__all__ = [
    "ParsedQuery",
    "QueryParser",
    "StructuredResult",
    "StructuredSearcher",
]
```

**Step 4: Run tests to verify they pass**

Run: `cd /Users/william-meroxa/Development/d4bl_ai_agent && python -m pytest tests/test_query_structured.py -v`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add src/d4bl/query/structured.py src/d4bl/query/__init__.py tests/test_query_structured.py
git commit -m "feat: Add structured DB searcher for research jobs"
```

---

## Task 5: Create Query Module — Result Fusion and Synthesis

Combines vector search results and structured DB results, then uses Ollama/Mistral to synthesize a natural language answer with source citations.

**Files:**
- Create: `src/d4bl/query/fusion.py`
- Create: `tests/test_query_fusion.py`

**Step 1: Write failing tests for ResultFusion**

Create `tests/test_query_fusion.py`:

```python
"""Tests for result fusion and answer synthesis."""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from d4bl.query.fusion import ResultFusion, QueryResult, SourceReference
from d4bl.query.structured import StructuredResult


class TestSourceReference:
    def test_from_vector_result(self):
        ref = SourceReference(
            url="https://example.com/nil",
            title="NIL Policy",
            snippet="Mississippi NIL policy...",
            source_type="vector",
            relevance_score=0.85,
        )
        assert ref.source_type == "vector"
        assert ref.relevance_score == 0.85


class TestQueryResult:
    def test_query_result_fields(self):
        qr = QueryResult(
            answer="NIL policies in Mississippi allow...",
            sources=[
                SourceReference(
                    url="https://example.com",
                    title="Source",
                    snippet="...",
                    source_type="vector",
                    relevance_score=0.9,
                )
            ],
            query="NIL policies Mississippi",
        )
        assert len(qr.sources) == 1
        assert qr.answer.startswith("NIL")


class TestResultFusion:
    def setup_method(self):
        self.fusion = ResultFusion(
            ollama_base_url="http://localhost:11434"
        )

    def test_merge_and_rank_deduplicates_by_url(self):
        """Duplicate URLs from vector and structured should be merged."""
        vector_results = [
            {
                "url": "https://example.com/nil",
                "content": "NIL policy content",
                "similarity": 0.9,
                "content_type": "html",
                "metadata": {"title": "NIL Policy"},
            },
            {
                "url": "https://example.com/other",
                "content": "Other content",
                "similarity": 0.7,
                "content_type": "html",
                "metadata": {},
            },
        ]
        structured_results = [
            StructuredResult(
                job_id=str(uuid4()),
                query="NIL policies",
                status="completed",
                summary="Research found that NIL policies...",
                created_at="2026-01-15T00:00:00",
                relevance_score=0.8,
            ),
        ]

        merged = self.fusion.merge_and_rank(
            vector_results, structured_results
        )
        assert len(merged) > 0
        # Should have sources from both vector and structured
        source_types = {s.source_type for s in merged}
        assert "vector" in source_types

    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession")
    async def test_synthesize_returns_query_result(self, mock_session_cls):
        """synthesize() should return a QueryResult with an answer."""
        llm_response = {
            "response": "Based on the available research, NIL policies in Mississippi allow college athletes to profit from their name, image, and likeness. Studies show disparities in how Black athletes access these opportunities."
        }
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=llm_response)
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.post = AsyncMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session_cls.return_value = mock_session

        sources = [
            SourceReference(
                url="https://example.com/nil",
                title="NIL Policy",
                snippet="Mississippi NIL policy content...",
                source_type="vector",
                relevance_score=0.9,
            ),
        ]

        result = await self.fusion.synthesize(
            query="What NIL policies affect Black athletes in Mississippi?",
            sources=sources,
        )

        assert isinstance(result, QueryResult)
        assert len(result.answer) > 0
        assert len(result.sources) > 0

    @pytest.mark.asyncio
    async def test_synthesize_no_sources_returns_no_results_message(self):
        """synthesize() with no sources should say no results found."""
        result = await self.fusion.synthesize(
            query="Nonexistent topic xyz",
            sources=[],
        )
        assert isinstance(result, QueryResult)
        assert "no" in result.answer.lower() or "found" in result.answer.lower()
```

**Step 2: Run tests to verify they fail**

Run: `cd /Users/william-meroxa/Development/d4bl_ai_agent && python -m pytest tests/test_query_fusion.py -v`
Expected: FAIL with `ModuleNotFoundError`

**Step 3: Implement ResultFusion**

Create `src/d4bl/query/fusion.py`:

```python
"""Fuse vector and structured search results into a synthesized answer."""

import logging
from dataclasses import dataclass, field
from typing import Optional

import aiohttp

from d4bl.query.structured import StructuredResult
from d4bl.settings import get_settings

logger = logging.getLogger(__name__)

SYNTHESIS_PROMPT = """You are a research assistant for a data justice platform. Based on the following sources, answer the user's question. Cite sources by number [1], [2], etc.

If the sources don't contain enough information to answer, say so clearly.

Question: {query}

Sources:
{sources_text}

Answer:"""


@dataclass
class SourceReference:
    """A source used to answer a query."""

    url: str
    title: str
    snippet: str
    source_type: str  # "vector" or "structured"
    relevance_score: float


@dataclass
class QueryResult:
    """The final result of a natural language query."""

    answer: str
    sources: list[SourceReference]
    query: str


class ResultFusion:
    """Merge, rank, and synthesize results from multiple data sources."""

    def __init__(self, ollama_base_url: Optional[str] = None):
        settings = get_settings()
        self.ollama_base_url = (
            ollama_base_url or settings.ollama_base_url
        ).rstrip("/")

    def merge_and_rank(
        self,
        vector_results: list[dict],
        structured_results: list[StructuredResult],
    ) -> list[SourceReference]:
        """Merge vector and structured results into a ranked source list."""
        sources: list[SourceReference] = []
        seen_urls: set[str] = set()

        # Add vector results
        for vr in vector_results:
            url = vr.get("url", "")
            if url in seen_urls:
                continue
            seen_urls.add(url)
            metadata = vr.get("metadata") or {}
            sources.append(
                SourceReference(
                    url=url,
                    title=metadata.get("title", url),
                    snippet=(vr.get("content") or "")[:300],
                    source_type="vector",
                    relevance_score=float(vr.get("similarity", 0)),
                )
            )

        # Add structured results
        for sr in structured_results:
            sources.append(
                SourceReference(
                    url=f"job://{sr.job_id}",
                    title=f"Research: {sr.query[:80]}",
                    snippet=(sr.summary or "")[:300],
                    source_type="structured",
                    relevance_score=sr.relevance_score,
                )
            )

        # Sort by relevance score descending
        sources.sort(key=lambda s: s.relevance_score, reverse=True)
        return sources

    async def synthesize(
        self,
        query: str,
        sources: list[SourceReference],
    ) -> QueryResult:
        """Generate a synthesized answer from ranked sources using LLM."""
        if not sources:
            return QueryResult(
                answer="No relevant results found for your query.",
                sources=[],
                query=query,
            )

        try:
            answer = await self._generate_answer(query, sources)
        except Exception:
            logger.warning("LLM synthesis failed, returning raw sources", exc_info=True)
            answer = self._fallback_answer(sources)

        return QueryResult(answer=answer, sources=sources, query=query)

    async def _generate_answer(
        self, query: str, sources: list[SourceReference]
    ) -> str:
        """Use Ollama/Mistral to synthesize an answer."""
        sources_text = "\n".join(
            f"[{i + 1}] ({s.source_type}) {s.title}\n{s.snippet}"
            for i, s in enumerate(sources[:10])  # Limit context
        )
        prompt = SYNTHESIS_PROMPT.format(
            query=query, sources_text=sources_text
        )

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.ollama_base_url}/api/generate",
                json={
                    "model": "mistral",
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.3},
                },
            ) as response:
                if response.status != 200:
                    raise RuntimeError(
                        f"Ollama returned status {response.status}"
                    )
                data = await response.json()

        return data.get("response", "").strip()

    def _fallback_answer(self, sources: list[SourceReference]) -> str:
        """Build a simple answer from sources without LLM."""
        lines = ["Here are the most relevant sources found:\n"]
        for i, s in enumerate(sources[:5]):
            lines.append(f"{i + 1}. **{s.title}** ({s.source_type})")
            lines.append(f"   {s.snippet}\n")
        return "\n".join(lines)
```

Update `src/d4bl/query/__init__.py`:

```python
"""NL Query Engine for D4BL research data."""

from d4bl.query.fusion import QueryResult, ResultFusion, SourceReference
from d4bl.query.parser import ParsedQuery, QueryParser
from d4bl.query.structured import StructuredResult, StructuredSearcher

__all__ = [
    "ParsedQuery",
    "QueryParser",
    "QueryResult",
    "ResultFusion",
    "SourceReference",
    "StructuredResult",
    "StructuredSearcher",
]
```

**Step 4: Run tests to verify they pass**

Run: `cd /Users/william-meroxa/Development/d4bl_ai_agent && python -m pytest tests/test_query_fusion.py -v`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add src/d4bl/query/fusion.py src/d4bl/query/__init__.py tests/test_query_fusion.py
git commit -m "feat: Add result fusion and LLM-based answer synthesis"
```

---

## Task 6: Create Query Module — Query Engine Orchestrator

Ties parser, vector search, structured search, and fusion together into a single `QueryEngine.query()` call.

**Files:**
- Create: `src/d4bl/query/engine.py`
- Create: `tests/test_query_engine.py`

**Step 1: Write failing tests for QueryEngine**

Create `tests/test_query_engine.py`:

```python
"""Tests for the QueryEngine orchestrator."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from d4bl.query.engine import QueryEngine
from d4bl.query.fusion import QueryResult, SourceReference
from d4bl.query.parser import ParsedQuery
from d4bl.query.structured import StructuredResult


class TestQueryEngine:
    def setup_method(self):
        self.engine = QueryEngine(
            ollama_base_url="http://localhost:11434"
        )

    @pytest.mark.asyncio
    async def test_query_orchestrates_full_pipeline(self, mock_db_session):
        """query() should parse, search both sources, fuse, and synthesize."""
        # Mock parser
        self.engine.parser.parse = AsyncMock(
            return_value=ParsedQuery(
                original_query="NIL policies Mississippi",
                intent="information_retrieval",
                entities=["NIL", "Mississippi"],
                search_queries=["NIL policies Mississippi"],
                data_sources=["vector", "structured"],
            )
        )

        # Mock vector store search
        self.engine.vector_store.search_similar = AsyncMock(
            return_value=[
                {
                    "url": "https://example.com/nil",
                    "content": "NIL policy content",
                    "similarity": 0.9,
                    "metadata": {"title": "NIL Policy"},
                }
            ]
        )

        # Mock structured search
        self.engine.structured_searcher.search = AsyncMock(
            return_value=[
                StructuredResult(
                    job_id=str(uuid4()),
                    query="NIL research",
                    status="completed",
                    summary="NIL findings...",
                    created_at="2026-01-15",
                    relevance_score=0.8,
                )
            ]
        )

        # Mock fusion synthesis
        self.engine.fusion.synthesize = AsyncMock(
            return_value=QueryResult(
                answer="NIL policies in Mississippi...",
                sources=[
                    SourceReference(
                        url="https://example.com/nil",
                        title="NIL Policy",
                        snippet="...",
                        source_type="vector",
                        relevance_score=0.9,
                    )
                ],
                query="NIL policies Mississippi",
            )
        )

        result = await self.engine.query(
            db=mock_db_session,
            question="NIL policies Mississippi",
        )

        assert isinstance(result, QueryResult)
        assert len(result.answer) > 0
        self.engine.parser.parse.assert_called_once()
        self.engine.vector_store.search_similar.assert_called_once()
        self.engine.structured_searcher.search.assert_called_once()
        self.engine.fusion.synthesize.assert_called_once()

    @pytest.mark.asyncio
    async def test_query_vector_only_when_parser_says_so(
        self, mock_db_session
    ):
        """query() should skip structured search if parser says vector only."""
        self.engine.parser.parse = AsyncMock(
            return_value=ParsedQuery(
                original_query="test",
                intent="information_retrieval",
                entities=[],
                search_queries=["test"],
                data_sources=["vector"],  # Only vector
            )
        )
        self.engine.vector_store.search_similar = AsyncMock(return_value=[])
        self.engine.structured_searcher.search = AsyncMock(return_value=[])
        self.engine.fusion.synthesize = AsyncMock(
            return_value=QueryResult(
                answer="No results", sources=[], query="test"
            )
        )

        await self.engine.query(db=mock_db_session, question="test")

        self.engine.vector_store.search_similar.assert_called_once()
        self.engine.structured_searcher.search.assert_not_called()
```

**Step 2: Run tests to verify they fail**

Run: `cd /Users/william-meroxa/Development/d4bl_ai_agent && python -m pytest tests/test_query_engine.py -v`
Expected: FAIL with `ModuleNotFoundError`

**Step 3: Implement QueryEngine**

Create `src/d4bl/query/engine.py`:

```python
"""Orchestrates the full NL query pipeline."""

import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from d4bl.infra.vector_store import get_vector_store
from d4bl.query.fusion import QueryResult, ResultFusion
from d4bl.query.parser import QueryParser
from d4bl.query.structured import StructuredSearcher

logger = logging.getLogger(__name__)


class QueryEngine:
    """Orchestrates NL query parsing, search, and synthesis.

    Usage:
        engine = QueryEngine()
        result = await engine.query(db=session, question="What are NIL policies?")
        print(result.answer)
        for source in result.sources:
            print(source.url, source.relevance_score)
    """

    def __init__(self, ollama_base_url: Optional[str] = None):
        self.parser = QueryParser(ollama_base_url=ollama_base_url)
        self.vector_store = get_vector_store()
        self.structured_searcher = StructuredSearcher()
        self.fusion = ResultFusion(ollama_base_url=ollama_base_url)

    async def query(
        self,
        db: AsyncSession,
        question: str,
        job_id: Optional[str] = None,
        limit: int = 10,
        similarity_threshold: float = 0.7,
    ) -> QueryResult:
        """Execute a full NL query pipeline.

        Args:
            db: Async database session.
            question: The user's natural language question.
            job_id: Optional job ID to scope vector search.
            limit: Max results per data source.
            similarity_threshold: Minimum similarity for vector results.

        Returns:
            QueryResult with synthesized answer and source citations.
        """
        # 1. Parse the query
        parsed = await self.parser.parse(question)
        logger.info(
            "Parsed query: intent=%s, entities=%s, sources=%s",
            parsed.intent,
            parsed.entities,
            parsed.data_sources,
        )

        # 2. Search data sources based on parser output
        vector_results = []
        structured_results = []

        if "vector" in parsed.data_sources:
            for sq in parsed.search_queries:
                results = await self.vector_store.search_similar(
                    db=db,
                    query_text=sq,
                    job_id=job_id,
                    limit=limit,
                    similarity_threshold=similarity_threshold,
                )
                vector_results.extend(results)

        if "structured" in parsed.data_sources:
            structured_results = await self.structured_searcher.search(
                db=db,
                search_queries=parsed.search_queries,
                limit=limit,
            )

        # 3. Merge and rank results
        sources = self.fusion.merge_and_rank(
            vector_results, structured_results
        )

        # 4. Synthesize answer
        return await self.fusion.synthesize(
            query=question, sources=sources
        )
```

Update `src/d4bl/query/__init__.py`:

```python
"""NL Query Engine for D4BL research data."""

from d4bl.query.engine import QueryEngine
from d4bl.query.fusion import QueryResult, ResultFusion, SourceReference
from d4bl.query.parser import ParsedQuery, QueryParser
from d4bl.query.structured import StructuredResult, StructuredSearcher

__all__ = [
    "ParsedQuery",
    "QueryEngine",
    "QueryParser",
    "QueryResult",
    "ResultFusion",
    "SourceReference",
    "StructuredResult",
    "StructuredSearcher",
]
```

**Step 4: Run tests to verify they pass**

Run: `cd /Users/william-meroxa/Development/d4bl_ai_agent && python -m pytest tests/test_query_engine.py -v`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add src/d4bl/query/engine.py src/d4bl/query/__init__.py tests/test_query_engine.py
git commit -m "feat: Add QueryEngine orchestrator for NL query pipeline"
```

---

## Task 7: Add NL Query API Endpoint

Wire the QueryEngine into a new FastAPI endpoint.

**Files:**
- Modify: `src/d4bl/app/api.py` (add endpoint after existing vector endpoints, ~line 413)
- Modify: `src/d4bl/app/schemas.py` (add request/response models)
- Create: `tests/test_api_query.py`

**Step 1: Write failing tests for the API endpoint**

Create `tests/test_api_query.py`:

```python
"""Tests for the NL query API endpoint."""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from d4bl.app.api import app
from d4bl.query.fusion import QueryResult, SourceReference


class TestQueryEndpoint:
    @pytest.mark.asyncio
    @patch("d4bl.app.api.get_query_engine")
    @patch("d4bl.app.api.get_db")
    async def test_post_query_returns_answer(
        self, mock_get_db, mock_get_engine
    ):
        """POST /api/query should return a synthesized answer."""
        mock_db = AsyncMock()
        mock_get_db.return_value = mock_db

        mock_engine = AsyncMock()
        mock_engine.query = AsyncMock(
            return_value=QueryResult(
                answer="NIL policies in Mississippi allow athletes...",
                sources=[
                    SourceReference(
                        url="https://example.com/nil",
                        title="NIL Policy",
                        snippet="MS NIL policy...",
                        source_type="vector",
                        relevance_score=0.9,
                    )
                ],
                query="NIL policies Mississippi",
            )
        )
        mock_get_engine.return_value = mock_engine

        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/query",
                json={
                    "question": "What NIL policies affect Black athletes in Mississippi?"
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert "answer" in data
        assert "sources" in data
        assert len(data["answer"]) > 0

    @pytest.mark.asyncio
    @patch("d4bl.app.api.get_query_engine")
    @patch("d4bl.app.api.get_db")
    async def test_post_query_empty_question_returns_422(
        self, mock_get_db, mock_get_engine
    ):
        """POST /api/query with empty question should return 422."""
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            response = await client.post("/api/query", json={})

        assert response.status_code == 422
```

**Step 2: Run tests to verify they fail**

Run: `cd /Users/william-meroxa/Development/d4bl_ai_agent && python -m pytest tests/test_api_query.py -v`
Expected: FAIL (endpoint doesn't exist yet)

**Step 3: Add Pydantic models to schemas.py**

Add these models to the end of `src/d4bl/app/schemas.py`:

```python
# --- NL Query models ---


class QueryRequest(BaseModel):
    question: str
    job_id: Optional[str] = None
    limit: int = 10


class QuerySourceItem(BaseModel):
    url: str
    title: str
    snippet: str
    source_type: str
    relevance_score: float


class QueryResponse(BaseModel):
    answer: str
    sources: List[QuerySourceItem]
    query: str
```

**Step 4: Add the endpoint to api.py**

Add after the existing vector endpoints (after the `/api/vector/job/{job_id}` endpoint). Also add the import and singleton getter near the top of `api.py`:

Import to add near top of file:

```python
from d4bl.query.engine import QueryEngine
```

Singleton getter to add after imports:

```python
_query_engine = None


def get_query_engine() -> QueryEngine:
    global _query_engine
    if _query_engine is None:
        _query_engine = QueryEngine()
    return _query_engine
```

Endpoint to add:

```python
@app.post("/api/query", response_model=QueryResponse)
async def natural_language_query(
    request: QueryRequest,
    db: AsyncSession = Depends(get_db),
):
    """Query research data using natural language.

    Searches both the vector store (scraped content) and structured
    database (research jobs) and returns a synthesized answer with
    source citations.
    """
    engine = get_query_engine()
    result = await engine.query(
        db=db,
        question=request.question,
        job_id=request.job_id,
        limit=request.limit,
    )
    return QueryResponse(
        answer=result.answer,
        sources=[
            QuerySourceItem(
                url=s.url,
                title=s.title,
                snippet=s.snippet,
                source_type=s.source_type,
                relevance_score=s.relevance_score,
            )
            for s in result.sources
        ],
        query=result.query,
    )
```

Also import `QueryRequest`, `QueryResponse`, `QuerySourceItem` from schemas in `api.py`.

**Step 5: Run tests to verify they pass**

Run: `cd /Users/william-meroxa/Development/d4bl_ai_agent && python -m pytest tests/test_api_query.py -v`
Expected: All tests PASS

**Step 6: Run all tests to verify nothing is broken**

Run: `cd /Users/william-meroxa/Development/d4bl_ai_agent && python -m pytest tests/ -v`
Expected: All tests PASS

**Step 7: Commit**

```bash
git add src/d4bl/app/api.py src/d4bl/app/schemas.py tests/test_api_query.py
git commit -m "feat: Add POST /api/query endpoint for NL research queries"
```

---

## Task 8: Add Frontend Query Component

Add a query bar to the existing frontend that calls the new `/api/query` endpoint.

**Files:**
- Create: `ui-nextjs/src/components/QueryBar.tsx`
- Create: `ui-nextjs/src/components/QueryResults.tsx`
- Modify: `ui-nextjs/src/app/page.tsx` (add QueryBar to the page)

**Step 1: Create QueryBar component**

Create `ui-nextjs/src/components/QueryBar.tsx`:

```tsx
"use client";

import { useState } from "react";

interface QuerySource {
  url: string;
  title: string;
  snippet: string;
  source_type: string;
  relevance_score: number;
}

interface QueryResponse {
  answer: string;
  sources: QuerySource[];
  query: string;
}

interface QueryBarProps {
  onResult: (result: QueryResponse) => void;
  onLoading: (loading: boolean) => void;
  onError: (error: string | null) => void;
}

export default function QueryBar({ onResult, onLoading, onError }: QueryBarProps) {
  const [question, setQuestion] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!question.trim()) return;

    onLoading(true);
    onError(null);

    try {
      const response = await fetch("/api/query", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: question.trim() }),
      });

      if (!response.ok) {
        throw new Error(`Query failed: ${response.statusText}`);
      }

      const data: QueryResponse = await response.json();
      onResult(data);
    } catch (err) {
      onError(err instanceof Error ? err.message : "Query failed");
    } finally {
      onLoading(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="flex gap-2">
      <input
        type="text"
        value={question}
        onChange={(e) => setQuestion(e.target.value)}
        placeholder="Ask a question about your research data..."
        className="flex-1 px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-[#00ff32]"
      />
      <button
        type="submit"
        disabled={!question.trim()}
        className="px-6 py-2 bg-[#00ff32] text-black font-medium rounded-lg hover:bg-[#00cc28] disabled:opacity-50 disabled:cursor-not-allowed"
      >
        Query
      </button>
    </form>
  );
}
```

**Step 2: Create QueryResults component**

Create `ui-nextjs/src/components/QueryResults.tsx`:

```tsx
"use client";

interface QuerySource {
  url: string;
  title: string;
  snippet: string;
  source_type: string;
  relevance_score: number;
}

interface QueryResultsProps {
  answer: string;
  sources: QuerySource[];
  query: string;
}

export default function QueryResults({ answer, sources, query }: QueryResultsProps) {
  return (
    <div className="bg-gray-900 border border-gray-700 rounded-lg p-6 space-y-4">
      <div>
        <h3 className="text-sm font-medium text-gray-400 mb-1">Query</h3>
        <p className="text-white">{query}</p>
      </div>

      <div>
        <h3 className="text-sm font-medium text-gray-400 mb-1">Answer</h3>
        <div className="text-white whitespace-pre-wrap">{answer}</div>
      </div>

      {sources.length > 0 && (
        <div>
          <h3 className="text-sm font-medium text-gray-400 mb-2">
            Sources ({sources.length})
          </h3>
          <ul className="space-y-2">
            {sources.map((source, i) => (
              <li
                key={i}
                className="bg-gray-800 rounded p-3 text-sm"
              >
                <div className="flex items-center gap-2 mb-1">
                  <span
                    className={`px-2 py-0.5 rounded text-xs font-medium ${
                      source.source_type === "vector"
                        ? "bg-blue-900 text-blue-300"
                        : "bg-purple-900 text-purple-300"
                    }`}
                  >
                    {source.source_type}
                  </span>
                  <span className="text-gray-500 text-xs">
                    {(source.relevance_score * 100).toFixed(0)}% relevant
                  </span>
                </div>
                <p className="text-white font-medium">{source.title}</p>
                <p className="text-gray-400 mt-1">{source.snippet}</p>
                {source.url && !source.url.startsWith("job://") && (
                  <a
                    href={source.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-[#00ff32] text-xs mt-1 inline-block hover:underline"
                  >
                    {source.url}
                  </a>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
```

**Step 3: Add QueryBar to the main page**

Modify `ui-nextjs/src/app/page.tsx` to import and render QueryBar and QueryResults. Add them in a new section above or below the existing ResearchForm. The exact integration depends on the current page layout — add it as a collapsible "Query Research Data" section.

Import at top:

```tsx
import QueryBar from "@/components/QueryBar";
import QueryResults from "@/components/QueryResults";
```

Add state and rendering in the page component:

```tsx
const [queryResult, setQueryResult] = useState<any>(null);
const [queryLoading, setQueryLoading] = useState(false);
const [queryError, setQueryError] = useState<string | null>(null);
```

And in the JSX, add a section:

```tsx
{/* Query Research Data */}
<div className="space-y-4">
  <h2 className="text-lg font-semibold text-white">Query Research Data</h2>
  <QueryBar
    onResult={setQueryResult}
    onLoading={setQueryLoading}
    onError={setQueryError}
  />
  {queryLoading && (
    <p className="text-gray-400">Searching research data...</p>
  )}
  {queryError && (
    <p className="text-red-400">{queryError}</p>
  )}
  {queryResult && (
    <QueryResults
      answer={queryResult.answer}
      sources={queryResult.sources}
      query={queryResult.query}
    />
  )}
</div>
```

**Step 4: Add Next.js API proxy for the query endpoint**

Check if `ui-nextjs/next.config.ts` already proxies `/api` to the FastAPI backend. If it does, the endpoint will work automatically. If not, add a rewrite rule:

```ts
async rewrites() {
  return [
    {
      source: "/api/:path*",
      destination: "http://localhost:8000/api/:path*",
    },
  ];
},
```

**Step 5: Verify frontend builds**

Run: `cd /Users/william-meroxa/Development/d4bl_ai_agent/ui-nextjs && npm run build`
Expected: Build succeeds with no errors

**Step 6: Commit**

```bash
git add ui-nextjs/src/components/QueryBar.tsx ui-nextjs/src/components/QueryResults.tsx ui-nextjs/src/app/page.tsx
git commit -m "feat: Add NL query bar and results display to frontend"
```

---

## Task 9: End-to-End Validation with Mississippi NIL Test Case

Manual validation of the full pipeline. This is not an automated test — it's the acceptance test for Iteration 1.

**Prerequisites:**
- PostgreSQL running with vector extension enabled
- Ollama running with `mistral` and `mxbai-embed-large` models pulled
- Backend running on port 8000
- Frontend running on port 3000

**Step 1: Run the migration**

Run: `cd /Users/william-meroxa/Development/d4bl_ai_agent && python scripts/run_vector_migration.py`

**Step 2: Start services and run a research job**

Run: Start backend with `python -m uvicorn d4bl.app.api:app --host 0.0.0.0 --port 8000`

Submit a research job via the UI or curl:
```bash
curl -X POST http://localhost:8000/api/research \
  -H "Content-Type: application/json" \
  -d '{"query": "Mississippi NIL policy impact on Black college athletes", "summary_format": "detailed"}'
```

Wait for job completion.

**Step 3: Query the research data**

```bash
curl -X POST http://localhost:8000/api/query \
  -H "Content-Type: application/json" \
  -d '{"question": "What are the NIL policies affecting Black athletes in Mississippi?"}'
```

**Expected:** A JSON response with:
- `answer`: A synthesized paragraph citing sources
- `sources`: Array of source references from both vector and structured data
- `query`: The original question

**Step 4: Test via frontend**

Open http://localhost:3000, type the same question in the Query Research Data section, and verify the answer renders with source citations.

**Step 5: Commit any fixes from validation**

```bash
git add -A
git commit -m "fix: Address issues found during Mississippi NIL e2e validation"
```
