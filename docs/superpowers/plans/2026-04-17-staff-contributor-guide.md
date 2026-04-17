# Staff Contributor Guide Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an admin upload UI, review queue, and staff tutorial page so non-technical D4BL staff can contribute data sources, documents, example queries, and feature requests through the web app.

**Architecture:** New `upload_routes.py` router with 6 endpoints, 4 new database tables (`uploads`, `uploaded_datasets`, `example_queries`, `feature_requests`), frontend upload tabs on `/admin`, a review queue component, and a `/guide` tutorial page. File uploads go to Supabase Storage; metadata and review state live in Postgres.

**Tech Stack:** FastAPI (backend), SQLAlchemy + asyncpg (ORM), Supabase Storage (files), Next.js App Router + React 19 (frontend), Tailwind CSS 4 (styling)

---

## File Structure

### Backend (create)
- `src/d4bl/app/upload_routes.py` — APIRouter with all upload/review endpoints
- `supabase/migrations/20260417000001_create_upload_tables.sql` — migration for 4 new tables
- `tests/test_upload_api.py` — backend tests for upload endpoints

### Backend (modify)
- `src/d4bl/infra/database.py` — add `Upload`, `UploadedDataset`, `ExampleQuery`, `FeatureRequest` models
- `src/d4bl/app/schemas.py` — add upload-related Pydantic schemas
- `src/d4bl/app/api.py` — include the new upload router

### Frontend (create)
- `ui-nextjs/components/admin/UploadDataSource.tsx` — data source upload form
- `ui-nextjs/components/admin/UploadDocument.tsx` — document upload form
- `ui-nextjs/components/admin/UploadQuery.tsx` — example query form
- `ui-nextjs/components/admin/UploadHistory.tsx` — shared upload history list
- `ui-nextjs/components/admin/ReviewQueue.tsx` — admin review queue tab
- `ui-nextjs/components/admin/ReviewDetail.tsx` — expandable review detail panel
- `ui-nextjs/app/guide/page.tsx` — staff tutorial page
- `ui-nextjs/components/guide/GuideSection.tsx` — collapsible accordion section
- `ui-nextjs/components/guide/FeatureRequestForm.tsx` — in-app feature request form

### Frontend (modify)
- `ui-nextjs/app/admin/page.tsx` — add upload + review queue tabs
- `ui-nextjs/components/NavBar.tsx` — add Guide link for authenticated users

---

## Task 1: Database Migration + Models

**Files:**
- Create: `supabase/migrations/20260417000001_create_upload_tables.sql`
- Modify: `src/d4bl/infra/database.py`

- [ ] **Step 1: Write the migration SQL**

Create `supabase/migrations/20260417000001_create_upload_tables.sql`:

```sql
-- Upload status tracking
CREATE TYPE upload_type AS ENUM ('datasource', 'document', 'query', 'feature_request');
CREATE TYPE upload_status AS ENUM ('pending_review', 'approved', 'rejected', 'processing', 'live');
CREATE TYPE feature_request_status AS ENUM ('open', 'acknowledged', 'planned', 'closed');

CREATE TABLE uploads (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    upload_type upload_type NOT NULL,
    status upload_status NOT NULL DEFAULT 'pending_review',
    file_path TEXT,
    original_filename TEXT,
    file_size_bytes INTEGER,
    metadata JSONB NOT NULL DEFAULT '{}',
    reviewer_id UUID,
    reviewer_notes TEXT,
    reviewed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_uploads_user_id ON uploads(user_id);
CREATE INDEX idx_uploads_status ON uploads(status);
CREATE INDEX idx_uploads_type ON uploads(upload_type);
CREATE INDEX idx_uploads_created_at ON uploads(created_at DESC);

CREATE TABLE uploaded_datasets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    upload_id UUID NOT NULL REFERENCES uploads(id) ON DELETE CASCADE,
    row_index INTEGER NOT NULL,
    data JSONB NOT NULL,
    UNIQUE(upload_id, row_index)
);

CREATE INDEX idx_uploaded_datasets_upload_id ON uploaded_datasets(upload_id);

CREATE TABLE example_queries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    upload_id UUID NOT NULL REFERENCES uploads(id) ON DELETE CASCADE,
    query_text TEXT NOT NULL,
    summary_format TEXT NOT NULL DEFAULT 'detailed',
    description TEXT NOT NULL,
    curated_answer TEXT,
    relevant_sources JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_example_queries_upload_id ON example_queries(upload_id);

CREATE TABLE feature_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    upload_id UUID REFERENCES uploads(id) ON DELETE SET NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    who_benefits TEXT NOT NULL,
    example TEXT,
    status feature_request_status NOT NULL DEFAULT 'open',
    admin_notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_feature_requests_user_id ON feature_requests(user_id);
CREATE INDEX idx_feature_requests_status ON feature_requests(status);
```

- [ ] **Step 2: Add SQLAlchemy models**

Add to `src/d4bl/infra/database.py`, after the existing model definitions:

```python
class Upload(Base):
    __tablename__ = "uploads"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(PG_UUID(as_uuid=True), nullable=False, index=True)
    upload_type = Column(String(20), nullable=False)  # datasource|document|query|feature_request
    status = Column(String(20), nullable=False, default="pending_review", index=True)
    file_path = Column(Text, nullable=True)
    original_filename = Column(Text, nullable=True)
    file_size_bytes = Column(Integer, nullable=True)
    metadata_ = Column("metadata", JSONB, nullable=False, default=dict)
    reviewer_id = Column(PG_UUID(as_uuid=True), nullable=True)
    reviewer_notes = Column(Text, nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utc_now, index=True)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utc_now, onupdate=_utc_now)


class UploadedDataset(Base):
    __tablename__ = "uploaded_datasets"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    upload_id = Column(PG_UUID(as_uuid=True), ForeignKey("uploads.id", ondelete="CASCADE"), nullable=False, index=True)
    row_index = Column(Integer, nullable=False)
    data = Column(JSONB, nullable=False)


class ExampleQuery(Base):
    __tablename__ = "example_queries"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    upload_id = Column(PG_UUID(as_uuid=True), ForeignKey("uploads.id", ondelete="CASCADE"), nullable=False, index=True)
    query_text = Column(Text, nullable=False)
    summary_format = Column(Text, nullable=False, default="detailed")
    description = Column(Text, nullable=False)
    curated_answer = Column(Text, nullable=True)
    relevant_sources = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utc_now)


class FeatureRequest(Base):
    __tablename__ = "feature_requests"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(PG_UUID(as_uuid=True), nullable=False, index=True)
    upload_id = Column(PG_UUID(as_uuid=True), ForeignKey("uploads.id", ondelete="SET NULL"), nullable=True)
    title = Column(Text, nullable=False)
    description = Column(Text, nullable=False)
    who_benefits = Column(Text, nullable=False)
    example = Column(Text, nullable=True)
    status = Column(String(20), nullable=False, default="open", index=True)
    admin_notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utc_now)
```

Note: The `metadata` column is mapped to `metadata_` in Python to avoid shadowing SQLAlchemy's internal `metadata` attribute. This follows the pattern: `metadata_ = Column("metadata", JSONB, ...)`.

- [ ] **Step 3: Verify models import cleanly**

Run: `cd /Users/william-meroxa/Development/d4bl_ai_agent/.worktrees/staff-guide && source .venv/bin/activate && python -c "from d4bl.infra.database import Upload, UploadedDataset, ExampleQuery, FeatureRequest; print('OK')"`

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add supabase/migrations/20260417000001_create_upload_tables.sql src/d4bl/infra/database.py
git commit -m "feat: add Upload, UploadedDataset, ExampleQuery, FeatureRequest models (#188)"
```

---

## Task 2: Pydantic Schemas

**Files:**
- Modify: `src/d4bl/app/schemas.py`
- Test: `tests/test_upload_api.py`

- [ ] **Step 1: Write failing tests for schemas**

Create `tests/test_upload_api.py`:

```python
"""Tests for staff upload API schemas and endpoints."""

import pytest
from pydantic import ValidationError


class TestUploadSchemas:
    """Validate upload request/response schemas."""

    def test_datasource_upload_valid(self):
        from d4bl.app.schemas import DataSourceUploadRequest

        req = DataSourceUploadRequest(
            source_name="County Health Rankings 2024",
            description="County-level health outcomes by race",
            geographic_level="county",
            data_year=2024,
        )
        assert req.source_name == "County Health Rankings 2024"
        assert req.geographic_level == "county"

    def test_datasource_upload_invalid_geo_level(self):
        from d4bl.app.schemas import DataSourceUploadRequest

        with pytest.raises(ValidationError):
            DataSourceUploadRequest(
                source_name="Test",
                description="Test",
                geographic_level="zipcode",
                data_year=2024,
            )

    def test_datasource_upload_blank_name(self):
        from d4bl.app.schemas import DataSourceUploadRequest

        with pytest.raises(ValidationError):
            DataSourceUploadRequest(
                source_name="  ",
                description="Test",
                geographic_level="county",
                data_year=2024,
            )

    def test_document_upload_valid(self):
        from d4bl.app.schemas import DocumentUploadRequest

        req = DocumentUploadRequest(
            title="Vera Incarceration Report",
            document_type="report",
            topic_tags=["incarceration", "racial-disparity"],
        )
        assert req.title == "Vera Incarceration Report"

    def test_document_upload_invalid_type(self):
        from d4bl.app.schemas import DocumentUploadRequest

        with pytest.raises(ValidationError):
            DocumentUploadRequest(
                title="Test",
                document_type="spreadsheet",
                topic_tags=[],
            )

    def test_example_query_valid(self):
        from d4bl.app.schemas import ExampleQueryRequest

        req = ExampleQueryRequest(
            query_text="What are the racial disparities in housing discrimination in Mississippi?",
            summary_format="detailed",
            description="Tests equity-focused housing query",
        )
        assert req.summary_format == "detailed"

    def test_example_query_too_long(self):
        from d4bl.app.schemas import ExampleQueryRequest

        with pytest.raises(ValidationError):
            ExampleQueryRequest(
                query_text="x" * 2001,
                summary_format="detailed",
                description="Too long",
            )

    def test_feature_request_valid(self):
        from d4bl.app.schemas import FeatureRequestCreate

        req = FeatureRequestCreate(
            title="Add HMDA mortgage data",
            description="Include Home Mortgage Disclosure Act data for lending disparity analysis",
            who_benefits="Researchers studying housing discrimination",
        )
        assert req.title == "Add HMDA mortgage data"

    def test_feature_request_blank_title(self):
        from d4bl.app.schemas import FeatureRequestCreate

        with pytest.raises(ValidationError):
            FeatureRequestCreate(
                title="",
                description="Test",
                who_benefits="Test",
            )

    def test_upload_review_valid(self):
        from d4bl.app.schemas import UploadReviewRequest

        req = UploadReviewRequest(action="approve", notes="Looks good")
        assert req.action == "approve"

    def test_upload_review_reject_requires_notes(self):
        from d4bl.app.schemas import UploadReviewRequest

        with pytest.raises(ValidationError):
            UploadReviewRequest(action="reject", notes=None)

    def test_upload_response_schema(self):
        from d4bl.app.schemas import UploadResponse

        resp = UploadResponse(
            id="00000000-0000-0000-0000-000000000001",
            upload_type="datasource",
            status="pending_review",
            original_filename="data.csv",
            metadata={"source_name": "Test"},
            created_at="2026-04-17T00:00:00Z",
        )
        assert resp.status == "pending_review"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/william-meroxa/Development/d4bl_ai_agent/.worktrees/staff-guide && source .venv/bin/activate && python -m pytest tests/test_upload_api.py -v 2>&1 | head -40`

Expected: FAIL — `ImportError: cannot import name 'DataSourceUploadRequest'`

- [ ] **Step 3: Add Pydantic schemas**

Add to `src/d4bl/app/schemas.py`:

```python
# --- Staff Upload Schemas ---


class DataSourceUploadRequest(BaseModel):
    source_name: str
    description: str
    geographic_level: Literal["state", "county", "tract"]
    data_year: int
    source_url: str | None = None
    category_tags: list[str] | None = None

    @field_validator("source_name")
    @classmethod
    def source_name_not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Source name cannot be empty")
        return v.strip()


class DocumentUploadRequest(BaseModel):
    title: str
    document_type: Literal["report", "article", "policy_brief", "other"]
    topic_tags: list[str] | None = None
    url: str | None = None

    @field_validator("title")
    @classmethod
    def title_not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Title cannot be empty")
        return v.strip()


class ExampleQueryRequest(BaseModel):
    query_text: str
    summary_format: Literal["brief", "detailed"] = "detailed"
    description: str
    curated_answer: str | None = None
    relevant_sources: list[str] | None = None

    @field_validator("query_text")
    @classmethod
    def query_text_valid(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Query text cannot be empty")
        if len(v) > 2000:
            raise ValueError("Query text must be under 2000 characters")
        return v.strip()


class FeatureRequestCreate(BaseModel):
    title: str
    description: str
    who_benefits: str
    example: str | None = None

    @field_validator("title")
    @classmethod
    def title_not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Title cannot be empty")
        return v.strip()

    @field_validator("description")
    @classmethod
    def description_not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Description cannot be empty")
        return v.strip()


class UploadReviewRequest(BaseModel):
    action: Literal["approve", "reject"]
    notes: str | None = None

    @model_validator(mode="after")
    def reject_requires_notes(self) -> "UploadReviewRequest":
        if self.action == "reject" and not self.notes:
            raise ValueError("Notes are required when rejecting an upload")
        return self


class UploadResponse(BaseModel):
    id: str
    upload_type: str
    status: str
    original_filename: str | None = None
    file_size_bytes: int | None = None
    metadata: dict | None = None
    reviewer_notes: str | None = None
    reviewed_at: str | None = None
    created_at: str
```

Also add the `model_validator` import at the top of `schemas.py` if not already present:

```python
from pydantic import BaseModel, Field, field_validator, model_validator
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/william-meroxa/Development/d4bl_ai_agent/.worktrees/staff-guide && python -m pytest tests/test_upload_api.py -v`

Expected: all 12 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/d4bl/app/schemas.py tests/test_upload_api.py
git commit -m "feat: add Pydantic schemas for staff upload API (#188)"
```

---

## Task 3: Upload API Routes (Create + List)

**Files:**
- Create: `src/d4bl/app/upload_routes.py`
- Modify: `src/d4bl/app/api.py` (include router)
- Test: `tests/test_upload_api.py`

- [ ] **Step 1: Write failing endpoint tests**

Add to `tests/test_upload_api.py`:

```python
from httpx import ASGITransport, AsyncClient

from d4bl.app.api import app


@pytest.fixture
async def admin_client(override_admin_auth):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def user_client(override_auth):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def unauth_client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestUploadEndpoints:
    """Test upload API endpoints."""

    @pytest.mark.asyncio
    async def test_upload_query_requires_auth(self, unauth_client):
        resp = await unauth_client.post(
            "/api/admin/uploads/query",
            json={
                "query_text": "Test query",
                "summary_format": "detailed",
                "description": "Test description",
            },
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_upload_query_success(self, user_client, mock_db_session):
        from d4bl.app.api import app
        from d4bl.infra.database import get_db

        app.dependency_overrides[get_db] = lambda: mock_db_session

        # Mock the execute to return the upload ID
        from unittest.mock import AsyncMock, MagicMock
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = None  # no existing
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        resp = await user_client.post(
            "/api/admin/uploads/query",
            json={
                "query_text": "What are racial disparities in housing?",
                "summary_format": "detailed",
                "description": "Tests equity-focused housing query",
            },
        )
        # Endpoint should call db.add + db.commit
        assert resp.status_code == 200
        data = resp.json()
        assert data["upload_type"] == "query"
        assert data["status"] == "pending_review"

        app.dependency_overrides.pop(get_db, None)

    @pytest.mark.asyncio
    async def test_upload_feature_request_success(self, user_client, mock_db_session):
        from d4bl.app.api import app
        from d4bl.infra.database import get_db

        app.dependency_overrides[get_db] = lambda: mock_db_session
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = None
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        resp = await user_client.post(
            "/api/admin/uploads/feature-request",
            json={
                "title": "Add HMDA data",
                "description": "Include HMDA mortgage data",
                "who_benefits": "Housing researchers",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["upload_type"] == "feature_request"

        app.dependency_overrides.pop(get_db, None)

    @pytest.mark.asyncio
    async def test_list_uploads_requires_auth(self, unauth_client):
        resp = await unauth_client.get("/api/admin/uploads")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_review_requires_admin(self, user_client):
        resp = await user_client.patch(
            "/api/admin/uploads/00000000-0000-0000-0000-000000000001/review",
            json={"action": "approve"},
        )
        assert resp.status_code == 403
```

Add the needed import at top of file:

```python
from unittest.mock import AsyncMock, MagicMock

from tests.conftest import MOCK_ADMIN, MOCK_USER
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/william-meroxa/Development/d4bl_ai_agent/.worktrees/staff-guide && python -m pytest tests/test_upload_api.py::TestUploadEndpoints -v 2>&1 | head -30`

Expected: FAIL — 404 (routes don't exist yet)

- [ ] **Step 3: Create upload_routes.py**

Create `src/d4bl/app/upload_routes.py`:

```python
"""Staff upload API routes.

Endpoints for uploading data sources, documents, example queries,
and feature requests. Includes admin review workflow.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from d4bl.app.auth import CurrentUser, get_current_user, require_admin
from d4bl.app.schemas import (
    DataSourceUploadRequest,
    DocumentUploadRequest,
    ExampleQueryRequest,
    FeatureRequestCreate,
    UploadResponse,
    UploadReviewRequest,
)
from d4bl.infra.database import (
    ExampleQuery,
    FeatureRequest,
    Upload,
    get_db,
)

router = APIRouter(tags=["uploads"])

MAX_DATASOURCE_SIZE = 50 * 1024 * 1024  # 50 MB
MAX_DOCUMENT_SIZE = 25 * 1024 * 1024  # 25 MB
ALLOWED_DATASOURCE_EXT = {".csv", ".xlsx"}
ALLOWED_DOCUMENT_EXT = {".pdf", ".docx"}


def _upload_to_response(upload: Upload) -> dict:
    """Convert an Upload ORM object to a response dict."""
    return {
        "id": str(upload.id),
        "upload_type": upload.upload_type,
        "status": upload.status,
        "original_filename": upload.original_filename,
        "file_size_bytes": upload.file_size_bytes,
        "metadata": upload.metadata_,
        "reviewer_notes": upload.reviewer_notes,
        "reviewed_at": upload.reviewed_at.isoformat() if upload.reviewed_at else None,
        "created_at": upload.created_at.isoformat() if upload.created_at else "",
    }


@router.post("/api/admin/uploads/datasource", response_model=UploadResponse)
async def upload_datasource(
    file: UploadFile = File(...),
    source_name: str = Form(...),
    description: str = Form(...),
    geographic_level: str = Form(...),
    data_year: int = Form(...),
    source_url: str | None = Form(None),
    category_tags: str | None = Form(None),
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Upload a CSV/XLSX data source file for review."""
    # Validate file extension
    ext = "." + (file.filename or "").rsplit(".", 1)[-1].lower() if file.filename else ""
    if ext not in ALLOWED_DATASOURCE_EXT:
        raise HTTPException(400, f"File type {ext} not allowed. Use: {ALLOWED_DATASOURCE_EXT}")

    # Validate via schema (reuses validators)
    DataSourceUploadRequest(
        source_name=source_name,
        description=description,
        geographic_level=geographic_level,
        data_year=data_year,
    )

    # Read file content to check size
    content = await file.read()
    if len(content) > MAX_DATASOURCE_SIZE:
        raise HTTPException(400, f"File too large. Max {MAX_DATASOURCE_SIZE // (1024*1024)}MB")
    if len(content) == 0:
        raise HTTPException(400, "File is empty")

    # Store file in Supabase Storage (placeholder — wired in Task 4)
    upload_id = uuid4()
    storage_path = f"datasource/{user.id}/{upload_id}_{file.filename}"

    tags = [t.strip() for t in category_tags.split(",")] if category_tags else None

    upload = Upload(
        id=upload_id,
        user_id=user.id,
        upload_type="datasource",
        file_path=storage_path,
        original_filename=file.filename,
        file_size_bytes=len(content),
        metadata_={
            "source_name": source_name,
            "description": description,
            "geographic_level": geographic_level,
            "data_year": data_year,
            "source_url": source_url,
            "category_tags": tags,
        },
    )
    db.add(upload)
    await db.commit()
    return _upload_to_response(upload)


@router.post("/api/admin/uploads/document", response_model=UploadResponse)
async def upload_document(
    title: str = Form(...),
    document_type: str = Form(...),
    topic_tags: str | None = Form(None),
    url: str | None = Form(None),
    file: UploadFile | None = File(None),
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Upload a document file or submit a URL for review."""
    if not file and not url:
        raise HTTPException(400, "Either a file or URL is required")

    DocumentUploadRequest(
        title=title,
        document_type=document_type,
        topic_tags=[t.strip() for t in topic_tags.split(",")] if topic_tags else None,
        url=url,
    )

    upload_id = uuid4()
    storage_path = None
    file_size = None
    filename = None

    if file:
        ext = "." + (file.filename or "").rsplit(".", 1)[-1].lower() if file.filename else ""
        if ext not in ALLOWED_DOCUMENT_EXT:
            raise HTTPException(400, f"File type {ext} not allowed. Use: {ALLOWED_DOCUMENT_EXT}")
        content = await file.read()
        if len(content) > MAX_DOCUMENT_SIZE:
            raise HTTPException(400, f"File too large. Max {MAX_DOCUMENT_SIZE // (1024*1024)}MB")
        storage_path = f"document/{user.id}/{upload_id}_{file.filename}"
        file_size = len(content)
        filename = file.filename

    tags = [t.strip() for t in topic_tags.split(",")] if topic_tags else None

    upload = Upload(
        id=upload_id,
        user_id=user.id,
        upload_type="document",
        file_path=storage_path,
        original_filename=filename,
        file_size_bytes=file_size,
        metadata_={
            "title": title,
            "document_type": document_type,
            "topic_tags": tags,
            "url": url,
        },
    )
    db.add(upload)
    await db.commit()
    return _upload_to_response(upload)


@router.post("/api/admin/uploads/query", response_model=UploadResponse)
async def upload_example_query(
    body: ExampleQueryRequest,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Submit an example research query for review."""
    upload_id = uuid4()
    upload = Upload(
        id=upload_id,
        user_id=user.id,
        upload_type="query",
        metadata_={
            "query_text": body.query_text,
            "summary_format": body.summary_format,
            "description": body.description,
            "curated_answer": body.curated_answer,
            "relevant_sources": body.relevant_sources,
        },
    )
    db.add(upload)

    example = ExampleQuery(
        upload_id=upload_id,
        query_text=body.query_text,
        summary_format=body.summary_format,
        description=body.description,
        curated_answer=body.curated_answer,
        relevant_sources=body.relevant_sources,
    )
    db.add(example)
    await db.commit()
    return _upload_to_response(upload)


@router.post("/api/admin/uploads/feature-request", response_model=UploadResponse)
async def submit_feature_request(
    body: FeatureRequestCreate,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Submit a feature request."""
    upload_id = uuid4()
    upload = Upload(
        id=upload_id,
        user_id=user.id,
        upload_type="feature_request",
        metadata_={
            "title": body.title,
            "description": body.description,
            "who_benefits": body.who_benefits,
            "example": body.example,
        },
    )
    db.add(upload)

    feature_req = FeatureRequest(
        user_id=user.id,
        upload_id=upload_id,
        title=body.title,
        description=body.description,
        who_benefits=body.who_benefits,
        example=body.example,
    )
    db.add(feature_req)
    await db.commit()
    return _upload_to_response(upload)


@router.get("/api/admin/uploads")
async def list_uploads(
    upload_type: str | None = None,
    status: str | None = None,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List uploads. Non-admins see only their own uploads."""
    clauses = []
    params: dict = {}

    if not user.is_admin:
        clauses.append("u.user_id = CAST(:user_id AS uuid)")
        params["user_id"] = str(user.id)

    if upload_type:
        clauses.append("u.upload_type = :upload_type")
        params["upload_type"] = upload_type

    if status:
        clauses.append("u.status = :status")
        params["status"] = status

    where = "WHERE " + " AND ".join(clauses) if clauses else ""

    query = text(f"""
        SELECT u.id, u.upload_type, u.status, u.original_filename,
               u.file_size_bytes, u.metadata, u.reviewer_notes,
               u.reviewed_at, u.created_at, u.user_id,
               p.email AS uploader_email, p.display_name AS uploader_name
        FROM uploads u
        LEFT JOIN profiles p ON p.id = u.user_id
        {where}
        ORDER BY u.created_at DESC
        LIMIT 100
    """)

    result = await db.execute(query, params)
    rows = result.mappings().all()

    return [
        {
            "id": str(r["id"]),
            "upload_type": r["upload_type"],
            "status": r["status"],
            "original_filename": r["original_filename"],
            "file_size_bytes": r["file_size_bytes"],
            "metadata": r["metadata"],
            "reviewer_notes": r["reviewer_notes"],
            "reviewed_at": r["reviewed_at"].isoformat() if r["reviewed_at"] else None,
            "created_at": r["created_at"].isoformat() if r["created_at"] else "",
            "uploader_email": r["uploader_email"],
            "uploader_name": r["uploader_name"],
        }
        for r in rows
    ]


@router.patch("/api/admin/uploads/{upload_id}/review")
async def review_upload(
    upload_id: str,
    body: UploadReviewRequest,
    user: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Approve or reject an upload (admin only)."""
    result = await db.execute(
        text("SELECT id, status FROM uploads WHERE id = CAST(:uid AS uuid)"),
        {"uid": upload_id},
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(404, "Upload not found")
    if row["status"] != "pending_review":
        raise HTTPException(400, f"Upload is already {row['status']}")

    new_status = "approved" if body.action == "approve" else "rejected"
    now = datetime.now(timezone.utc)

    await db.execute(
        text("""
            UPDATE uploads
            SET status = :status, reviewer_id = CAST(:reviewer_id AS uuid),
                reviewer_notes = :notes, reviewed_at = :reviewed_at,
                updated_at = :updated_at
            WHERE id = CAST(:uid AS uuid)
        """),
        {
            "status": new_status,
            "reviewer_id": str(user.id),
            "notes": body.notes,
            "reviewed_at": now,
            "updated_at": now,
            "uid": upload_id,
        },
    )
    await db.commit()

    return {"id": upload_id, "status": new_status, "reviewed_at": now.isoformat()}
```

- [ ] **Step 4: Register router in api.py**

Add to the imports section of `src/d4bl/app/api.py`:

```python
from d4bl.app.upload_routes import router as upload_router
```

Add to the `include_router` block (after the existing routers around line 564):

```python
app.include_router(upload_router)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /Users/william-meroxa/Development/d4bl_ai_agent/.worktrees/staff-guide && python -m pytest tests/test_upload_api.py -v`

Expected: all tests PASS

- [ ] **Step 6: Run full test suite to check for regressions**

Run: `cd /Users/william-meroxa/Development/d4bl_ai_agent/.worktrees/staff-guide && python -m pytest tests/ -x -q 2>&1 | tail -20`

Expected: no new failures

- [ ] **Step 7: Commit**

```bash
git add src/d4bl/app/upload_routes.py src/d4bl/app/api.py tests/test_upload_api.py
git commit -m "feat: add upload API routes — create, list, review (#188)"
```

---

## Task 4: Frontend Upload Tabs

**Files:**
- Create: `ui-nextjs/components/admin/UploadDataSource.tsx`
- Create: `ui-nextjs/components/admin/UploadDocument.tsx`
- Create: `ui-nextjs/components/admin/UploadQuery.tsx`
- Create: `ui-nextjs/components/admin/UploadHistory.tsx`
- Modify: `ui-nextjs/app/admin/page.tsx`

- [ ] **Step 1: Create UploadHistory component**

Create `ui-nextjs/components/admin/UploadHistory.tsx`:

```tsx
'use client';

import { useCallback, useEffect, useState } from 'react';
import { useAuth } from '@/lib/auth-context';
import { API_BASE } from '@/lib/api';

interface UploadRecord {
  id: string;
  upload_type: string;
  status: string;
  original_filename: string | null;
  metadata: Record<string, unknown>;
  reviewer_notes: string | null;
  created_at: string;
}

const STATUS_COLORS: Record<string, string> = {
  pending_review: 'bg-yellow-600',
  approved: 'bg-green-600',
  rejected: 'bg-red-600',
  processing: 'bg-blue-600',
  live: 'bg-[#00ff32] text-black',
};

export default function UploadHistory({
  uploadType,
  refreshKey,
}: {
  uploadType: string;
  refreshKey: number;
}) {
  const { session } = useAuth();
  const [uploads, setUploads] = useState<UploadRecord[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchUploads = useCallback(async () => {
    if (!session?.access_token) return;
    setLoading(true);
    try {
      const resp = await fetch(
        `${API_BASE}/api/admin/uploads?upload_type=${uploadType}`,
        { headers: { Authorization: `Bearer ${session.access_token}` } }
      );
      if (resp.ok) {
        setUploads(await resp.json());
      }
    } finally {
      setLoading(false);
    }
  }, [session?.access_token, uploadType]);

  useEffect(() => {
    fetchUploads();
  }, [fetchUploads, refreshKey]);

  if (loading) return <p className="text-gray-400 text-sm">Loading history...</p>;
  if (uploads.length === 0) return <p className="text-gray-500 text-sm">No uploads yet.</p>;

  return (
    <div className="mt-6">
      <h4 className="text-sm font-semibold text-gray-300 mb-2">Your Uploads</h4>
      <div className="space-y-2">
        {uploads.map((u) => (
          <div
            key={u.id}
            className="flex items-center justify-between bg-[#1a1a1a] border border-[#404040] rounded-lg px-4 py-3"
          >
            <div>
              <span className="text-white text-sm">
                {u.original_filename ||
                  (u.metadata as Record<string, string>)?.title ||
                  (u.metadata as Record<string, string>)?.query_text?.slice(0, 60) ||
                  'Upload'}
              </span>
              <span className="text-gray-500 text-xs ml-2">
                {new Date(u.created_at).toLocaleDateString()}
              </span>
            </div>
            <div className="flex items-center gap-2">
              <span
                className={`text-xs px-2 py-1 rounded ${STATUS_COLORS[u.status] || 'bg-gray-600'}`}
              >
                {u.status.replace('_', ' ')}
              </span>
              {u.reviewer_notes && (
                <span className="text-gray-400 text-xs max-w-48 truncate" title={u.reviewer_notes}>
                  {u.reviewer_notes}
                </span>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Create UploadDataSource component**

Create `ui-nextjs/components/admin/UploadDataSource.tsx`:

```tsx
'use client';

import { FormEvent, useState } from 'react';
import { useAuth } from '@/lib/auth-context';
import { API_BASE } from '@/lib/api';
import UploadHistory from './UploadHistory';

export default function UploadDataSource() {
  const { session } = useAuth();
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setSubmitting(true);
    setMessage(null);

    const form = new FormData(e.currentTarget);

    try {
      const resp = await fetch(`${API_BASE}/api/admin/uploads/datasource`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${session?.access_token}` },
        body: form,
      });
      if (resp.ok) {
        setMessage({ type: 'success', text: 'Data source uploaded! It will be reviewed by an admin.' });
        (e.target as HTMLFormElement).reset();
        setRefreshKey((k) => k + 1);
      } else {
        const err = await resp.json();
        setMessage({ type: 'error', text: err.detail || 'Upload failed' });
      }
    } catch {
      setMessage({ type: 'error', text: 'Network error' });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div>
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="block text-sm text-gray-300 mb-1">File (.csv or .xlsx) *</label>
          <input
            type="file"
            name="file"
            accept=".csv,.xlsx"
            required
            className="w-full text-sm text-gray-300 file:mr-4 file:py-2 file:px-4 file:rounded file:border-0 file:bg-[#404040] file:text-white hover:file:bg-[#505050]"
          />
        </div>
        <div>
          <label className="block text-sm text-gray-300 mb-1">Source Name *</label>
          <input
            type="text"
            name="source_name"
            required
            placeholder="e.g., County Health Rankings 2024"
            className="w-full bg-[#1a1a1a] border border-[#404040] rounded px-3 py-2 text-white text-sm placeholder:text-gray-600"
          />
        </div>
        <div>
          <label className="block text-sm text-gray-300 mb-1">Description *</label>
          <textarea
            name="description"
            required
            rows={2}
            placeholder="What does this data contain?"
            className="w-full bg-[#1a1a1a] border border-[#404040] rounded px-3 py-2 text-white text-sm placeholder:text-gray-600"
          />
        </div>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm text-gray-300 mb-1">Geographic Level *</label>
            <select
              name="geographic_level"
              required
              className="w-full bg-[#1a1a1a] border border-[#404040] rounded px-3 py-2 text-white text-sm"
            >
              <option value="state">State</option>
              <option value="county">County</option>
              <option value="tract">Census Tract</option>
            </select>
          </div>
          <div>
            <label className="block text-sm text-gray-300 mb-1">Data Year *</label>
            <input
              type="number"
              name="data_year"
              required
              min={2000}
              max={2030}
              defaultValue={2024}
              className="w-full bg-[#1a1a1a] border border-[#404040] rounded px-3 py-2 text-white text-sm"
            />
          </div>
        </div>
        <div>
          <label className="block text-sm text-gray-300 mb-1">Source URL (optional)</label>
          <input
            type="url"
            name="source_url"
            placeholder="https://..."
            className="w-full bg-[#1a1a1a] border border-[#404040] rounded px-3 py-2 text-white text-sm placeholder:text-gray-600"
          />
        </div>
        <div>
          <label className="block text-sm text-gray-300 mb-1">Category Tags (optional, comma-separated)</label>
          <input
            type="text"
            name="category_tags"
            placeholder="health, county-level, racial-disparity"
            className="w-full bg-[#1a1a1a] border border-[#404040] rounded px-3 py-2 text-white text-sm placeholder:text-gray-600"
          />
        </div>
        {message && (
          <p className={`text-sm ${message.type === 'success' ? 'text-[#00ff32]' : 'text-red-400'}`}>
            {message.text}
          </p>
        )}
        <button
          type="submit"
          disabled={submitting}
          className="bg-[#00ff32] text-black font-semibold px-6 py-2 rounded hover:bg-[#00cc28] disabled:opacity-50"
        >
          {submitting ? 'Uploading...' : 'Upload Data Source'}
        </button>
      </form>
      <UploadHistory uploadType="datasource" refreshKey={refreshKey} />
    </div>
  );
}
```

- [ ] **Step 3: Create UploadDocument component**

Create `ui-nextjs/components/admin/UploadDocument.tsx`:

```tsx
'use client';

import { FormEvent, useState } from 'react';
import { useAuth } from '@/lib/auth-context';
import { API_BASE } from '@/lib/api';
import UploadHistory from './UploadHistory';

export default function UploadDocument() {
  const { session } = useAuth();
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const [mode, setMode] = useState<'file' | 'url'>('file');

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setSubmitting(true);
    setMessage(null);

    const form = new FormData(e.currentTarget);

    try {
      const resp = await fetch(`${API_BASE}/api/admin/uploads/document`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${session?.access_token}` },
        body: form,
      });
      if (resp.ok) {
        setMessage({ type: 'success', text: 'Document submitted for review!' });
        (e.target as HTMLFormElement).reset();
        setRefreshKey((k) => k + 1);
      } else {
        const err = await resp.json();
        setMessage({ type: 'error', text: err.detail || 'Upload failed' });
      }
    } catch {
      setMessage({ type: 'error', text: 'Network error' });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div>
      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="flex gap-2 mb-2">
          <button
            type="button"
            onClick={() => setMode('file')}
            className={`text-sm px-3 py-1 rounded ${mode === 'file' ? 'bg-[#00ff32] text-black' : 'bg-[#404040] text-gray-300'}`}
          >
            Upload File
          </button>
          <button
            type="button"
            onClick={() => setMode('url')}
            className={`text-sm px-3 py-1 rounded ${mode === 'url' ? 'bg-[#00ff32] text-black' : 'bg-[#404040] text-gray-300'}`}
          >
            Submit URL
          </button>
        </div>
        {mode === 'file' ? (
          <div>
            <label className="block text-sm text-gray-300 mb-1">File (.pdf or .docx) *</label>
            <input
              type="file"
              name="file"
              accept=".pdf,.docx"
              required={mode === 'file'}
              className="w-full text-sm text-gray-300 file:mr-4 file:py-2 file:px-4 file:rounded file:border-0 file:bg-[#404040] file:text-white hover:file:bg-[#505050]"
            />
          </div>
        ) : (
          <div>
            <label className="block text-sm text-gray-300 mb-1">Article URL *</label>
            <input
              type="url"
              name="url"
              required={mode === 'url'}
              placeholder="https://..."
              className="w-full bg-[#1a1a1a] border border-[#404040] rounded px-3 py-2 text-white text-sm placeholder:text-gray-600"
            />
          </div>
        )}
        <div>
          <label className="block text-sm text-gray-300 mb-1">Title *</label>
          <input
            type="text"
            name="title"
            required
            placeholder="e.g., Vera Institute Incarceration Report 2024"
            className="w-full bg-[#1a1a1a] border border-[#404040] rounded px-3 py-2 text-white text-sm placeholder:text-gray-600"
          />
        </div>
        <div>
          <label className="block text-sm text-gray-300 mb-1">Document Type *</label>
          <select
            name="document_type"
            required
            className="w-full bg-[#1a1a1a] border border-[#404040] rounded px-3 py-2 text-white text-sm"
          >
            <option value="report">Report</option>
            <option value="article">Article</option>
            <option value="policy_brief">Policy Brief</option>
            <option value="other">Other</option>
          </select>
        </div>
        <div>
          <label className="block text-sm text-gray-300 mb-1">Topic Tags (optional, comma-separated)</label>
          <input
            type="text"
            name="topic_tags"
            placeholder="incarceration, racial-disparity, policy"
            className="w-full bg-[#1a1a1a] border border-[#404040] rounded px-3 py-2 text-white text-sm placeholder:text-gray-600"
          />
        </div>
        {message && (
          <p className={`text-sm ${message.type === 'success' ? 'text-[#00ff32]' : 'text-red-400'}`}>
            {message.text}
          </p>
        )}
        <button
          type="submit"
          disabled={submitting}
          className="bg-[#00ff32] text-black font-semibold px-6 py-2 rounded hover:bg-[#00cc28] disabled:opacity-50"
        >
          {submitting ? 'Submitting...' : 'Submit Document'}
        </button>
      </form>
      <UploadHistory uploadType="document" refreshKey={refreshKey} />
    </div>
  );
}
```

- [ ] **Step 4: Create UploadQuery component**

Create `ui-nextjs/components/admin/UploadQuery.tsx`:

```tsx
'use client';

import { FormEvent, useState } from 'react';
import { useAuth } from '@/lib/auth-context';
import { API_BASE } from '@/lib/api';
import UploadHistory from './UploadHistory';

export default function UploadQuery() {
  const { session } = useAuth();
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setSubmitting(true);
    setMessage(null);

    const formData = new FormData(e.currentTarget);
    const body = {
      query_text: formData.get('query_text') as string,
      summary_format: formData.get('summary_format') as string,
      description: formData.get('description') as string,
      curated_answer: (formData.get('curated_answer') as string) || null,
      relevant_sources: null,
    };

    try {
      const resp = await fetch(`${API_BASE}/api/admin/uploads/query`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${session?.access_token}`,
        },
        body: JSON.stringify(body),
      });
      if (resp.ok) {
        setMessage({ type: 'success', text: 'Example query submitted for review!' });
        (e.target as HTMLFormElement).reset();
        setRefreshKey((k) => k + 1);
      } else {
        const err = await resp.json();
        setMessage({ type: 'error', text: err.detail || 'Submit failed' });
      }
    } catch {
      setMessage({ type: 'error', text: 'Network error' });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div>
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="block text-sm text-gray-300 mb-1">Research Query *</label>
          <textarea
            name="query_text"
            required
            rows={3}
            maxLength={2000}
            placeholder="e.g., What are the racial disparities in housing discrimination in Mississippi?"
            className="w-full bg-[#1a1a1a] border border-[#404040] rounded px-3 py-2 text-white text-sm placeholder:text-gray-600"
          />
        </div>
        <div>
          <label className="block text-sm text-gray-300 mb-1">Summary Format *</label>
          <select
            name="summary_format"
            required
            className="w-full bg-[#1a1a1a] border border-[#404040] rounded px-3 py-2 text-white text-sm"
          >
            <option value="detailed">Detailed</option>
            <option value="brief">Brief</option>
          </select>
        </div>
        <div>
          <label className="block text-sm text-gray-300 mb-1">
            Why is this a good example? *
          </label>
          <textarea
            name="description"
            required
            rows={2}
            placeholder="Explain what makes this query useful for others"
            className="w-full bg-[#1a1a1a] border border-[#404040] rounded px-3 py-2 text-white text-sm placeholder:text-gray-600"
          />
        </div>
        <div>
          <label className="block text-sm text-gray-300 mb-1">
            Curated Answer (optional)
          </label>
          <textarea
            name="curated_answer"
            rows={4}
            placeholder="If you have a known good answer, paste it here"
            className="w-full bg-[#1a1a1a] border border-[#404040] rounded px-3 py-2 text-white text-sm placeholder:text-gray-600"
          />
        </div>
        {message && (
          <p className={`text-sm ${message.type === 'success' ? 'text-[#00ff32]' : 'text-red-400'}`}>
            {message.text}
          </p>
        )}
        <button
          type="submit"
          disabled={submitting}
          className="bg-[#00ff32] text-black font-semibold px-6 py-2 rounded hover:bg-[#00cc28] disabled:opacity-50"
        >
          {submitting ? 'Submitting...' : 'Submit Example Query'}
        </button>
      </form>
      <UploadHistory uploadType="query" refreshKey={refreshKey} />
    </div>
  );
}
```

- [ ] **Step 5: Add upload tabs to admin page**

Modify `ui-nextjs/app/admin/page.tsx`:

Add imports at the top:

```tsx
import UploadDataSource from '@/components/admin/UploadDataSource';
import UploadDocument from '@/components/admin/UploadDocument';
import UploadQuery from '@/components/admin/UploadQuery';
```

Add a `uploadTab` state variable alongside the existing state:

```tsx
const [uploadTab, setUploadTab] = useState<'datasource' | 'document' | 'query'>('datasource');
```

Add a new section after the existing "Data Ingestion" section (before User Management). Use the same card styling as the existing sections:

```tsx
{/* Staff Uploads */}
<div className="bg-[#1a1a1a] border border-[#404040] rounded-lg p-6">
  <h2 className="text-xl font-bold text-white mb-4">Staff Uploads</h2>
  <div className="flex gap-2 mb-6">
    {(['datasource', 'document', 'query'] as const).map((tab) => (
      <button
        key={tab}
        onClick={() => setUploadTab(tab)}
        className={`px-4 py-2 rounded text-sm font-medium ${
          uploadTab === tab
            ? 'bg-[#00ff32] text-black'
            : 'bg-[#404040] text-gray-300 hover:bg-[#505050]'
        }`}
      >
        {tab === 'datasource' ? 'Data Sources' : tab === 'document' ? 'Documents' : 'Example Queries'}
      </button>
    ))}
  </div>
  {uploadTab === 'datasource' && <UploadDataSource />}
  {uploadTab === 'document' && <UploadDocument />}
  {uploadTab === 'query' && <UploadQuery />}
</div>
```

- [ ] **Step 6: Verify the frontend builds**

Run: `cd /Users/william-meroxa/Development/d4bl_ai_agent/.worktrees/staff-guide/ui-nextjs && npm run build 2>&1 | tail -20`

Expected: build succeeds

- [ ] **Step 7: Commit**

```bash
git add ui-nextjs/components/admin/UploadDataSource.tsx ui-nextjs/components/admin/UploadDocument.tsx ui-nextjs/components/admin/UploadQuery.tsx ui-nextjs/components/admin/UploadHistory.tsx ui-nextjs/app/admin/page.tsx
git commit -m "feat: add staff upload tabs to admin page — data sources, documents, queries (#188)"
```

---

## Task 5: Review Queue

**Files:**
- Create: `ui-nextjs/components/admin/ReviewQueue.tsx`
- Create: `ui-nextjs/components/admin/ReviewDetail.tsx`
- Modify: `ui-nextjs/app/admin/page.tsx`

- [ ] **Step 1: Create ReviewDetail component**

Create `ui-nextjs/components/admin/ReviewDetail.tsx`:

```tsx
'use client';

import { useState } from 'react';
import { useAuth } from '@/lib/auth-context';
import { API_BASE } from '@/lib/api';

interface Upload {
  id: string;
  upload_type: string;
  status: string;
  original_filename: string | null;
  file_size_bytes: number | null;
  metadata: Record<string, unknown>;
  uploader_email: string | null;
  uploader_name: string | null;
  created_at: string;
}

export default function ReviewDetail({
  upload,
  onReviewed,
}: {
  upload: Upload;
  onReviewed: () => void;
}) {
  const { session } = useAuth();
  const [notes, setNotes] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const meta = upload.metadata;

  async function handleReview(action: 'approve' | 'reject') {
    if (action === 'reject' && !notes.trim()) {
      setError('Notes are required when rejecting');
      return;
    }
    setSubmitting(true);
    setError(null);

    try {
      const resp = await fetch(`${API_BASE}/api/admin/uploads/${upload.id}/review`, {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${session?.access_token}`,
        },
        body: JSON.stringify({ action, notes: notes || null }),
      });
      if (resp.ok) {
        onReviewed();
      } else {
        const err = await resp.json();
        setError(err.detail || 'Review failed');
      }
    } catch {
      setError('Network error');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="bg-[#222] border border-[#505050] rounded-lg p-4 mt-2 space-y-3">
      <div className="grid grid-cols-2 gap-2 text-sm">
        <div>
          <span className="text-gray-500">Uploader:</span>{' '}
          <span className="text-gray-300">{upload.uploader_name || upload.uploader_email}</span>
        </div>
        <div>
          <span className="text-gray-500">Type:</span>{' '}
          <span className="text-gray-300">{upload.upload_type}</span>
        </div>
        {upload.original_filename && (
          <div>
            <span className="text-gray-500">File:</span>{' '}
            <span className="text-gray-300">{upload.original_filename}</span>
            {upload.file_size_bytes && (
              <span className="text-gray-500 ml-1">
                ({(upload.file_size_bytes / 1024).toFixed(0)} KB)
              </span>
            )}
          </div>
        )}
      </div>

      {/* Type-specific metadata preview */}
      <div className="text-sm space-y-1">
        {Object.entries(meta).map(([key, val]) =>
          val != null ? (
            <div key={key}>
              <span className="text-gray-500">{key.replace(/_/g, ' ')}:</span>{' '}
              <span className="text-gray-300">
                {typeof val === 'string' ? val : JSON.stringify(val)}
              </span>
            </div>
          ) : null
        )}
      </div>

      <div>
        <label className="block text-sm text-gray-400 mb-1">Review Notes</label>
        <textarea
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          rows={2}
          placeholder="Optional for approve, required for reject"
          className="w-full bg-[#1a1a1a] border border-[#404040] rounded px-3 py-2 text-white text-sm placeholder:text-gray-600"
        />
      </div>

      {error && <p className="text-red-400 text-sm">{error}</p>}

      <div className="flex gap-2">
        <button
          onClick={() => handleReview('approve')}
          disabled={submitting}
          className="bg-[#00ff32] text-black font-semibold px-4 py-2 rounded text-sm hover:bg-[#00cc28] disabled:opacity-50"
        >
          Approve
        </button>
        <button
          onClick={() => handleReview('reject')}
          disabled={submitting}
          className="bg-red-600 text-white font-semibold px-4 py-2 rounded text-sm hover:bg-red-700 disabled:opacity-50"
        >
          Reject
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Create ReviewQueue component**

Create `ui-nextjs/components/admin/ReviewQueue.tsx`:

```tsx
'use client';

import { useCallback, useEffect, useState } from 'react';
import { useAuth } from '@/lib/auth-context';
import { API_BASE } from '@/lib/api';
import ReviewDetail from './ReviewDetail';

interface UploadRecord {
  id: string;
  upload_type: string;
  status: string;
  original_filename: string | null;
  file_size_bytes: number | null;
  metadata: Record<string, unknown>;
  uploader_email: string | null;
  uploader_name: string | null;
  created_at: string;
}

const TYPE_LABELS: Record<string, string> = {
  datasource: 'Data Source',
  document: 'Document',
  query: 'Example Query',
  feature_request: 'Feature Request',
};

export default function ReviewQueue() {
  const { session } = useAuth();
  const [uploads, setUploads] = useState<UploadRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [filterType, setFilterType] = useState<string>('');

  const fetchPending = useCallback(async () => {
    if (!session?.access_token) return;
    setLoading(true);
    try {
      const params = new URLSearchParams({ status: 'pending_review' });
      if (filterType) params.set('upload_type', filterType);
      const resp = await fetch(`${API_BASE}/api/admin/uploads?${params}`, {
        headers: { Authorization: `Bearer ${session.access_token}` },
      });
      if (resp.ok) {
        setUploads(await resp.json());
      }
    } finally {
      setLoading(false);
    }
  }, [session?.access_token, filterType]);

  useEffect(() => {
    fetchPending();
  }, [fetchPending]);

  function handleReviewed() {
    setExpandedId(null);
    fetchPending();
  }

  return (
    <div>
      <div className="flex items-center gap-3 mb-4">
        <h3 className="text-lg font-bold text-white">Review Queue</h3>
        <select
          value={filterType}
          onChange={(e) => setFilterType(e.target.value)}
          className="bg-[#1a1a1a] border border-[#404040] rounded px-2 py-1 text-sm text-gray-300"
        >
          <option value="">All types</option>
          <option value="datasource">Data Sources</option>
          <option value="document">Documents</option>
          <option value="query">Example Queries</option>
          <option value="feature_request">Feature Requests</option>
        </select>
        <span className="text-gray-500 text-sm">{uploads.length} pending</span>
      </div>

      {loading ? (
        <p className="text-gray-400">Loading...</p>
      ) : uploads.length === 0 ? (
        <p className="text-gray-500">No pending uploads to review.</p>
      ) : (
        <div className="space-y-2">
          {uploads.map((u) => (
            <div key={u.id}>
              <button
                onClick={() => setExpandedId(expandedId === u.id ? null : u.id)}
                className="w-full flex items-center justify-between bg-[#1a1a1a] border border-[#404040] rounded-lg px-4 py-3 hover:border-[#606060] text-left"
              >
                <div className="flex items-center gap-3">
                  <span className="text-xs bg-[#404040] text-gray-300 px-2 py-1 rounded">
                    {TYPE_LABELS[u.upload_type] || u.upload_type}
                  </span>
                  <span className="text-white text-sm">
                    {u.original_filename ||
                      (u.metadata as Record<string, string>)?.title ||
                      (u.metadata as Record<string, string>)?.source_name ||
                      (u.metadata as Record<string, string>)?.query_text?.slice(0, 60) ||
                      'Upload'}
                  </span>
                </div>
                <div className="flex items-center gap-3">
                  <span className="text-gray-500 text-xs">
                    {u.uploader_name || u.uploader_email}
                  </span>
                  <span className="text-gray-500 text-xs">
                    {new Date(u.created_at).toLocaleDateString()}
                  </span>
                  <span className="text-gray-500">{expandedId === u.id ? '▲' : '▼'}</span>
                </div>
              </button>
              {expandedId === u.id && (
                <ReviewDetail upload={u} onReviewed={handleReviewed} />
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Add Review Queue tab to admin page**

Modify `ui-nextjs/app/admin/page.tsx`:

Add import:

```tsx
import ReviewQueue from '@/components/admin/ReviewQueue';
```

Add a new section after the Staff Uploads section (visible only to admins):

```tsx
{/* Review Queue (admin only) */}
<div className="bg-[#1a1a1a] border border-[#404040] rounded-lg p-6">
  <ReviewQueue />
</div>
```

- [ ] **Step 4: Verify the frontend builds**

Run: `cd /Users/william-meroxa/Development/d4bl_ai_agent/.worktrees/staff-guide/ui-nextjs && npm run build 2>&1 | tail -20`

Expected: build succeeds

- [ ] **Step 5: Commit**

```bash
git add ui-nextjs/components/admin/ReviewQueue.tsx ui-nextjs/components/admin/ReviewDetail.tsx ui-nextjs/app/admin/page.tsx
git commit -m "feat: add review queue to admin page for upload approvals (#188)"
```

---

## Task 6: Staff Tutorial Page (`/guide`)

**Files:**
- Create: `ui-nextjs/components/guide/GuideSection.tsx`
- Create: `ui-nextjs/components/guide/FeatureRequestForm.tsx`
- Create: `ui-nextjs/app/guide/page.tsx`
- Modify: `ui-nextjs/components/NavBar.tsx`

- [ ] **Step 1: Create GuideSection accordion component**

Create `ui-nextjs/components/guide/GuideSection.tsx`:

```tsx
'use client';

import { ReactNode, useState } from 'react';

export default function GuideSection({
  title,
  defaultOpen = false,
  children,
  actionLabel,
  actionHref,
}: {
  title: string;
  defaultOpen?: boolean;
  children: ReactNode;
  actionLabel?: string;
  actionHref?: string;
}) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <div className="border border-[#404040] rounded-lg overflow-hidden">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between px-6 py-4 bg-[#1a1a1a] hover:bg-[#222] text-left"
      >
        <h2 className="text-lg font-semibold text-white">{title}</h2>
        <span className="text-gray-500 text-xl">{open ? '−' : '+'}</span>
      </button>
      {open && (
        <div className="px-6 py-4 bg-[#1a1a1a] border-t border-[#404040] space-y-4">
          <div className="text-gray-300 text-sm leading-relaxed space-y-3">{children}</div>
          {actionLabel && actionHref && (
            <a
              href={actionHref}
              className="inline-block mt-2 bg-[#00ff32] text-black font-semibold px-4 py-2 rounded text-sm hover:bg-[#00cc28]"
            >
              {actionLabel} →
            </a>
          )}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Create FeatureRequestForm component**

Create `ui-nextjs/components/guide/FeatureRequestForm.tsx`:

```tsx
'use client';

import { FormEvent, useState } from 'react';
import { useAuth } from '@/lib/auth-context';
import { API_BASE } from '@/lib/api';

export default function FeatureRequestForm() {
  const { session } = useAuth();
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setSubmitting(true);
    setMessage(null);

    const form = new FormData(e.currentTarget);
    const body = {
      title: form.get('title') as string,
      description: form.get('description') as string,
      who_benefits: form.get('who_benefits') as string,
      example: (form.get('example') as string) || null,
    };

    try {
      const resp = await fetch(`${API_BASE}/api/admin/uploads/feature-request`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${session?.access_token}`,
        },
        body: JSON.stringify(body),
      });
      if (resp.ok) {
        setMessage({ type: 'success', text: 'Feature request submitted! The team will review it.' });
        (e.target as HTMLFormElement).reset();
      } else {
        const err = await resp.json();
        setMessage({ type: 'error', text: err.detail || 'Submit failed' });
      }
    } catch {
      setMessage({ type: 'error', text: 'Network error' });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4 mt-4">
      <div>
        <label className="block text-sm text-gray-300 mb-1">What feature would you like? *</label>
        <input
          type="text"
          name="title"
          required
          placeholder="e.g., Add HMDA mortgage lending data"
          className="w-full bg-[#222] border border-[#404040] rounded px-3 py-2 text-white text-sm placeholder:text-gray-600"
        />
      </div>
      <div>
        <label className="block text-sm text-gray-300 mb-1">Describe the feature *</label>
        <textarea
          name="description"
          required
          rows={3}
          placeholder="What should it do? What problem does it solve?"
          className="w-full bg-[#222] border border-[#404040] rounded px-3 py-2 text-white text-sm placeholder:text-gray-600"
        />
      </div>
      <div>
        <label className="block text-sm text-gray-300 mb-1">Who benefits from this? *</label>
        <input
          type="text"
          name="who_benefits"
          required
          placeholder="e.g., Researchers studying housing discrimination"
          className="w-full bg-[#222] border border-[#404040] rounded px-3 py-2 text-white text-sm placeholder:text-gray-600"
        />
      </div>
      <div>
        <label className="block text-sm text-gray-300 mb-1">Example of how it would work (optional)</label>
        <textarea
          name="example"
          rows={2}
          placeholder="Describe a scenario where someone would use this feature"
          className="w-full bg-[#222] border border-[#404040] rounded px-3 py-2 text-white text-sm placeholder:text-gray-600"
        />
      </div>
      {message && (
        <p className={`text-sm ${message.type === 'success' ? 'text-[#00ff32]' : 'text-red-400'}`}>
          {message.text}
        </p>
      )}
      <button
        type="submit"
        disabled={submitting}
        className="bg-[#00ff32] text-black font-semibold px-6 py-2 rounded hover:bg-[#00cc28] disabled:opacity-50"
      >
        {submitting ? 'Submitting...' : 'Submit Feature Request'}
      </button>
    </form>
  );
}
```

- [ ] **Step 3: Create the /guide page**

Create `ui-nextjs/app/guide/page.tsx`:

```tsx
'use client';

import { useRouter } from 'next/navigation';
import { useEffect } from 'react';
import { useAuth } from '@/lib/auth-context';
import GuideSection from '@/components/guide/GuideSection';
import FeatureRequestForm from '@/components/guide/FeatureRequestForm';

export default function GuidePage() {
  const { user, isLoading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!isLoading && !user) {
      router.push('/login');
    }
  }, [user, isLoading, router]);

  if (isLoading) {
    return (
      <div className="min-h-screen bg-[#292929] flex items-center justify-center">
        <p className="text-gray-400">Loading...</p>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#292929] py-8 px-4">
      <div className="max-w-3xl mx-auto">
        <h1 className="text-3xl font-bold text-white mb-2">Staff Contributor Guide</h1>
        <p className="text-gray-400 mb-8">
          Learn how to contribute data sources, documents, example queries, and feature ideas to the
          D4BL platform.
        </p>

        <div className="space-y-4">
          <GuideSection
            title="Adding a Data Source"
            defaultOpen={true}
            actionLabel="Upload a data source"
            actionHref="/admin"
          >
            <p>
              <strong className="text-white">What makes a good data source?</strong> We look for
              datasets that include geographic identifiers (state, county, or census tract FIPS
              codes), racial or demographic breakdowns, and recent data (ideally within the last 3
              years).
            </p>
            <p>
              <strong className="text-white">Supported formats:</strong> CSV and Excel (.xlsx)
              files, up to 50MB. Your file should have column headers in the first row.
            </p>
            <p>
              <strong className="text-white">How to upload:</strong> Go to the Admin page, select
              the &quot;Data Sources&quot; tab under Staff Uploads, fill in the source details, and
              attach your file. You&apos;ll need to specify the geographic level (state, county, or
              tract) and data year.
            </p>
            <p>
              <strong className="text-white">What happens next:</strong> Your upload enters a review
              queue. An admin will check the data for quality and relevance, then approve or provide
              feedback. Once approved, the data becomes available in the Explore page.
            </p>
            <p className="text-gray-400 text-xs">
              Example: Upload a CSV from the County Health Rankings with columns like county_fips,
              state, measure_name, value, and race. Set geographic level to &quot;County&quot; and data year
              to 2024.
            </p>
          </GuideSection>

          <GuideSection
            title="Sharing a Document"
            actionLabel="Upload a document"
            actionHref="/admin"
          >
            <p>
              <strong className="text-white">What types of documents are useful?</strong> Policy
              briefs, research reports, news articles, and academic papers — especially those focused
              on racial equity, data justice, and systemic disparities.
            </p>
            <p>
              <strong className="text-white">File vs. URL:</strong> Upload PDFs or Word documents
              directly (up to 25MB), or submit a URL for web articles. URLs will be crawled to
              extract content automatically.
            </p>
            <p>
              <strong className="text-white">How documents are used:</strong> Approved documents
              feed into the research agents&apos; knowledge base and the vector search system. When
              someone asks a research question, the AI can draw on these documents to provide better,
              more grounded answers.
            </p>
            <p className="text-gray-400 text-xs">
              Example: Upload a Vera Institute report on incarceration trends as a PDF, tagged with
              &quot;incarceration&quot; and &quot;racial-disparity&quot;. Or paste a URL to a recent ProPublica
              article on environmental justice.
            </p>
          </GuideSection>

          <GuideSection
            title="Contributing Example Queries"
            actionLabel="Submit an example query"
            actionHref="/admin"
          >
            <p>
              <strong className="text-white">What makes a good example query?</strong> Specific,
              answerable questions focused on racial equity and data justice. They should reference a
              geographic area or policy domain and be questions that someone would genuinely ask.
            </p>
            <p>
              <strong className="text-white">Why examples matter:</strong> Example queries help
              train the system to better understand equity-focused questions. They also serve as
              templates that other users can build from.
            </p>
            <p>
              <strong className="text-white">What to include:</strong> Write the query as you would
              naturally ask it. Add a description of why it&apos;s a good example. If you have a
              known good answer, include that too — it helps with evaluation.
            </p>
            <p className="text-gray-400 text-xs">
              Example: &quot;What are the racial disparities in mortgage lending denial rates in
              Atlanta metro counties?&quot; — Good because it specifies a metric, geography, and
              equity lens.
            </p>
          </GuideSection>

          <GuideSection title="Requesting a Feature">
            <p>
              <strong className="text-white">Have an idea?</strong> Use the form below to submit a
              feature request. The team reviews requests regularly and will follow up on feasible
              ideas.
            </p>
            <p>
              <strong className="text-white">Tips for a good request:</strong>
            </p>
            <ul className="list-disc list-inside space-y-1 text-gray-300">
              <li>Be specific about what problem it solves</li>
              <li>Explain who would benefit</li>
              <li>Include an example scenario if possible</li>
              <li>Focus on the &quot;what&quot; and &quot;why&quot;, not the &quot;how&quot;</li>
            </ul>
            <FeatureRequestForm />
          </GuideSection>

          <GuideSection title="Developing a Feature (Advanced)">
            <p className="text-yellow-500 text-xs font-semibold uppercase tracking-wide mb-2">
              For technical contributors
            </p>
            <p>
              <strong className="text-white">Architecture overview:</strong> D4BL uses a FastAPI
              backend (Python) serving a Next.js frontend (TypeScript/React). Research agents are
              powered by CrewAI with a local Ollama LLM. Data lives in PostgreSQL and Supabase
              (vector search).
            </p>
            <p>
              <strong className="text-white">Getting started:</strong> Clone the repo, set up a
              Python virtual environment, install dependencies, and start the backend and frontend
              dev servers. See the{' '}
              <a
                href="https://github.com/William-Hill/d4bl_ai_agent/blob/main/docs/DEVELOPMENT.md"
                className="text-[#00ff32] underline"
                target="_blank"
                rel="noopener noreferrer"
              >
                Development Guide
              </a>{' '}
              for full setup instructions.
            </p>
            <p>
              <strong className="text-white">Workflow:</strong> Create a feature branch, make your
              changes, test locally (run the backend + frontend, verify in browser), then open a pull
              request. Use conventional commit messages (e.g., <code className="text-[#00ff32]">feat:</code>,{' '}
              <code className="text-[#00ff32]">fix:</code>).
            </p>
            <p>
              <strong className="text-white">Key directories:</strong>
            </p>
            <ul className="list-disc list-inside space-y-1 text-gray-300 font-mono text-xs">
              <li>src/d4bl/app/ — API endpoints</li>
              <li>src/d4bl/agents/ — AI agent definitions</li>
              <li>src/d4bl/infra/ — database models</li>
              <li>ui-nextjs/app/ — frontend pages</li>
              <li>ui-nextjs/components/ — React components</li>
              <li>scripts/ingestion/ — data ingestion scripts</li>
            </ul>
          </GuideSection>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Add Guide link to NavBar**

Modify `ui-nextjs/components/NavBar.tsx`. Add a Guide link visible to all authenticated users, between the existing nav links and the admin-only links:

```tsx
{user && (
  <Link href="/guide" className="text-gray-300 hover:text-white transition-colors">
    Guide
  </Link>
)}
```

- [ ] **Step 5: Verify the frontend builds**

Run: `cd /Users/william-meroxa/Development/d4bl_ai_agent/.worktrees/staff-guide/ui-nextjs && npm run build 2>&1 | tail -20`

Expected: build succeeds

- [ ] **Step 6: Commit**

```bash
git add ui-nextjs/components/guide/GuideSection.tsx ui-nextjs/components/guide/FeatureRequestForm.tsx ui-nextjs/app/guide/page.tsx ui-nextjs/components/NavBar.tsx
git commit -m "feat: add /guide staff tutorial page with feature request form (#188)"
```

---

## Task 7: Approval Processing (Deferred)

**Note:** The spec describes automatic processing when an admin approves an upload (CSV parsing into `uploaded_datasets`, document vectorization, query insertion). The review endpoint in Task 3 sets the status to `approved` but does **not** trigger background processing.

This is intentional for v1: the approval marks the upload as reviewed, and a developer can later write processing scripts to handle each type. The `status` field supports the full lifecycle (`pending_review` → `approved` → `processing` → `live`) so when processing is wired up, it slots in cleanly.

**Future work (not in this plan):**
- Background task on approval: parse CSV → `uploaded_datasets` rows
- Background task on approval: extract PDF text → vectorize → Supabase
- Background task on approval: insert `example_queries` row → mark `live`

---

## Task 8: Lint + Full Test Suite

**Files:** none (verification only)

- [ ] **Step 1: Run ESLint on new frontend files**

Run: `cd /Users/william-meroxa/Development/d4bl_ai_agent/.worktrees/staff-guide/ui-nextjs && npx next lint 2>&1 | tail -20`

Expected: no errors (warnings acceptable)

Fix any lint errors before proceeding.

- [ ] **Step 2: Run full backend tests**

Run: `cd /Users/william-meroxa/Development/d4bl_ai_agent/.worktrees/staff-guide && source .venv/bin/activate && python -m pytest tests/ -x -q 2>&1 | tail -20`

Expected: all tests pass

- [ ] **Step 3: Run full frontend build**

Run: `cd /Users/william-meroxa/Development/d4bl_ai_agent/.worktrees/staff-guide/ui-nextjs && npm run build 2>&1 | tail -10`

Expected: build succeeds

- [ ] **Step 4: Fix any issues and commit**

If fixes were needed:

```bash
git add -u
git commit -m "fix: address lint and test issues for staff guide (#188)"
```
