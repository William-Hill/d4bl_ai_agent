"""Staff upload API routes.

Endpoints for uploading data sources, documents, example queries,
and feature requests. Includes admin review workflow.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import PurePosixPath
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import ValidationError
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


def _safe_filename(raw: str | None) -> str:
    """Strip directory components from a client-supplied filename."""
    return PurePosixPath(raw or "file").name


def _file_ext(filename: str | None) -> str:
    """Extract lowercase extension (e.g. '.csv') or '' if none."""
    name = _safe_filename(filename)
    parts = name.rsplit(".", 1)
    return ("." + parts[-1].lower()) if len(parts) == 2 else ""


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
    ext = _file_ext(file.filename)
    if ext not in ALLOWED_DATASOURCE_EXT:
        raise HTTPException(400, f"File type {ext!r} not allowed. Use: {ALLOWED_DATASOURCE_EXT}")

    try:
        DataSourceUploadRequest(
            source_name=source_name,
            description=description,
            geographic_level=geographic_level,
            data_year=data_year,
        )
    except ValidationError as exc:
        raise HTTPException(422, detail=exc.errors()) from exc

    # File bytes are read for validation only; Supabase Storage upload is deferred.
    content = await file.read()
    if len(content) > MAX_DATASOURCE_SIZE:
        raise HTTPException(400, f"File too large. Max {MAX_DATASOURCE_SIZE // (1024*1024)}MB")
    if len(content) == 0:
        raise HTTPException(400, "File is empty")

    upload_id = uuid4()
    safe_name = _safe_filename(file.filename)

    tags = [t.strip() for t in category_tags.split(",") if t.strip()] if category_tags else None

    upload = Upload(
        id=upload_id,
        user_id=user.id,
        upload_type="datasource",
        status="pending_review",
        file_path=None,
        original_filename=safe_name,
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

    tags = [t.strip() for t in topic_tags.split(",") if t.strip()] if topic_tags else None

    try:
        validated = DocumentUploadRequest(
            title=title,
            document_type=document_type,
            topic_tags=tags,
            url=url,
        )
    except ValidationError as exc:
        raise HTTPException(422, detail=exc.errors()) from exc

    upload_id = uuid4()
    file_size = None
    filename = None

    if file:
        ext = _file_ext(file.filename)
        if ext not in ALLOWED_DOCUMENT_EXT:
            raise HTTPException(400, f"File type {ext!r} not allowed. Use: {ALLOWED_DOCUMENT_EXT}")
        # File bytes are read for validation only; Supabase Storage upload is deferred.
        content = await file.read()
        if len(content) > MAX_DOCUMENT_SIZE:
            raise HTTPException(400, f"File too large. Max {MAX_DOCUMENT_SIZE // (1024*1024)}MB")
        if len(content) == 0:
            raise HTTPException(400, "File is empty")
        file_size = len(content)
        filename = _safe_filename(file.filename)

    upload = Upload(
        id=upload_id,
        user_id=user.id,
        upload_type="document",
        status="pending_review",
        file_path=None,
        original_filename=filename,
        file_size_bytes=file_size,
        metadata_={
            "title": validated.title,
            "document_type": validated.document_type,
            "topic_tags": validated.topic_tags,
            "url": validated.url,
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
        status="pending_review",
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
        status="pending_review",
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


VALID_UPLOAD_TYPES = {"datasource", "document", "query", "feature_request"}
VALID_UPLOAD_STATUSES = {"pending_review", "approved", "rejected", "processing", "live"}


@router.get("/api/admin/uploads")
async def list_uploads(
    upload_type: str | None = None,
    status: str | None = None,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List uploads. Non-admins see only their own uploads."""
    if upload_type and upload_type not in VALID_UPLOAD_TYPES:
        raise HTTPException(400, f"Invalid upload_type. Use: {sorted(VALID_UPLOAD_TYPES)}")
    if status and status not in VALID_UPLOAD_STATUSES:
        raise HTTPException(400, f"Invalid status. Use: {sorted(VALID_UPLOAD_STATUSES)}")

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
    upload_id: UUID,
    body: UploadReviewRequest,
    user: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Approve or reject an upload (admin only)."""
    result = await db.execute(
        text("SELECT id, status FROM uploads WHERE id = CAST(:uid AS uuid)"),
        {"uid": str(upload_id)},
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
            "uid": str(upload_id),
        },
    )
    await db.commit()

    return {"id": str(upload_id), "status": new_status, "reviewed_at": now.isoformat()}
