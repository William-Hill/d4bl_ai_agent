"""
Pydantic schemas shared by the FastAPI application.
"""
from typing import List, Optional

from pydantic import BaseModel


class ResearchRequest(BaseModel):
    query: str
    summary_format: str = "detailed"  # brief, detailed, comprehensive
    selected_agents: Optional[List[str]] = None  # List of agent names to run (e.g., ["researcher", "writer"])


class ResearchResponse(BaseModel):
    job_id: str
    status: str
    message: str


class JobStatus(BaseModel):
    job_id: str
    trace_id: Optional[str] = None
    status: str  # pending, running, completed, error
    progress: Optional[str] = None
    result: Optional[dict] = None
    error: Optional[str] = None
    query: Optional[str] = None
    summary_format: Optional[str] = None
    logs: Optional[List[str]] = None
    research_data: Optional[dict] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    completed_at: Optional[str] = None


class JobHistoryResponse(BaseModel):
    jobs: List[JobStatus]
    total: int
    page: int
    page_size: int


class EvaluationResultItem(BaseModel):
    id: str
    span_id: str
    trace_id: Optional[str] = None
    job_id: Optional[str] = None
    eval_name: str
    label: Optional[str] = None
    score: Optional[float] = None
    explanation: Optional[str] = None
    input_text: Optional[str] = None
    output_text: Optional[str] = None
    context_text: Optional[str] = None
    created_at: Optional[str] = None


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


# --- Explore Data models ---


class IndicatorItem(BaseModel):
    fips_code: str
    geography_name: str
    state_fips: str
    geography_type: str
    year: int
    race: str
    metric: str
    value: float
    margin_of_error: Optional[float] = None


class PolicyBillItem(BaseModel):
    state: str
    state_name: str
    bill_number: str
    title: str
    summary: Optional[str] = None
    status: str
    topic_tags: Optional[List[str]] = None
    introduced_date: Optional[str] = None
    last_action_date: Optional[str] = None
    url: Optional[str] = None


class StateSummaryItem(BaseModel):
    state_fips: str
    state_name: str
    available_metrics: List[str]
    bill_count: int
    latest_year: Optional[int] = None

