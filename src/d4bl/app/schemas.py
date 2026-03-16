"""
Pydantic schemas shared by the FastAPI application.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, field_validator


class ResearchRequest(BaseModel):
    query: str
    summary_format: Literal["brief", "detailed", "comprehensive"] = "detailed"
    # List of agent names to run (e.g., ["researcher", "writer"])
    selected_agents: list[str] | None = None
    # LiteLLM model string, e.g. "gemini/gemini-2.0-flash"
    model: str | None = None

    @field_validator("query")
    @classmethod
    def query_not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Query cannot be empty")
        return v


class ResearchResponse(BaseModel):
    job_id: str
    status: str
    message: str


class JobStatus(BaseModel):
    job_id: str
    trace_id: str | None = None
    status: str  # pending, running, completed, error
    progress: str | None = None
    result: dict | None = None
    error: str | None = None
    query: str | None = None
    summary_format: str | None = None
    logs: list[str] | None = None
    research_data: dict | None = None
    created_at: str | None = None
    updated_at: str | None = None
    completed_at: str | None = None


class JobHistoryResponse(BaseModel):
    jobs: list[JobStatus]
    total: int
    page: int
    page_size: int


class EvaluationResultItem(BaseModel):
    id: str
    span_id: str
    trace_id: str | None = None
    job_id: str | None = None
    eval_name: str
    label: str | None = None
    score: float | None = None
    explanation: str | None = None
    input_text: str | None = None
    output_text: str | None = None
    context_text: str | None = None
    created_at: str | None = None


# --- NL Query models ---


class QueryRequest(BaseModel):
    question: str
    job_id: str | None = None
    limit: int = 10

    @field_validator("question")
    @classmethod
    def question_not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Question cannot be empty")
        return v


class QuerySourceItem(BaseModel):
    url: str
    title: str
    snippet: str
    source_type: str
    relevance_score: float
    # Provenance metadata (populated for ingested data results)
    data_source_name: str | None = None
    quality_score: float | None = None
    last_updated: str | None = None
    coverage_notes: str | None = None


class QueryResponse(BaseModel):
    answer: str
    sources: list[QuerySourceItem]
    query: str


# --- Explore Data models ---


class ExploreRow(BaseModel):
    """A single row in a standardized explore API response."""

    state_fips: str
    state_name: str
    value: float
    metric: str
    year: int
    race: str | None = None


class ExploreResponse(BaseModel):
    """Standardized response shape for all explore endpoints."""

    rows: list[ExploreRow]
    national_average: float | None
    available_metrics: list[str]
    available_years: list[int]
    available_races: list[str]


class IndicatorItem(BaseModel):
    """Single Census ACS indicator observation for a geography/race/year."""

    fips_code: str
    geography_name: str
    state_fips: str
    geography_type: str
    year: int
    race: str
    metric: str
    value: float
    margin_of_error: float | None = None


class PolicyBillItem(BaseModel):
    """Legislative bill summary from OpenStates with status and topic tags."""

    state: str
    state_name: str
    bill_number: str
    title: str
    summary: str | None = None
    status: str
    topic_tags: list[str] | None = None
    introduced_date: str | None = None
    last_action_date: str | None = None
    url: str | None = None


class StateSummaryItem(BaseModel):
    """Per-state metadata: available metrics, bill count, and latest year."""

    state_fips: str
    state_name: str
    available_metrics: list[str]
    bill_count: int
    latest_year: int | None = None


# --- Admin models ---


class InviteRequest(BaseModel):
    email: str

    @field_validator("email")
    @classmethod
    def email_not_blank(cls, v: str) -> str:
        if not v or not v.strip() or "@" not in v:
            raise ValueError("Valid email required")
        return v.strip()


class UserProfile(BaseModel):
    id: str
    email: str
    role: str
    display_name: str | None = None
    created_at: str | None = None


class UpdateRoleRequest(BaseModel):
    role: Literal["user", "admin"]


# --- Data Ingestion models ---


class DataSourceCreate(BaseModel):
    name: str
    source_type: Literal["api", "file_upload", "web_scrape", "rss_feed", "database", "mcp"]
    config: dict = {}
    default_schedule: str | None = None
    enabled: bool = True

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("name must not be blank")
        return v.strip()


class DataSourceUpdate(BaseModel):
    name: str | None = None
    config: dict | None = None
    default_schedule: str | None = None
    enabled: bool | None = None

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not v.strip():
            raise ValueError("name must not be blank")
        return v.strip()


class DataSourceResponse(BaseModel):
    id: str
    name: str
    source_type: str
    config: dict
    default_schedule: str | None
    enabled: bool
    created_by: str | None
    created_at: str | None
    updated_at: str | None
    last_run_status: str | None = None
    last_run_at: str | None = None


class IngestionRunResponse(BaseModel):
    id: str
    data_source_id: str
    dagster_run_id: str | None
    status: str
    triggered_by: str | None
    trigger_type: str
    records_ingested: int | None
    started_at: str | None
    completed_at: str | None
    error_detail: str | None


class DataOverviewResponse(BaseModel):
    """High-level statistics for the data ingestion dashboard."""

    total_sources: int
    enabled_sources: int
    recent_failures: int


# --- Ingestion trigger models ---


class TriggerResponse(BaseModel):
    """Returned when an ingestion run is triggered for a data source."""

    ingestion_run_id: str
    status: str  # "triggered"


class RunStatusResponse(BaseModel):
    """Status of the latest ingestion run for a source."""

    ingestion_run_id: str
    status: str
    started_at: str | None = None
    completed_at: str | None = None
    records_ingested: int | None = None
    error_detail: str | None = None


# --- Keyword Monitor models ---


# --- Lineage models ---


class LineageRecordResponse(BaseModel):
    """Single data lineage record with full provenance."""

    id: str
    ingestion_run_id: str
    target_table: str
    record_id: str
    source_url: str | None = None
    source_hash: str | None = None
    transformation: dict | None = None
    quality_score: float | None = None
    coverage_metadata: dict | None = None
    bias_flags: Any = None
    retrieved_at: str | None = None
    # Joined from parent tables
    data_source_name: str | None = None
    data_source_type: str | None = None


class LineageGraphNode(BaseModel):
    """A node in the asset dependency graph."""

    asset_key: str
    source_name: str | None = None
    source_type: str | None = None
    last_run_status: str | None = None
    last_run_at: str | None = None
    record_count: int = 0


class LineageGraphResponse(BaseModel):
    """Asset dependency graph showing data flow."""

    nodes: list[LineageGraphNode]


# --- Test Connection models ---


class ConnectionTestResponse(BaseModel):
    """Result of testing a source connection."""

    success: bool
    message: str
    details: dict | None = None


class KeywordMonitorCreate(BaseModel):
    name: str
    keywords: list[str]
    source_ids: list[str]
    schedule: str | None = None
    enabled: bool = True

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("name must not be blank")
        return v.strip()


class KeywordMonitorUpdate(BaseModel):
    name: str | None = None
    keywords: list[str] | None = None
    source_ids: list[str] | None = None
    schedule: str | None = None
    enabled: bool | None = None

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not v.strip():
            raise ValueError("name must not be blank")
        return v.strip()


class KeywordMonitorResponse(BaseModel):
    id: str
    name: str
    keywords: list[str]
    source_ids: list[str]
    schedule: str | None
    enabled: bool
    created_by: str | None
    created_at: str | None


# --- State Summary / Insights models ---


class RacialGapGroup(BaseModel):
    race: str
    value: float


class RacialGap(BaseModel):
    groups: list[RacialGapGroup]
    max_ratio: float
    max_ratio_label: str


class StateSummaryInsight(BaseModel):
    state_fips: str
    state_name: str
    metric: str
    value: float
    national_average: float
    national_rank: int
    national_rank_total: int
    percentile: float
    racial_gap: RacialGap | None
    year: int
    source: str

