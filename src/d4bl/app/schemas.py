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

