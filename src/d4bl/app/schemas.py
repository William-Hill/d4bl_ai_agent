"""
Pydantic schemas shared by the FastAPI application.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class ResearchRequest(BaseModel):
    query: str
    summary_format: Literal["brief", "detailed", "comprehensive"] = "detailed"
    # List of agent names to run (e.g., ["researcher", "writer"])
    selected_agents: list[str] | None = None
    # LiteLLM model string, e.g. "gemini/gemini-2.5-flash"
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


class UsageInfo(BaseModel):
    """LLM token usage and estimated cost for a research job."""

    total_tokens: int = Field(default=0, ge=0)
    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    successful_requests: int = Field(default=0, ge=0)
    estimated_cost_usd: float = Field(default=0.0, ge=0.0)
    model: str | None = None
    provider: str | None = None


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
    usage: UsageInfo | None = None
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


class CostSummaryResponse(BaseModel):
    """Aggregate LLM cost statistics (admin only)."""

    total_jobs: int
    total_tokens: int
    total_prompt_tokens: int
    total_completion_tokens: int
    total_estimated_cost_usd: float
    jobs_with_usage: int


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
    """A single racial group's metric value."""

    race: str
    value: float


class RacialGap(BaseModel):
    """Racial disparity summary with group values and max ratio."""

    groups: list[RacialGapGroup]
    max_ratio: float
    max_ratio_label: str


class StateSummaryInsight(BaseModel):
    """Pre-computed state-level stats: rank, percentile, and racial gap."""

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


# --- Explore query models ---


class ExploreQueryContext(BaseModel):
    """Current explore page state passed as context for AI queries."""

    source: str
    metric: str | None = None
    state_fips: str | None = None
    race: str | None = None
    year: int | None = None


class ExploreQueryRequest(BaseModel):
    """Natural language question with explore page context."""

    question: str
    context: ExploreQueryContext

    @field_validator("question")
    @classmethod
    def question_not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Question must not be blank")
        return v.strip()


class ExploreQueryResponse(BaseModel):
    """Answer from the context-aware query engine."""

    answer: str
    data: list[ExploreRow] | None = None
    visualization_hint: str | None = None


class ExplainRequest(BaseModel):
    """Structured data context for LLM explanation generation."""

    source: str
    metric: str
    state_fips: str
    state_name: str
    value: float
    national_average: float
    racial_gap: RacialGap | None = None
    year: int


class ExplainResponse(BaseModel):
    """LLM-generated explanation with methodology and caveats."""

    narrative: str
    methodology_note: str
    caveats: list[str]
    generated_at: str


# --- Model Comparison models ---


class PipelineStep(BaseModel):
    """A single step in the model pipeline."""

    step: str  # "parse", "search", "synthesize", "evaluate"
    model_name: str
    output: str
    latency_seconds: float


class PipelinePath(BaseModel):
    """Full pipeline execution path for one model configuration."""

    label: str  # "Base Model" or "Fine-Tuned"
    steps: list[PipelineStep]
    final_answer: str
    total_latency_seconds: float
    eval_score: float | None = None  # 1-5 score from evaluator model
    eval_explanation: str | None = None  # why the evaluator gave this score
    eval_issues: list[str] | None = None  # specific issues found


class CompareRequest(BaseModel):
    """Request to compare base vs fine-tuned model pipelines end-to-end."""

    prompt: str
    pipeline_a_parser: str | None = None
    pipeline_a_explainer: str | None = None
    pipeline_b_parser: str | None = None
    pipeline_b_explainer: str | None = None

    @field_validator("prompt")
    @classmethod
    def prompt_not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Prompt cannot be empty")
        return v


class CompareResponse(BaseModel):
    """End-to-end comparison of base and fine-tuned model pipelines."""

    baseline: PipelinePath
    finetuned: PipelinePath
    prompt: str


# --- Eval Run models ---


class EvalRunItem(BaseModel):
    """A single model evaluation run result."""

    id: str | None = None
    model_name: str
    model_version: str
    base_model_name: str
    task: str
    metrics: dict[str, float | None]
    ship_decision: str
    blocking_failures: list[dict] | None = None  # CriterionFailure dicts from eval harness
    created_at: str | None = None
    suggestions: dict | None = None


class EvalRunsResponse(BaseModel):
    """Collection of eval run results."""

    runs: list[EvalRunItem]


class SuggestionItem(BaseModel):
    """A single improvement suggestion from post-eval analysis."""

    metric: str
    severity: str
    current: float
    target: float
    suggestion: str
    category: str = "training_data"


class AnalyzeResponse(BaseModel):
    """Response from the eval run analysis endpoint."""

    run_id: str
    suggestions: dict


# --- Flywheel Metrics models ---


class CorpusStats(BaseModel):
    """Corpus composition statistics."""

    total_chunks: int
    total_tokens: int
    content_types: dict[str, int]
    unstructured_pct: float


class TrainingRunItem(BaseModel):
    """A training run with key metrics for the flywheel dashboard."""

    model_version: str
    task: str
    metrics: dict[str, Any]
    ship_decision: str
    created_at: str | None = None


class ResearchQualityItem(BaseModel):
    """Average evaluation score for a single eval type."""

    avg_score: float
    count: int


class TimeSeriesPoint(BaseModel):
    """A single data point on a time-series chart."""

    date: str
    value: float


class FlywheelMetricsResponse(BaseModel):
    """Full flywheel metrics dashboard response."""

    corpus: CorpusStats
    training_runs: list[TrainingRunItem]
    research_quality: dict[str, ResearchQualityItem]
    time_series: dict[str, list[TimeSeriesPoint]]


# --- Staff Upload Schemas ---


class DataSourceUploadRequest(BaseModel):
    source_name: str
    description: str
    geographic_level: Literal["state", "county", "tract"]
    # Constant year when the file has no per-row year column; optional if year_column is set.
    data_year: int | None = None
    source_url: str | None = None
    category_tags: list[str] | None = None
    # Declared column mapping — contributor tells us what each CSV column means.
    geo_column: str
    metric_value_column: str
    metric_name: str
    race_column: str | None = None
    year_column: str | None = None

    @field_validator("source_name")
    @classmethod
    def source_name_not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Source name cannot be empty")
        return v.strip()

    @field_validator("geo_column", "metric_value_column")
    @classmethod
    def column_names_non_blank(cls, v: str) -> str:
        s = v.strip() if isinstance(v, str) else ""
        if not s:
            raise ValueError("cannot be blank or whitespace-only")
        return s

    @field_validator("race_column", "year_column", mode="before")
    @classmethod
    def optional_column_names_strip(cls, v: object) -> str | None:
        if v is None:
            return None
        if isinstance(v, str):
            s = v.strip()
            return s or None
        return v

    @field_validator("metric_name")
    @classmethod
    def metric_name_valid(cls, v: str) -> str:
        from d4bl.services.datasource_processing.validation import validate_metric_name

        return validate_metric_name(v)

    @model_validator(mode="after")
    def data_year_or_year_column(self) -> "DataSourceUploadRequest":
        if self.data_year is None and not (self.year_column and self.year_column.strip()):
            raise ValueError("Either data_year or year_column is required")
        return self


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
    created_at: str | None = None
