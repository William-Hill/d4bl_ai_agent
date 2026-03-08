"""
Database models and connection for storing research queries and results
"""
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base

from d4bl.settings import get_settings

Base = declarative_base()


def _utc_now() -> datetime:
    """Return the current UTC time as a timezone-aware datetime."""
    return datetime.now(timezone.utc)


class ResearchJob(Base):
    """Model for storing research job queries and results"""
    __tablename__ = "research_jobs"

    job_id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    trace_id = Column(String(64), nullable=True, index=True)
    query = Column(Text, nullable=False, index=True)
    summary_format = Column(String(20), nullable=False, default="detailed")
    status = Column(String(20), nullable=False, default="pending", index=True)
    progress = Column(Text, nullable=True)
    result = Column(JSON, nullable=True)  # Store the full result dict as JSON
    research_data = Column(JSON, nullable=True)  # Store research data for use as reference in evaluations
    error = Column(Text, nullable=True)
    logs = Column(JSON, nullable=True)  # Store logs array as JSON
    created_at = Column(DateTime, nullable=False, default=_utc_now, index=True)
    updated_at = Column(DateTime, nullable=False, default=_utc_now, onupdate=_utc_now)
    completed_at = Column(DateTime, nullable=True)
    # No ForeignKey -- auth.users is managed by Supabase, not SQLAlchemy
    user_id = Column(PG_UUID(as_uuid=True), nullable=True, index=True)

    def to_dict(self):
        """Convert model to dictionary"""
        return {
            "job_id": str(self.job_id),
            "trace_id": self.trace_id,
            "query": self.query,
            "summary_format": self.summary_format,
            "status": self.status,
            "progress": self.progress,
            "result": self.result,
            "research_data": self.research_data,
            "error": self.error,
            "logs": self.logs,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "user_id": str(self.user_id) if self.user_id else None,
        }


class EvaluationResult(Base):
    """Store evaluator outputs for spans"""
    __tablename__ = "evaluation_results"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    span_id = Column(String(64), nullable=False, index=True)
    trace_id = Column(String(64), nullable=True, index=True)
    job_id = Column(PG_UUID(as_uuid=True), nullable=True, index=True)  # Link to ResearchJob
    eval_name = Column(String(100), nullable=False, index=True)
    label = Column(String(100), nullable=True)
    score = Column(Float, nullable=True)
    explanation = Column(Text, nullable=True)
    input_text = Column(Text, nullable=True)
    output_text = Column(Text, nullable=True)
    context_text = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=_utc_now, index=True)

    def to_dict(self):
        return {
            "id": str(self.id),
            "span_id": self.span_id,
            "trace_id": self.trace_id,
            "job_id": str(self.job_id) if self.job_id else None,
            "eval_name": self.eval_name,
            "label": self.label,
            "score": self.score,
            "explanation": self.explanation,
            "input_text": self.input_text,
            "output_text": self.output_text,
            "context_text": self.context_text,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class CensusIndicator(Base):
    """Race-disaggregated Census ACS indicators by geography."""
    __tablename__ = "census_indicators"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    fips_code = Column(String(5), nullable=False, index=True)
    geography_type = Column(String(10), nullable=False)   # state | county | tract
    geography_name = Column(Text, nullable=False)
    state_fips = Column(String(2), nullable=False, index=True)
    year = Column(Integer, nullable=False)
    race = Column(String(50), nullable=False)
    metric = Column(String(100), nullable=False)
    value = Column(Float, nullable=False)
    margin_of_error = Column(Float, nullable=True)
    created_at = Column(DateTime, nullable=False, default=_utc_now)

    __table_args__ = (
        # Composite index to support common query filters
        Index(
            "ix_census_indicator_state_geo_metric_race_year",
            "state_fips",
            "geography_type",
            "metric",
            "race",
            "year",
        ),
        # Ensure idempotent upserts on core identity
        UniqueConstraint(
            "fips_code",
            "year",
            "race",
            "metric",
            name="uq_census_indicator_key",
        ),
        {"comment": "Census ACS 5-year estimates, race-disaggregated"},
    )


class PolicyBill(Base):
    """State legislation tracked via OpenStates."""
    __tablename__ = "policy_bills"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    state = Column(String(2), nullable=False, index=True)
    state_name = Column(String(50), nullable=False)
    bill_id = Column(String(50), nullable=False)
    bill_number = Column(String(20), nullable=False)
    title = Column(Text, nullable=False)
    summary = Column(Text, nullable=True)
    status = Column(String(20), nullable=False, index=True)
    topic_tags = Column(JSON, nullable=True)
    session = Column(String(20), nullable=False, index=True)
    introduced_date = Column(Date, nullable=True)
    last_action_date = Column(Date, nullable=True)
    url = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=_utc_now)
    updated_at = Column(DateTime, nullable=False, default=_utc_now, onupdate=_utc_now)

    __table_args__ = (
        # Support common filters for policy tracker views
        Index(
            "ix_policy_bill_state_status_session",
            "state",
            "status",
            "session",
        ),
        # Idempotent upserts per state/session/bill id
        UniqueConstraint(
            "state",
            "bill_id",
            "session",
            name="uq_policy_bill_key",
        ),
    )


class DataSource(Base):
    """Admin-configured data source for ingestion."""

    __tablename__ = "data_sources"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    name = Column(String(255), nullable=False)
    source_type = Column(
        String(50),
        nullable=False,
        comment="api|file_upload|web_scrape|rss_feed|database|mcp",
    )
    config = Column(JSON, nullable=False, default=dict)
    default_schedule = Column(String(100), nullable=True)
    enabled = Column(Boolean, nullable=False, default=True)
    created_by = Column(PG_UUID(as_uuid=True), nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        Index("ix_data_sources_source_type", "source_type"),
        Index("ix_data_sources_enabled", "enabled"),
    )

    def to_dict(self):
        return {
            "id": str(self.id),
            "name": self.name,
            "source_type": self.source_type,
            "config": self.config,
            "default_schedule": self.default_schedule,
            "enabled": self.enabled,
            "created_by": str(self.created_by) if self.created_by else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class IngestionRun(Base):
    """Audit trail for every ingestion execution."""

    __tablename__ = "ingestion_runs"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    data_source_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("data_sources.id", ondelete="CASCADE"),
        nullable=False,
    )
    dagster_run_id = Column(String(255), nullable=True)
    status = Column(
        String(50),
        nullable=False,
        default="pending",
        comment="pending|running|completed|failed",
    )
    triggered_by = Column(PG_UUID(as_uuid=True), nullable=True)
    trigger_type = Column(
        String(50),
        nullable=False,
        default="manual",
        comment="manual|scheduled|sensor",
    )
    records_ingested = Column(Integer, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    error_detail = Column(Text, nullable=True)

    __table_args__ = (
        Index("ix_ingestion_runs_data_source_id", "data_source_id"),
        Index("ix_ingestion_runs_status", "status"),
        Index("ix_ingestion_runs_started_at", "started_at"),
    )

    def to_dict(self):
        return {
            "id": str(self.id),
            "data_source_id": str(self.data_source_id),
            "dagster_run_id": self.dagster_run_id,
            "status": self.status,
            "triggered_by": str(self.triggered_by) if self.triggered_by else None,
            "trigger_type": self.trigger_type,
            "records_ingested": self.records_ingested,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": (
                self.completed_at.isoformat() if self.completed_at else None
            ),
            "error_detail": self.error_detail,
        }


class DataLineage(Base):
    """Row/asset-level provenance aligned with D4BL methodology."""

    __tablename__ = "data_lineage"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    ingestion_run_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("ingestion_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    target_table = Column(String(255), nullable=False)
    record_id = Column(PG_UUID(as_uuid=True), nullable=False)
    source_url = Column(Text, nullable=True)
    source_hash = Column(String(128), nullable=True)
    transformation = Column(JSON, nullable=True)
    quality_score = Column(Float, nullable=True, comment="1-5 scale")
    coverage_metadata = Column(JSON, nullable=True)
    bias_flags = Column(JSON, nullable=True)
    retrieved_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    __table_args__ = (
        Index("ix_data_lineage_ingestion_run_id", "ingestion_run_id"),
        Index("ix_data_lineage_target_table", "target_table"),
        Index("ix_data_lineage_record_id", "record_id"),
    )

    def to_dict(self):
        return {
            "id": str(self.id),
            "ingestion_run_id": str(self.ingestion_run_id),
            "target_table": self.target_table,
            "record_id": str(self.record_id),
            "source_url": self.source_url,
            "source_hash": self.source_hash,
            "transformation": self.transformation,
            "quality_score": self.quality_score,
            "coverage_metadata": self.coverage_metadata,
            "bias_flags": self.bias_flags,
            "retrieved_at": (
                self.retrieved_at.isoformat() if self.retrieved_at else None
            ),
        }


class KeywordMonitor(Base):
    """Topic/keyword-based ingestion configuration."""

    __tablename__ = "keyword_monitors"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    name = Column(String(255), nullable=False)
    keywords = Column(JSON, nullable=False, default=list)
    source_ids = Column(JSON, nullable=False, default=list)
    schedule = Column(String(100), nullable=True)
    enabled = Column(Boolean, nullable=False, default=True)
    created_by = Column(PG_UUID(as_uuid=True), nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    __table_args__ = (
        Index("ix_keyword_monitors_enabled", "enabled"),
    )

    def to_dict(self):
        return {
            "id": str(self.id),
            "name": self.name,
            "keywords": self.keywords,
            "source_ids": self.source_ids,
            "schedule": self.schedule,
            "enabled": self.enabled,
            "created_by": str(self.created_by) if self.created_by else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# Database connection setup
def get_database_url() -> str:
    """Get database URL from settings."""
    settings = get_settings()
    db_user = settings.postgres_user
    db_password = settings.postgres_password
    db_host = settings.postgres_host
    db_port = settings.postgres_port
    db_name = settings.postgres_db

    if db_host in ("localhost", "127.0.0.1") and settings.is_docker:
        original_host = db_host
        db_host = "postgres"
        print(
            f"⚠ Warning: Detected Docker environment, "
            f"using 'postgres' as hostname instead of '{original_host}'"
        )
    elif db_host in ("localhost", "127.0.0.1"):
        print(
            "⚠ Warning: Using 'localhost' as database host. "
            "In Docker, this should be 'postgres' or 'host.docker.internal'"
        )

    if not db_name or db_name == db_user:
        db_name = "postgres"
        print(f"⚠ Warning: Using default database name: {db_name}")

    database_url = f"postgresql+asyncpg://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
    print(f"📊 Database URL: postgresql+asyncpg://{db_user}:***@{db_host}:{db_port}/{db_name}")

    return database_url


# Create async engine
engine = None
async_session_maker = None


def init_db():
    """Initialize database connection"""
    global engine, async_session_maker

    settings = get_settings()
    database_url = get_database_url()
    engine = create_async_engine(
        database_url,
        echo=settings.db_echo,
        future=True,
        pool_pre_ping=True,  # Verify connections before using them
        pool_size=5,  # Limit connection pool size
        max_overflow=10,  # Max overflow connections
        pool_recycle=3600,  # Recycle connections after 1 hour
    )
    async_session_maker = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )


async def get_db() -> AsyncSession:
    """Get database session"""
    if async_session_maker is None:
        init_db()
    async with async_session_maker() as session:
        try:
            yield session
        finally:
            await session.close()


async def create_tables():
    """Create all database tables"""
    if engine is None:
        init_db()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db():
    """Close database connection"""
    if engine:
        await engine.dispose()

