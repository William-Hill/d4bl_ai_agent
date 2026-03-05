"""
Pydantic schemas shared by the FastAPI application.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, field_validator


class ResearchRequest(BaseModel):
    query: str
    summary_format: Literal["brief", "detailed", "comprehensive"] = "detailed"
    # List of agent names to run (e.g., ["researcher", "writer"])
    selected_agents: list[str] | None = None

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


class QueryResponse(BaseModel):
    answer: str
    sources: list[QuerySourceItem]
    query: str


# --- Explore Data models ---


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

