"""
Database models and connection for storing research queries and results
"""
import os
from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import JSON, Text, Column, String, DateTime, Float
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

Base = declarative_base()


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
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

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
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)

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


# Database connection setup
def get_database_url() -> str:
    """Get database URL from environment variables"""
    db_user = os.getenv("POSTGRES_USER", "d4bl_user")
    db_password = os.getenv("POSTGRES_PASSWORD", "d4bl_password")
    db_host = os.getenv("POSTGRES_HOST", "localhost")
    db_port = os.getenv("POSTGRES_PORT", "5432")
    db_name = os.getenv("POSTGRES_DB", "postgres")
    
    # CRITICAL: In Docker, we MUST use 'postgres' as the hostname (Docker service name)
    # OR use 'host.docker.internal' to reach services on the host machine (like Supabase)
    # Only override if host is localhost/127.0.0.1 AND we're in Docker AND it's not already set to host.docker.internal
    if (db_host == "localhost" or db_host == "127.0.0.1") and db_host != "host.docker.internal":
        # Check if we're in Docker (common indicators)
        if os.path.exists("/.dockerenv") or os.getenv("DOCKER_CONTAINER"):
            original_host = db_host
            db_host = "postgres"
            print(f"⚠ Warning: Detected Docker environment, using 'postgres' as hostname instead of '{original_host}'")
        else:
            print("⚠ Warning: Using 'localhost' as database host. In Docker, this should be 'postgres' or 'host.docker.internal'")
    
    # Ensure we're using the correct database name (not the username)
    if not db_name or db_name == db_user:
        db_name = "postgres"
        print(f"⚠ Warning: Using default database name: {db_name}")
    
    # Use asyncpg driver for async operations
    database_url = f"postgresql+asyncpg://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
    print(f"📊 Database URL: postgresql+asyncpg://{db_user}:***@{db_host}:{db_port}/{db_name}")
    
    # Final safety check: warn if using localhost in what looks like Docker
    if (db_host == "localhost" or db_host == "127.0.0.1") and os.path.exists("/.dockerenv"):
        print(f"⚠⚠⚠ CRITICAL WARNING: Using localhost in Docker container!")
        print(f"   This will try to connect to host Postgres, not Docker Postgres!")
        print(f"   Set POSTGRES_HOST=postgres in docker-compose.yml")
    
    return database_url


# Create async engine
engine = None
async_session_maker = None


def init_db():
    """Initialize database connection"""
    global engine, async_session_maker
    
    database_url = get_database_url()
    engine = create_async_engine(
        database_url,
        echo=os.getenv("DB_ECHO", "false").lower() == "true",
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

