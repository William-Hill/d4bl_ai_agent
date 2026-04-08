# LLM Cost Tracking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Track LLM token usage and estimated cost per research job, display per-job costs on ResultsCard, and show aggregate cost metrics on the admin page.

**Architecture:** Add a `usage` JSONB column to the `ResearchJob` table. After CrewAI's `kickoff()` returns a `CrewOutput` object, extract its `token_usage` attribute (a `UsageMetrics` Pydantic model with `total_tokens`, `prompt_tokens`, `completion_tokens`, `cached_prompt_tokens`, `successful_requests`). Calculate estimated cost using a simple per-model rate table (since the project uses Ollama locally and Gemini via LiteLLM, not OpenAI). Store the usage dict in the new column and expose it through the existing job status API and a new admin costs endpoint.

**Tech Stack:** Python (FastAPI, SQLAlchemy, CrewAI 1.5.0), TypeScript (Next.js, React 19), PostgreSQL (JSONB)

**Key Reference Files:**
- `src/d4bl/infra/database.py` -- ResearchJob model (line 39-81)
- `src/d4bl/services/research_runner.py` -- crew kickoff + result processing (line 399-427 for kickoff, line 448-792 for result handling)
- `src/d4bl/app/api.py` -- GET /api/jobs/{id} (line 642-653), admin endpoints (line 1963+)
- `src/d4bl/app/schemas.py` -- JobStatus schema (line 34-47)
- `ui-nextjs/components/ResultsCard.tsx` -- research results display
- `ui-nextjs/app/admin/page.tsx` -- admin dashboard
- `ui-nextjs/lib/types.ts` -- frontend type definitions
- `ui-nextjs/lib/api.ts` -- API client functions and types
- CrewAI source: `.venv/.../crewai/crews/crew_output.py` -- CrewOutput has `token_usage: UsageMetrics`
- CrewAI source: `.venv/.../crewai/types/usage_metrics.py` -- fields: `total_tokens`, `prompt_tokens`, `cached_prompt_tokens`, `completion_tokens`, `successful_requests`

---

### Task 1: Add `usage` JSONB column to ResearchJob model and create migration

**Files:**
- Modify: `src/d4bl/infra/database.py`
- Create: `supabase/migrations/20260407000001_add_usage_column.sql`
- Modify: `tests/test_database.py`

- [ ] **Step 1: Write test for the new `usage` column**

In `tests/test_database.py`, add a test verifying the `usage` column exists on `ResearchJob` and is JSONB type:

```python
from sqlalchemy.dialects.postgresql import JSONB


class TestUsageColumn:
    """Verify the usage JSONB column on ResearchJob."""

    def test_research_job_has_usage_column(self):
        col = ResearchJob.__table__.columns["usage"]
        assert col is not None

    def test_usage_column_is_jsonb(self):
        col = ResearchJob.__table__.columns["usage"]
        assert isinstance(col.type, JSONB)

    def test_usage_column_is_nullable(self):
        col = ResearchJob.__table__.columns["usage"]
        assert col.nullable is True

    def test_to_dict_includes_usage(self):
        job = ResearchJob()
        job.job_id = uuid4()
        job.query = "test"
        job.summary_format = "detailed"
        job.status = "pending"
        job.usage = {"total_tokens": 100, "estimated_cost_usd": 0.001}
        d = job.to_dict()
        assert d["usage"] == {"total_tokens": 100, "estimated_cost_usd": 0.001}

    def test_to_dict_usage_none_when_unset(self):
        job = ResearchJob()
        job.job_id = uuid4()
        job.query = "test"
        job.summary_format = "detailed"
        job.status = "pending"
        d = job.to_dict()
        assert d["usage"] is None
```

Add the necessary import at the top of `tests/test_database.py`:

```python
from uuid import uuid4
```

**Test command:** `python -m pytest tests/test_database.py::TestUsageColumn -v`

- [ ] **Step 2: Add `usage` column to ResearchJob model**

In `src/d4bl/infra/database.py`, add the `usage` column to the `ResearchJob` class after the `user_id` column (line 62):

```python
    # No ForeignKey -- auth.users is managed by Supabase, not SQLAlchemy
    user_id = Column(PG_UUID(as_uuid=True), nullable=True, index=True)
    usage = Column(JSONB, nullable=True)  # LLM token usage and cost per job
```

- [ ] **Step 3: Update `to_dict` to include `usage`**

In `src/d4bl/infra/database.py`, update the `to_dict` method of `ResearchJob` to include the new field. Add after the `"user_id"` line (line 81):

```python
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
            "usage": self.usage,
        }
```

- [ ] **Step 4: Create SQL migration**

Create `supabase/migrations/20260407000001_add_usage_column.sql`:

```sql
-- Add JSONB column to track LLM token usage and estimated cost per research job.
ALTER TABLE research_jobs ADD COLUMN IF NOT EXISTS usage JSONB;

COMMENT ON COLUMN research_jobs.usage IS
  'LLM token usage and cost: {prompt_tokens, completion_tokens, total_tokens, estimated_cost_usd, model}';
```

**Test command:** `python -m pytest tests/test_database.py -v`

**Commit:** `git commit -m "feat(infra): add usage JSONB column to ResearchJob for cost tracking"`

---

### Task 2: Extract token usage from CrewAI result and store in database

**Files:**
- Create: `src/d4bl/services/cost_tracker.py`
- Modify: `src/d4bl/services/research_runner.py`
- Create: `tests/test_cost_tracker.py`
- Modify: `tests/test_warmup.py` (if it tests `update_job_status`)

- [ ] **Step 1: Write tests for cost_tracker module**

Create `tests/test_cost_tracker.py`:

```python
"""Tests for the cost tracker utility."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock


class TestExtractUsageMetrics:
    """Verify extraction of token usage from a CrewAI result."""

    def test_extracts_token_counts_from_crew_output(self):
        from d4bl.services.cost_tracker import extract_usage

        mock_usage = MagicMock()
        mock_usage.total_tokens = 1500
        mock_usage.prompt_tokens = 1000
        mock_usage.completion_tokens = 500
        mock_usage.cached_prompt_tokens = 50
        mock_usage.successful_requests = 5

        mock_result = MagicMock()
        mock_result.token_usage = mock_usage

        usage = extract_usage(mock_result, model="ollama/qwen2.5:3b")

        assert usage["total_tokens"] == 1500
        assert usage["prompt_tokens"] == 1000
        assert usage["completion_tokens"] == 500
        assert usage["cached_prompt_tokens"] == 50
        assert usage["successful_requests"] == 5
        assert usage["model"] == "ollama/qwen2.5:3b"

    def test_returns_none_when_no_token_usage(self):
        from d4bl.services.cost_tracker import extract_usage

        mock_result = MagicMock(spec=[])  # no token_usage attribute

        usage = extract_usage(mock_result, model="ollama/qwen2.5:3b")
        assert usage is None

    def test_returns_none_when_token_usage_is_none(self):
        from d4bl.services.cost_tracker import extract_usage

        mock_result = MagicMock()
        mock_result.token_usage = None

        usage = extract_usage(mock_result, model="ollama/qwen2.5:3b")
        assert usage is None

    def test_returns_none_when_all_tokens_zero(self):
        from d4bl.services.cost_tracker import extract_usage

        mock_usage = MagicMock()
        mock_usage.total_tokens = 0
        mock_usage.prompt_tokens = 0
        mock_usage.completion_tokens = 0
        mock_usage.cached_prompt_tokens = 0
        mock_usage.successful_requests = 0

        mock_result = MagicMock()
        mock_result.token_usage = mock_usage

        usage = extract_usage(mock_result, model="ollama/qwen2.5:3b")
        assert usage is None


class TestEstimateCost:
    """Verify cost estimation logic."""

    def test_ollama_local_models_are_free(self):
        from d4bl.services.cost_tracker import estimate_cost_usd

        cost = estimate_cost_usd(
            prompt_tokens=10000,
            completion_tokens=5000,
            model="ollama/qwen2.5:3b",
        )
        assert cost == 0.0

    def test_gemini_flash_cost(self):
        from d4bl.services.cost_tracker import estimate_cost_usd

        # Gemini 2.5 Flash: $0.15/1M input, $0.60/1M output (as of 2025)
        cost = estimate_cost_usd(
            prompt_tokens=1_000_000,
            completion_tokens=1_000_000,
            model="gemini/gemini-2.5-flash",
        )
        assert cost == pytest.approx(0.75, abs=0.01)

    def test_unknown_model_returns_zero(self):
        from d4bl.services.cost_tracker import estimate_cost_usd

        cost = estimate_cost_usd(
            prompt_tokens=1000,
            completion_tokens=500,
            model="unknown/model",
        )
        assert cost == 0.0

    def test_extract_usage_includes_estimated_cost(self):
        from d4bl.services.cost_tracker import extract_usage

        mock_usage = MagicMock()
        mock_usage.total_tokens = 2_000_000
        mock_usage.prompt_tokens = 1_000_000
        mock_usage.completion_tokens = 1_000_000
        mock_usage.cached_prompt_tokens = 0
        mock_usage.successful_requests = 10

        mock_result = MagicMock()
        mock_result.token_usage = mock_usage

        usage = extract_usage(mock_result, model="gemini/gemini-2.5-flash")

        assert "estimated_cost_usd" in usage
        assert usage["estimated_cost_usd"] > 0

    def test_extract_usage_ollama_cost_is_zero(self):
        from d4bl.services.cost_tracker import extract_usage

        mock_usage = MagicMock()
        mock_usage.total_tokens = 5000
        mock_usage.prompt_tokens = 3000
        mock_usage.completion_tokens = 2000
        mock_usage.cached_prompt_tokens = 0
        mock_usage.successful_requests = 3

        mock_result = MagicMock()
        mock_result.token_usage = mock_usage

        usage = extract_usage(mock_result, model="ollama/llama3")

        assert usage["estimated_cost_usd"] == 0.0
```

**Test command:** `python -m pytest tests/test_cost_tracker.py -v`

- [ ] **Step 2: Implement cost_tracker module**

Create `src/d4bl/services/cost_tracker.py`:

```python
"""
Utility for extracting LLM token usage from CrewAI results and estimating cost.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Per-million-token pricing. Local Ollama models are free.
# Format: model_prefix -> (input_cost_per_1M, output_cost_per_1M)
_MODEL_COSTS: dict[str, tuple[float, float]] = {
    "ollama/": (0.0, 0.0),
    "gemini/gemini-2.5-flash": (0.15, 0.60),
    "gemini/gemini-2.5-pro": (1.25, 10.00),
    "gemini/gemini-2.0-flash": (0.10, 0.40),
    "gemini/gemini-1.5-flash": (0.075, 0.30),
    "gemini/gemini-1.5-pro": (1.25, 5.00),
}


def estimate_cost_usd(
    prompt_tokens: int,
    completion_tokens: int,
    model: str,
) -> float:
    """Estimate USD cost based on token counts and model name.

    Uses a prefix-match lookup table. Returns 0.0 for unknown or local models.
    """
    model_lower = model.lower() if model else ""

    # Try exact match first, then prefix match (longest prefix wins)
    matched_cost: tuple[float, float] | None = None
    matched_len = 0

    for prefix, costs in _MODEL_COSTS.items():
        if model_lower.startswith(prefix) and len(prefix) > matched_len:
            matched_cost = costs
            matched_len = len(prefix)

    if matched_cost is None:
        return 0.0

    input_cost_per_m, output_cost_per_m = matched_cost
    cost = (prompt_tokens / 1_000_000) * input_cost_per_m + (
        completion_tokens / 1_000_000
    ) * output_cost_per_m
    return round(cost, 6)


def extract_usage(result: Any, model: str) -> dict[str, Any] | None:
    """Extract token usage from a CrewAI CrewOutput and compute estimated cost.

    Returns a dict suitable for storing in the ``usage`` JSONB column, or None
    if no meaningful usage data is available.
    """
    token_usage = getattr(result, "token_usage", None)
    if token_usage is None:
        return None

    total = getattr(token_usage, "total_tokens", 0) or 0
    prompt = getattr(token_usage, "prompt_tokens", 0) or 0
    completion = getattr(token_usage, "completion_tokens", 0) or 0
    cached = getattr(token_usage, "cached_prompt_tokens", 0) or 0
    requests = getattr(token_usage, "successful_requests", 0) or 0

    if total == 0 and prompt == 0 and completion == 0:
        return None

    cost = estimate_cost_usd(prompt, completion, model)

    return {
        "total_tokens": total,
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "cached_prompt_tokens": cached,
        "successful_requests": requests,
        "estimated_cost_usd": cost,
        "model": model,
    }
```

**Test command:** `python -m pytest tests/test_cost_tracker.py -v`

- [ ] **Step 3: Wire cost extraction into research_runner.py**

In `src/d4bl/services/research_runner.py`, add the import near the top (after line 37):

```python
from d4bl.services.cost_tracker import extract_usage
```

Then, after the crew result is obtained and before the evaluation section (after line 427, where `sys.stdout` is restored), add usage extraction. Insert after the line `await notify_progress("Research completed, processing results...", phase="evaluation")` (line 448):

```python
            # Extract LLM token usage from CrewAI result
            usage_dict: dict | None = None
            try:
                model_name = model or settings.ollama_model or "ollama/unknown"
                usage_dict = extract_usage(result, model=model_name)
                if usage_dict:
                    logger.info(
                        "Token usage: %d total (%d prompt + %d completion), est. $%.4f",
                        usage_dict["total_tokens"],
                        usage_dict["prompt_tokens"],
                        usage_dict["completion_tokens"],
                        usage_dict["estimated_cost_usd"],
                    )
            except Exception as usage_err:
                logger.warning("Failed to extract token usage: %s", usage_err)
```

- [ ] **Step 4: Update `update_job_status` to accept and store `usage`**

In `src/d4bl/services/research_runner.py`, update the `update_job_status` function signature (line 239) to accept `usage`:

```python
async def update_job_status(
    db: AsyncSession,
    job_id: str,
    status: str,
    progress: str | None = None,
    result: dict | None = None,
    research_data: dict | None = None,
    error: str | None = None,
    logs: list[str] | None = None,
    trace_id: str | None = None,
    evaluation_results: dict | None = None,
    usage: dict | None = None,
) -> None:
```

Inside the function body, after the `trace_id` assignment (after line 275), add:

```python
        if usage is not None:
            job.usage = usage
```

- [ ] **Step 5: Pass `usage_dict` through `set_status` and the final status update**

In `src/d4bl/services/research_runner.py`, update the inner `set_status` function (around line 304) to accept and forward `usage`:

```python
    async def set_status(
        progress_msg: str | None,
        status: str = "running",
        result: dict | None = None,
        research_data: dict | None = None,
        error: str | None = None,
        logs: list[str] | None = None,
        trace_override: str | None = None,
        evaluation_results: dict | None = None,
        usage: dict | None = None,
    ) -> None:
        trace_value = trace_override or trace_id_hex
        async for db in get_db():
            try:
                await update_job_status(
                    db,
                    job_id,
                    status,
                    progress=progress_msg,
                    result=result,
                    research_data=research_data,
                    error=error,
                    logs=logs,
                    trace_id=trace_value,
                    evaluation_results=evaluation_results,
                    usage=usage,
                )
                break
            except Exception as update_err:  # noqa: BLE001
                print(f"Error updating job status: {update_err}")
                break
```

Then update the final `set_status` call (around line 785) to include `usage=usage_dict`:

```python
            await set_status(
                "Research completed successfully!",
                status="completed",
                result=result_dict,
                research_data=research_data_dict,
                logs=final_logs,
                evaluation_results=evaluation_results,
                usage=usage_dict,
            )
```

**Test command:** `python -m pytest tests/test_cost_tracker.py tests/test_database.py -v`

**Commit:** `git commit -m "feat(services): extract CrewAI token usage and estimate cost per job"`

---

### Task 3: Add `usage` to the JobStatus schema so it appears in API responses

**Files:**
- Modify: `src/d4bl/app/schemas.py`
- Modify: `ui-nextjs/lib/api.ts`
- Modify: `tests/test_app_schemas.py`

- [ ] **Step 1: Write test for the schema change**

In `tests/test_app_schemas.py`, add a test (append to the file):

```python
class TestJobStatusUsage:
    """Verify usage field is included in JobStatus schema."""

    def test_job_status_accepts_usage_dict(self):
        from d4bl.app.schemas import JobStatus

        status = JobStatus(
            job_id="abc-123",
            status="completed",
            usage={
                "total_tokens": 1500,
                "prompt_tokens": 1000,
                "completion_tokens": 500,
                "estimated_cost_usd": 0.003,
                "model": "ollama/qwen2.5:3b",
            },
        )
        assert status.usage["total_tokens"] == 1500
        assert status.usage["estimated_cost_usd"] == 0.003

    def test_job_status_usage_defaults_to_none(self):
        from d4bl.app.schemas import JobStatus

        status = JobStatus(job_id="abc-123", status="pending")
        assert status.usage is None
```

**Test command:** `python -m pytest tests/test_app_schemas.py::TestJobStatusUsage -v`

- [ ] **Step 2: Add `usage` field to `JobStatus` schema**

In `src/d4bl/app/schemas.py`, add `usage` to the `JobStatus` class (after `completed_at` on line 47):

```python
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
    usage: dict | None = None
```

- [ ] **Step 3: Update frontend `JobStatus` type in `ui-nextjs/lib/api.ts`**

In `ui-nextjs/lib/api.ts`, add `usage` to the `JobStatus` interface (after `completed_at`, around line 75):

```typescript
export interface JobStatus {
  job_id: string;
  trace_id?: string;
  status: 'pending' | 'running' | 'completed' | 'error';
  progress?: string;
  result?: ResearchResult;
  error?: string;
  query?: string;
  summary_format?: string;
  logs?: string[];
  created_at?: string;
  updated_at?: string;
  completed_at?: string;
  usage?: {
    total_tokens: number;
    prompt_tokens: number;
    completion_tokens: number;
    cached_prompt_tokens?: number;
    successful_requests?: number;
    estimated_cost_usd: number;
    model: string;
  };
}
```

**Test command:** `python -m pytest tests/test_app_schemas.py -v`

**Commit:** `git commit -m "feat(api): include usage in JobStatus schema for cost visibility"`

---

### Task 4: Add admin costs API endpoint

**Files:**
- Modify: `src/d4bl/app/api.py`
- Modify: `src/d4bl/app/schemas.py`
- Create: `tests/test_admin_costs.py`

- [ ] **Step 1: Write tests for the admin costs endpoint**

Create `tests/test_admin_costs.py`:

```python
"""Tests for the admin costs endpoint."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from tests.conftest import MOCK_ADMIN, MOCK_USER


@pytest.fixture
def admin_client(override_admin_auth):
    """TestClient authenticated as admin."""
    return TestClient(override_admin_auth, raise_server_exceptions=False)


@pytest.fixture
def user_client(override_auth):
    """TestClient authenticated as regular user."""
    return TestClient(override_auth, raise_server_exceptions=False)


class TestAdminCostsEndpoint:
    """Test GET /api/admin/costs endpoint."""

    def test_requires_admin(self, user_client):
        """Regular users cannot access the costs endpoint."""
        response = user_client.get("/api/admin/costs")
        assert response.status_code in (401, 403)

    @patch("d4bl.app.api.get_db")
    def test_returns_aggregate_costs(self, mock_get_db, admin_client):
        """Admin gets aggregate cost stats."""
        # Mock the database query results
        mock_db = AsyncMock()

        # Mock for total jobs with usage
        mock_total_result = MagicMock()
        mock_total_result.scalar_one.return_value = 5

        # Mock for aggregate sums
        mock_agg_result = MagicMock()
        mock_agg_result.one.return_value = (7500, 5000, 2500, 0.015)

        # Mock for recent jobs
        mock_recent_result = MagicMock()
        mock_recent_result.mappings.return_value.all.return_value = [
            {
                "job_id": str(uuid4()),
                "query": "test query",
                "created_at": "2026-04-07T00:00:00",
                "usage": {
                    "total_tokens": 1500,
                    "estimated_cost_usd": 0.003,
                    "model": "ollama/qwen2.5:3b",
                },
            }
        ]

        call_count = 0
        async def mock_execute(query, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return mock_total_result
            elif call_count == 2:
                return mock_agg_result
            else:
                return mock_recent_result

        mock_db.execute = mock_execute

        async def mock_db_gen():
            yield mock_db

        mock_get_db.return_value = mock_db_gen()

        response = admin_client.get("/api/admin/costs")
        assert response.status_code == 200
        data = response.json()
        assert "total_jobs_with_usage" in data
        assert "total_tokens" in data
        assert "total_estimated_cost_usd" in data
        assert "recent_jobs" in data

    @patch("d4bl.app.api.get_db")
    def test_returns_zeros_when_no_jobs_have_usage(self, mock_get_db, admin_client):
        """Returns zero aggregates when no jobs have usage data."""
        mock_db = AsyncMock()

        mock_total_result = MagicMock()
        mock_total_result.scalar_one.return_value = 0

        mock_agg_result = MagicMock()
        mock_agg_result.one.return_value = (None, None, None, None)

        mock_recent_result = MagicMock()
        mock_recent_result.mappings.return_value.all.return_value = []

        call_count = 0
        async def mock_execute(query, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return mock_total_result
            elif call_count == 2:
                return mock_agg_result
            else:
                return mock_recent_result

        mock_db.execute = mock_execute

        async def mock_db_gen():
            yield mock_db

        mock_get_db.return_value = mock_db_gen()

        response = admin_client.get("/api/admin/costs")
        assert response.status_code == 200
        data = response.json()
        assert data["total_jobs_with_usage"] == 0
        assert data["total_tokens"] == 0
        assert data["total_estimated_cost_usd"] == 0.0
```

**Test command:** `python -m pytest tests/test_admin_costs.py -v`

- [ ] **Step 2: Add response schema for admin costs**

In `src/d4bl/app/schemas.py`, add after the `UpdateRoleRequest` class (around line 193):

```python
class CostSummaryJob(BaseModel):
    """A recent job entry in the cost summary."""

    job_id: str
    query: str | None = None
    created_at: str | None = None
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0
    model: str | None = None


class CostSummaryResponse(BaseModel):
    """Aggregate cost stats returned by the admin costs endpoint."""

    total_jobs_with_usage: int = 0
    total_tokens: int = 0
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_estimated_cost_usd: float = 0.0
    avg_tokens_per_job: float = 0.0
    avg_cost_per_job: float = 0.0
    recent_jobs: list[CostSummaryJob] = []
```

- [ ] **Step 3: Add the admin costs endpoint to api.py**

In `src/d4bl/app/api.py`, add the import for the new schema. Update the import block (around line 39) to include `CostSummaryJob, CostSummaryResponse`:

```python
from d4bl.app.schemas import (
    CompareRequest,
    CompareResponse,
    CostSummaryJob,
    CostSummaryResponse,
    EvalRunItem,
    # ... rest of imports
)
```

Then add the endpoint after the existing admin endpoints (after the ingestion status endpoint, around line 2110):

```python
# ---------------------------------------------------------------------------
# Admin cost tracking
# ---------------------------------------------------------------------------


@app.get("/api/admin/costs", response_model=CostSummaryResponse)
async def get_cost_summary(
    limit: int = 20,
    user: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Aggregate LLM cost stats across all research jobs (admin only)."""
    limit = max(1, min(limit, 100))

    # Count jobs with non-null usage
    count_result = await db.execute(
        text("SELECT count(*) FROM research_jobs WHERE usage IS NOT NULL")
    )
    total_jobs = count_result.scalar_one()

    # Aggregate token totals and cost
    agg_result = await db.execute(
        text("""
            SELECT
                COALESCE(SUM((usage->>'total_tokens')::int), 0),
                COALESCE(SUM((usage->>'prompt_tokens')::int), 0),
                COALESCE(SUM((usage->>'completion_tokens')::int), 0),
                COALESCE(SUM((usage->>'estimated_cost_usd')::numeric), 0)
            FROM research_jobs
            WHERE usage IS NOT NULL
        """)
    )
    total_tokens, total_prompt, total_completion, total_cost = agg_result.one()

    total_tokens = total_tokens or 0
    total_prompt = total_prompt or 0
    total_completion = total_completion or 0
    total_cost = float(total_cost or 0)

    avg_tokens = total_tokens / total_jobs if total_jobs > 0 else 0.0
    avg_cost = total_cost / total_jobs if total_jobs > 0 else 0.0

    # Recent jobs with usage
    recent_result = await db.execute(
        text("""
            SELECT job_id, query, created_at, usage
            FROM research_jobs
            WHERE usage IS NOT NULL
            ORDER BY created_at DESC
            LIMIT :lim
        """),
        {"lim": limit},
    )
    recent_rows = recent_result.mappings().all()

    recent_jobs = []
    for row in recent_rows:
        usage = row["usage"] or {}
        recent_jobs.append(
            CostSummaryJob(
                job_id=str(row["job_id"]),
                query=row["query"],
                created_at=row["created_at"].isoformat() if row["created_at"] else None,
                total_tokens=usage.get("total_tokens", 0),
                estimated_cost_usd=usage.get("estimated_cost_usd", 0.0),
                model=usage.get("model"),
            )
        )

    return CostSummaryResponse(
        total_jobs_with_usage=total_jobs,
        total_tokens=total_tokens,
        total_prompt_tokens=total_prompt,
        total_completion_tokens=total_completion,
        total_estimated_cost_usd=total_cost,
        avg_tokens_per_job=round(avg_tokens, 1),
        avg_cost_per_job=round(avg_cost, 6),
        recent_jobs=recent_jobs,
    )
```

**Test command:** `python -m pytest tests/test_admin_costs.py -v`

**Commit:** `git commit -m "feat(api): add GET /api/admin/costs endpoint for aggregate LLM cost stats"`

---

### Task 5: Display per-job cost on ResultsCard

**Files:**
- Modify: `ui-nextjs/components/ResultsCard.tsx`
- Modify: `ui-nextjs/lib/types.ts`

- [ ] **Step 1: Add `usage` to the `ResearchResult` type**

In `ui-nextjs/lib/types.ts`, update the `ResearchResult` interface to include an optional `usage` field:

```typescript
/** Result payload returned when a research job completes. */
export interface ResearchResult {
  report?: string;
  tasks_output?: ResearchTaskOutput[];
  raw_output?: string;
}

/** LLM token usage and cost metadata. */
export interface UsageMetrics {
  total_tokens: number;
  prompt_tokens: number;
  completion_tokens: number;
  cached_prompt_tokens?: number;
  successful_requests?: number;
  estimated_cost_usd: number;
  model: string;
}
```

- [ ] **Step 2: Update ResultsCard to accept and display usage**

In `ui-nextjs/components/ResultsCard.tsx`, update the `ResultsCardProps` interface to accept optional `usage` and display it:

```typescript
'use client';

import { useEffect, useMemo, useRef } from 'react';
import { ResearchResult, ResearchTaskOutput, UsageMetrics } from '@/lib/types';

interface ResultsCardProps {
  results: ResearchResult;
  usage?: UsageMetrics | null;
}

function formatTokenCount(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return n.toString();
}

function formatCost(usd: number): string {
  if (usd === 0) return 'free (local)';
  if (usd < 0.01) return `~$${usd.toFixed(4)}`;
  return `~$${usd.toFixed(2)}`;
}

export default function ResultsCard({ results, usage }: ResultsCardProps) {
```

Then, inside the component's return JSX, add a usage badge after the `<h2>Research Results</h2>` heading (before the `<div className="space-y-6">`):

```tsx
      <h2 className="text-2xl font-bold text-white mb-6">
        Research Results
      </h2>

      {usage && usage.total_tokens > 0 && (
        <div className="flex items-center gap-3 mb-4 text-sm text-gray-400">
          <span>{formatTokenCount(usage.total_tokens)} tokens</span>
          <span className="text-[#404040]">|</span>
          <span>{formatCost(usage.estimated_cost_usd)}</span>
          {usage.model && (
            <>
              <span className="text-[#404040]">|</span>
              <span className="text-gray-500">{usage.model}</span>
            </>
          )}
        </div>
      )}

      <div className="space-y-6">
```

**Test command:** `cd ui-nextjs && npm run build`

**Commit:** `git commit -m "feat(ui): display per-job token usage and cost on ResultsCard"`

Note: The parent page (`ui-nextjs/app/page.tsx`) threading of the `usage` prop is handled in Task 7.

---

### Task 6: Add cost tracking section to admin page

**Files:**
- Modify: `ui-nextjs/app/admin/page.tsx`

- [ ] **Step 1: Add cost fetching state and logic**

In `ui-nextjs/app/admin/page.tsx`, add state for cost data and a fetch function. Add these state declarations after the existing state (after `ingestLoading` around line 42):

```typescript
  // --- Cost tracking state ---
  interface CostSummaryJob {
    job_id: string;
    query: string | null;
    created_at: string | null;
    total_tokens: number;
    estimated_cost_usd: number;
    model: string | null;
  }

  interface CostSummary {
    total_jobs_with_usage: number;
    total_tokens: number;
    total_prompt_tokens: number;
    total_completion_tokens: number;
    total_estimated_cost_usd: number;
    avg_tokens_per_job: number;
    avg_cost_per_job: number;
    recent_jobs: CostSummaryJob[];
  }

  const [costSummary, setCostSummary] = useState<CostSummary | null>(null);
  const [costLoading, setCostLoading] = useState(false);
```

Add a fetch function after `fetchUsers`:

```typescript
  const fetchCosts = useCallback(async () => {
    if (!session?.access_token) return;
    setCostLoading(true);
    try {
      const response = await fetch(`${API_BASE}/api/admin/costs`, {
        headers: getHeaders(),
      });
      if (response.ok) {
        setCostSummary(await response.json());
      }
    } catch {
      // Silently fail -- cost tracking is informational
    } finally {
      setCostLoading(false);
    }
  }, [session?.access_token, getHeaders]);
```

Add the effect to fetch costs when admin (after the `fetchUsers` effect):

```typescript
  useEffect(() => {
    if (isAdmin) fetchCosts();
  }, [isAdmin, fetchCosts]);
```

- [ ] **Step 2: Add Cost Tracking UI section**

In `ui-nextjs/app/admin/page.tsx`, add a Cost Tracking section in the JSX. Insert it before the "Invite User" form section (before the `{/* Invite form */}` comment):

```tsx
        {/* Cost Tracking */}
        <div className="bg-[#1a1a1a] border border-[#404040] rounded-lg p-6 mb-8">
          <h2 className="text-lg font-semibold text-white mb-4">LLM Cost Tracking</h2>
          {costLoading && <p className="text-gray-400 text-sm">Loading costs...</p>}
          {costSummary && (
            <>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-6">
                <div className="bg-[#292929] rounded-lg p-4 border border-[#404040]">
                  <p className="text-xs text-gray-500 uppercase tracking-wide">Total Spend</p>
                  <p className="text-xl font-bold text-white mt-1">
                    {costSummary.total_estimated_cost_usd === 0
                      ? '$0.00'
                      : costSummary.total_estimated_cost_usd < 0.01
                        ? `$${costSummary.total_estimated_cost_usd.toFixed(4)}`
                        : `$${costSummary.total_estimated_cost_usd.toFixed(2)}`}
                  </p>
                </div>
                <div className="bg-[#292929] rounded-lg p-4 border border-[#404040]">
                  <p className="text-xs text-gray-500 uppercase tracking-wide">Total Tokens</p>
                  <p className="text-xl font-bold text-white mt-1">
                    {costSummary.total_tokens >= 1_000_000
                      ? `${(costSummary.total_tokens / 1_000_000).toFixed(1)}M`
                      : costSummary.total_tokens >= 1_000
                        ? `${(costSummary.total_tokens / 1_000).toFixed(1)}k`
                        : costSummary.total_tokens}
                  </p>
                </div>
                <div className="bg-[#292929] rounded-lg p-4 border border-[#404040]">
                  <p className="text-xs text-gray-500 uppercase tracking-wide">Jobs Tracked</p>
                  <p className="text-xl font-bold text-white mt-1">
                    {costSummary.total_jobs_with_usage}
                  </p>
                </div>
                <div className="bg-[#292929] rounded-lg p-4 border border-[#404040]">
                  <p className="text-xs text-gray-500 uppercase tracking-wide">Avg / Job</p>
                  <p className="text-xl font-bold text-white mt-1">
                    {costSummary.avg_cost_per_job === 0
                      ? '$0.00'
                      : `$${costSummary.avg_cost_per_job.toFixed(4)}`}
                  </p>
                </div>
              </div>

              {costSummary.recent_jobs.length > 0 && (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-[#404040]">
                        <th className="text-left py-2 px-3 text-gray-400 font-normal">Query</th>
                        <th className="text-right py-2 px-3 text-gray-400 font-normal">Tokens</th>
                        <th className="text-right py-2 px-3 text-gray-400 font-normal">Cost</th>
                        <th className="text-right py-2 px-3 text-gray-400 font-normal">Model</th>
                        <th className="text-right py-2 px-3 text-gray-400 font-normal">Date</th>
                      </tr>
                    </thead>
                    <tbody>
                      {costSummary.recent_jobs.map((job) => (
                        <tr key={job.job_id} className="border-b border-[#404040] last:border-0">
                          <td className="py-2 px-3 text-gray-300 max-w-xs truncate">
                            {job.query || '-'}
                          </td>
                          <td className="py-2 px-3 text-right text-gray-300 tabular-nums">
                            {job.total_tokens.toLocaleString()}
                          </td>
                          <td className="py-2 px-3 text-right text-gray-300 tabular-nums">
                            {job.estimated_cost_usd === 0
                              ? 'free'
                              : `$${job.estimated_cost_usd.toFixed(4)}`}
                          </td>
                          <td className="py-2 px-3 text-right text-gray-500">
                            {job.model || '-'}
                          </td>
                          <td className="py-2 px-3 text-right text-gray-500">
                            {job.created_at
                              ? new Date(job.created_at).toLocaleDateString()
                              : '-'}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              {costSummary.total_jobs_with_usage === 0 && (
                <p className="text-gray-500 text-sm">
                  No cost data yet. Costs will appear after research jobs complete.
                </p>
              )}
            </>
          )}
        </div>
```

**Test command:** `cd ui-nextjs && npm run build`

**Commit:** `git commit -m "feat(ui): add LLM cost tracking section to admin page"`

---

### Task 7: Thread `usage` prop to ResultsCard from the research page

**Files:**
- Modify: `ui-nextjs/app/page.tsx`

The research page (`ui-nextjs/app/page.tsx`) stores `results` as `ResearchResult | null` (line 22) and sets it from three code paths:
1. **WebSocket complete** (line 67): `setResults(data.result)` -- WS payload does not carry `usage`.
2. **Polling** (line 95): `setResults(status.result)` -- `status` is `JobStatus` which has `usage`.
3. **handleSelectJob** (lines 142/154): from `job.result` or `latestStatus.result` -- both `JobStatus` objects have `usage`.

- [ ] **Step 1: Add `usage` state variable**

In `ui-nextjs/app/page.tsx`, add a state variable for usage. Import `UsageMetrics` from `@/lib/types` (add to the existing import on line 13), then add state after line 22:

```typescript
import { QueryResponse, ResearchResult, UsageMetrics, WsMessage } from '@/lib/types';

// ... existing state ...
const [results, setResults] = useState<ResearchResult | null>(null);
const [usage, setUsage] = useState<UsageMetrics | null>(null);
```

- [ ] **Step 2: Set usage in WebSocket complete handler**

In the `switch (data.type)` block, update the `'complete'` case (around line 64-69). Capture `jobId` before it is nulled out to fetch usage:

```typescript
case 'complete':
  updateLogs(data);
  setProgress('Research completed!');
  setResults(data.result);
  setPhase(null);
  // Fetch usage from job status (WS complete payload doesn't include it)
  if (jobId) {
    getJobStatus(jobId).then(s => setUsage(s.usage ?? null)).catch(() => {});
  }
  setJobId(null);
  break;
```

- [ ] **Step 3: Set usage in polling path**

In the polling effect (around line 92-96), set usage alongside results:

```typescript
if (status.status === 'completed') {
  setProgress('Research completed!');
  setResults(status.result ?? null);
  setUsage(status.usage ?? null);
  setJobId(null);
  clearInterval(pollInterval);
}
```

- [ ] **Step 4: Set usage in handleSelectJob**

In `handleSelectJob` (around line 141-154), set usage in both completion paths:

```typescript
// Path 1: job already completed (line 141-142)
if (job.status === 'completed' && job.result) {
  setResults(job.result);
  setUsage(job.usage ?? null);
  // ...existing scroll code...
}

// Path 2: fetched latest status (line 153-154)
if (latestStatus.status === 'completed' && latestStatus.result) {
  setResults(latestStatus.result);
  setUsage(latestStatus.usage ?? null);
}
```

- [ ] **Step 5: Clear usage on new job submission**

In `handleSubmit` (line 117), clear usage when starting a new job:

```typescript
setResults(null);
setUsage(null);
```

- [ ] **Step 6: Pass usage to ResultsCard**

Update line 269 from:

```tsx
<ResultsCard results={results} />
```

to:

```tsx
<ResultsCard results={results} usage={usage} />
```

**Test command:** `cd ui-nextjs && npm run build && npm run lint`

**Commit:** `git commit -m "feat(ui): thread usage prop to ResultsCard from research page"`

---

### Task 8: Run full test suite and build verification

- [ ] **Step 1: Run backend tests**

```bash
python -m pytest tests/test_database.py tests/test_cost_tracker.py tests/test_app_schemas.py tests/test_admin_costs.py -v
```

- [ ] **Step 2: Run full backend test suite**

```bash
python -m pytest tests/ -v --timeout=30
```

- [ ] **Step 3: Run frontend build and lint**

```bash
cd ui-nextjs && npm run build && npm run lint
```

- [ ] **Step 4: Apply migration to local database**

```bash
python scripts/run_vector_migration.py
# Or manually:
# psql -h localhost -p 54322 -U postgres -d postgres -f supabase/migrations/20260407000001_add_usage_column.sql
```

**Commit:** (no commit -- verification step)
