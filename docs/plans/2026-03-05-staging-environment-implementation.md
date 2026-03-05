# Staging Environment & CI/CD Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Set up CI/CD with GitHub Actions, deploy to Fly.io staging, add LLM provider configurability with UI selector, and create a stakeholder distribution package with basic multi-tenancy.

**Architecture:** Three Fly.io apps (backend, frontend, Crawl4AI) with Supabase Cloud for database/vectors, Langfuse Cloud for observability, and Gemini Flash as the default staging LLM. GitHub Actions handles PR verification and auto-deploy on merge to `main` or push to `epic/*`.

**Tech Stack:** Fly.io, GitHub Actions, Supabase Cloud, Langfuse Cloud, LiteLLM (Gemini Flash), Docker, FastAPI, Next.js

**Design doc:** `docs/plans/2026-03-05-staging-environment-design.md`

---

### Task 1: Add LLM provider settings to Settings dataclass

**Files:**
- Modify: `src/d4bl/settings.py`
- Test: `tests/test_settings.py`

**Step 1: Write failing tests for new LLM settings**

Add to `tests/test_settings.py`:

```python
# In TestFieldDefaults class:

def test_llm_provider_default(self) -> None:
    s = _fresh_settings(LLM_PROVIDER=None)
    assert s.llm_provider == "ollama"

def test_llm_provider_from_env(self) -> None:
    s = _fresh_settings(LLM_PROVIDER="gemini")
    assert s.llm_provider == "gemini"

def test_llm_provider_lowercased(self) -> None:
    s = _fresh_settings(LLM_PROVIDER="Gemini")
    assert s.llm_provider == "gemini"

def test_llm_model_default(self) -> None:
    s = _fresh_settings(LLM_MODEL=None)
    assert s.llm_model == "mistral"

def test_llm_model_from_env(self) -> None:
    s = _fresh_settings(LLM_MODEL="gemini-2.0-flash")
    assert s.llm_model == "gemini-2.0-flash"

def test_llm_api_key_default_none(self) -> None:
    s = _fresh_settings(LLM_API_KEY=None)
    assert s.llm_api_key is None

def test_llm_api_key_from_env(self) -> None:
    s = _fresh_settings(LLM_API_KEY="sk-test-key")
    assert s.llm_api_key == "sk-test-key"

def test_tenant_id_default_none(self) -> None:
    s = _fresh_settings(TENANT_ID=None)
    assert s.tenant_id is None

def test_tenant_id_from_env(self) -> None:
    s = _fresh_settings(TENANT_ID="org-d4bl")
    assert s.tenant_id == "org-d4bl"
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_settings.py -v -k "llm_provider or llm_model or llm_api_key or tenant_id"`
Expected: FAIL — `AttributeError: 'Settings' object has no attribute 'llm_provider'`

**Step 3: Add LLM and tenant fields to Settings**

In `src/d4bl/settings.py`, add to the `Settings` class:

```python
# After the existing CORS fields, add:

# -- LLM provider --
llm_provider: str = field(init=False)
llm_model: str = field(init=False)
llm_api_key: str | None = field(init=False)

# -- Multi-tenancy --
tenant_id: str | None = field(init=False)
```

In `__post_init__`, after the CORS block, add:

```python
# LLM provider
_set("llm_provider", os.getenv("LLM_PROVIDER", "ollama").lower())
_set("llm_model", os.getenv("LLM_MODEL", "mistral"))
_set("llm_api_key", os.getenv("LLM_API_KEY"))

# Multi-tenancy
_set("tenant_id", os.getenv("TENANT_ID"))
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_settings.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add src/d4bl/settings.py tests/test_settings.py
git commit -m "feat: add LLM provider and tenant_id settings"
```

---

### Task 2: Refactor LLM module to support multiple providers

**Files:**
- Modify: `src/d4bl/llm/ollama.py` → rename to `src/d4bl/llm/provider.py`
- Modify: `src/d4bl/llm/__init__.py`
- Create: `tests/test_llm_provider.py`

**Step 1: Write failing tests for the new provider-aware LLM factory**

Create `tests/test_llm_provider.py`:

```python
"""Tests for d4bl.llm.provider — multi-provider LLM factory."""
from __future__ import annotations

import os
from unittest.mock import patch, MagicMock

import pytest

from d4bl.settings import Settings


def _fresh_settings(**env_overrides: str | None) -> Settings:
    old = {}
    for key, val in env_overrides.items():
        old[key] = os.environ.get(key)
        if val is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = val
    try:
        return Settings()
    finally:
        for key, orig in old.items():
            if orig is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = orig


class TestBuildLlmModelString:
    """Test the model string builder for LiteLLM."""

    def test_ollama_provider(self) -> None:
        from d4bl.llm.provider import build_llm_model_string
        assert build_llm_model_string("ollama", "mistral") == "ollama/mistral"

    def test_gemini_provider(self) -> None:
        from d4bl.llm.provider import build_llm_model_string
        assert build_llm_model_string("gemini", "gemini-2.0-flash") == "gemini/gemini-2.0-flash"

    def test_openai_provider(self) -> None:
        from d4bl.llm.provider import build_llm_model_string
        assert build_llm_model_string("openai", "gpt-4o-mini") == "openai/gpt-4o-mini"

    def test_anthropic_provider(self) -> None:
        from d4bl.llm.provider import build_llm_model_string
        assert build_llm_model_string("anthropic", "claude-haiku-4-5-20251001") == "anthropic/claude-haiku-4-5-20251001"


class TestGetLlm:
    """Test the get_llm() factory function."""

    @patch("d4bl.llm.provider.get_settings")
    @patch("d4bl.llm.provider.LLM")
    def test_ollama_sets_api_base(self, mock_llm_cls, mock_get_settings) -> None:
        from d4bl.llm.provider import get_llm, reset_llm
        reset_llm()
        mock_settings = MagicMock()
        mock_settings.llm_provider = "ollama"
        mock_settings.llm_model = "mistral"
        mock_settings.llm_api_key = None
        mock_settings.ollama_base_url = "http://localhost:11434"
        mock_get_settings.return_value = mock_settings

        get_llm()

        mock_llm_cls.assert_called_once()
        call_kwargs = mock_llm_cls.call_args[1]
        assert call_kwargs["model"] == "ollama/mistral"
        assert call_kwargs["base_url"] == "http://localhost:11434"
        reset_llm()

    @patch("d4bl.llm.provider.get_settings")
    @patch("d4bl.llm.provider.LLM")
    def test_gemini_sets_api_key(self, mock_llm_cls, mock_get_settings) -> None:
        from d4bl.llm.provider import get_llm, reset_llm
        reset_llm()
        mock_settings = MagicMock()
        mock_settings.llm_provider = "gemini"
        mock_settings.llm_model = "gemini-2.0-flash"
        mock_settings.llm_api_key = "test-gemini-key"
        mock_settings.ollama_base_url = "http://localhost:11434"
        mock_get_settings.return_value = mock_settings

        get_llm()

        mock_llm_cls.assert_called_once()
        call_kwargs = mock_llm_cls.call_args[1]
        assert call_kwargs["model"] == "gemini/gemini-2.0-flash"
        assert call_kwargs["api_key"] == "test-gemini-key"
        assert "base_url" not in call_kwargs
        reset_llm()


class TestGetAvailableModels:
    """Test the available models endpoint helper."""

    @patch("d4bl.llm.provider.get_settings")
    def test_returns_configured_model(self, mock_get_settings) -> None:
        from d4bl.llm.provider import get_available_models
        mock_settings = MagicMock()
        mock_settings.llm_provider = "gemini"
        mock_settings.llm_model = "gemini-2.0-flash"
        mock_settings.llm_api_key = "key"
        mock_settings.ollama_base_url = "http://localhost:11434"
        mock_get_settings.return_value = mock_settings

        models = get_available_models()
        assert len(models) >= 1
        default_model = next(m for m in models if m["is_default"])
        assert default_model["provider"] == "gemini"
        assert default_model["model"] == "gemini-2.0-flash"
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_llm_provider.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'd4bl.llm.provider'`

**Step 3: Create the provider-aware LLM module**

Create `src/d4bl/llm/provider.py`:

```python
from __future__ import annotations

import logging
import os
import threading

from crewai import LLM

from d4bl.settings import get_settings

logger = logging.getLogger(__name__)

_llm: LLM | None = None
_lock = threading.Lock()


def build_llm_model_string(provider: str, model: str) -> str:
    """Build the LiteLLM model string: '{provider}/{model}'."""
    return f"{provider}/{model}"


def get_llm() -> LLM:
    """Get or create the LLM instance (lazy, thread-safe).

    Supports ollama (local), gemini, openai, anthropic, and any other
    provider that LiteLLM supports.
    """
    global _llm
    if _llm is not None:
        return _llm

    with _lock:
        if _llm is not None:
            return _llm

        settings = get_settings()
        provider = settings.llm_provider
        model_string = build_llm_model_string(provider, settings.llm_model)

        kwargs: dict = {
            "model": model_string,
            "temperature": 0.5,
            "timeout": 180.0,
            "num_retries": 5,
        }

        if provider == "ollama":
            os.environ["OLLAMA_API_BASE"] = settings.ollama_base_url
            kwargs["base_url"] = settings.ollama_base_url
        else:
            if settings.llm_api_key:
                kwargs["api_key"] = settings.llm_api_key

        _llm = LLM(**kwargs)
        logger.info(
            "Initialized LLM (provider=%s, model=%s)",
            provider,
            settings.llm_model,
        )
        return _llm


def reset_llm() -> None:
    """Reset the LLM instance (useful for testing or config changes)."""
    global _llm
    with _lock:
        _llm = None
    logger.info("Reset LLM instance")


def get_available_models() -> list[dict]:
    """Return available models based on current configuration.

    Returns a list of dicts with keys: provider, model, model_string, is_default.
    """
    settings = get_settings()
    current_model_string = build_llm_model_string(
        settings.llm_provider, settings.llm_model
    )
    models = [
        {
            "provider": settings.llm_provider,
            "model": settings.llm_model,
            "model_string": current_model_string,
            "is_default": True,
        }
    ]
    return models
```

**Step 4: Update `src/d4bl/llm/__init__.py`**

Read the current `__init__.py` first, then update it to re-export from the new module while keeping backward compatibility:

```python
from d4bl.llm.provider import get_llm, reset_llm, get_available_models, build_llm_model_string

# Backward compatibility aliases
get_ollama_llm = get_llm
reset_ollama_llm = reset_llm
```

**Step 5: Run tests to verify they pass**

Run: `pytest tests/test_llm_provider.py tests/test_ollama_client.py -v`
Expected: ALL PASS

**Step 6: Update all call sites from `get_ollama_llm` to `get_llm`**

Search for `get_ollama_llm` across the codebase and update imports:
- `src/d4bl/agents/crew.py:17` — change `from d4bl.llm import get_ollama_llm` to `from d4bl.llm import get_llm`
- Update all calls: `get_ollama_llm()` → `get_llm()`

**Step 7: Run all tests**

Run: `pytest tests/ -v`
Expected: ALL PASS

**Step 8: Commit**

```bash
git add src/d4bl/llm/ src/d4bl/agents/crew.py tests/test_llm_provider.py
git commit -m "feat: add multi-provider LLM support via LiteLLM"
```

---

### Task 3: Add `/api/models` endpoint and model param to research jobs

**Files:**
- Modify: `src/d4bl/app/api.py`
- Modify: `src/d4bl/app/schemas.py`
- Modify: `src/d4bl/services/research_runner.py`
- Create: `tests/test_api_models.py`

**Step 1: Write failing tests**

Create `tests/test_api_models.py`:

```python
"""Tests for the /api/models endpoint and model param on research."""
from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from d4bl.app.api import app


@pytest.fixture
def mock_db():
    """Mock the database dependency."""
    with patch("d4bl.app.api.get_db") as mock:
        session = MagicMock()
        mock.return_value = session
        yield session


@pytest.mark.asyncio
async def test_get_models_returns_list():
    """GET /api/models should return a list of available models."""
    mock_models = [
        {
            "provider": "gemini",
            "model": "gemini-2.0-flash",
            "model_string": "gemini/gemini-2.0-flash",
            "is_default": True,
        }
    ]
    with patch("d4bl.app.api.get_available_models", return_value=mock_models):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/models")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    assert data[0]["provider"] == "gemini"
    assert data[0]["is_default"] is True


def test_research_request_accepts_model():
    """ResearchRequest schema should accept an optional model field."""
    from d4bl.app.schemas import ResearchRequest
    req = ResearchRequest(query="test query", model="gemini/gemini-2.0-flash")
    assert req.model == "gemini/gemini-2.0-flash"


def test_research_request_model_defaults_none():
    """ResearchRequest.model should default to None."""
    from d4bl.app.schemas import ResearchRequest
    req = ResearchRequest(query="test query")
    assert req.model is None
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_api_models.py -v`
Expected: FAIL

**Step 3: Add model field to ResearchRequest schema**

In `src/d4bl/app/schemas.py`, add to `ResearchRequest`:

```python
class ResearchRequest(BaseModel):
    query: str
    summary_format: Literal["brief", "detailed", "comprehensive"] = "detailed"
    selected_agents: list[str] | None = None
    model: str | None = None  # LiteLLM model string, e.g. "gemini/gemini-2.0-flash"
```

**Step 4: Add `/api/models` endpoint to api.py**

In `src/d4bl/app/api.py`, add the import and endpoint:

```python
# Add to imports:
from d4bl.llm import get_available_models

# Add endpoint before the research endpoint:
@app.get("/api/models")
async def list_models():
    """Return available LLM models."""
    return get_available_models()
```

**Step 5: Pass model to research runner**

In `src/d4bl/app/api.py`, update `create_research` to pass the model:

```python
task = asyncio.create_task(run_research_job(
    job_id,
    request.query,
    request.summary_format,
    request.selected_agents,
    request.model,
))
```

Update `run_research_job` signature in `src/d4bl/services/research_runner.py`:

```python
async def run_research_job(
    job_id: str,
    query: str,
    summary_format: str,
    selected_agents: list[str] | None = None,
    model: str | None = None,
) -> None:
```

The `model` parameter will be used in Task 2's `get_llm()` in a future iteration — for now it's plumbed through but the crew uses the default configured LLM.

**Step 6: Run tests**

Run: `pytest tests/test_api_models.py tests/test_app_schemas.py -v`
Expected: ALL PASS

**Step 7: Commit**

```bash
git add src/d4bl/app/api.py src/d4bl/app/schemas.py src/d4bl/services/research_runner.py tests/test_api_models.py
git commit -m "feat: add /api/models endpoint and model param to research jobs"
```

---

### Task 4: Add multi-tenancy (tenant_id) to ResearchJob

**Files:**
- Modify: `src/d4bl/infra/database.py`
- Modify: `src/d4bl/app/api.py`
- Create: `tests/test_tenant_filter.py`

**Step 1: Write failing tests**

Create `tests/test_tenant_filter.py`:

```python
"""Tests for tenant_id filtering on ResearchJob."""
from __future__ import annotations

import pytest
from d4bl.infra.database import ResearchJob


def test_research_job_has_tenant_id_column():
    """ResearchJob model should have a tenant_id column."""
    assert hasattr(ResearchJob, "tenant_id")


def test_research_job_to_dict_includes_tenant_id():
    """to_dict() should include tenant_id."""
    job = ResearchJob(query="test", status="pending", tenant_id="org-test")
    d = job.to_dict()
    assert "tenant_id" in d
    assert d["tenant_id"] == "org-test"


def test_research_job_tenant_id_nullable():
    """tenant_id should be nullable (backward compatible)."""
    job = ResearchJob(query="test", status="pending")
    assert job.tenant_id is None
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_tenant_filter.py -v`
Expected: FAIL — `TypeError` or `AttributeError` for tenant_id

**Step 3: Add tenant_id column to ResearchJob**

In `src/d4bl/infra/database.py`, add to `ResearchJob`:

```python
class ResearchJob(Base):
    __tablename__ = "research_jobs"

    # ... existing columns ...
    tenant_id = Column(String(100), nullable=True, index=True)
```

Update `to_dict()` to include `tenant_id`:

```python
def to_dict(self):
    return {
        # ... existing fields ...
        "tenant_id": self.tenant_id,
    }
```

**Step 4: Update API to set and filter by tenant_id**

In `src/d4bl/app/api.py`, update `create_research`:

```python
job = ResearchJob(
    query=request.query,
    summary_format=request.summary_format,
    status="pending",
    progress="Job created, waiting to start...",
    tenant_id=_settings.tenant_id,
)
```

Update `get_job_history` to filter by tenant_id when configured:

```python
if _settings.tenant_id:
    filters.append(ResearchJob.tenant_id == _settings.tenant_id)
```

**Step 5: Run tests**

Run: `pytest tests/test_tenant_filter.py -v`
Expected: ALL PASS

**Step 6: Commit**

```bash
git add src/d4bl/infra/database.py src/d4bl/app/api.py tests/test_tenant_filter.py
git commit -m "feat: add tenant_id to ResearchJob for multi-tenancy"
```

---

### Task 5: Add LLM selector to frontend ResearchForm

**Files:**
- Modify: `ui-nextjs/components/ResearchForm.tsx`
- Modify: `ui-nextjs/app/page.tsx`

**Step 1: Add model fetching and selector to ResearchForm**

Update `ui-nextjs/components/ResearchForm.tsx`:

Add `model` to the `onSubmit` callback signature:

```typescript
interface ResearchFormProps {
  onSubmit: (query: string, summaryFormat: string, selectedAgents?: string[], model?: string) => void;
  disabled?: boolean;
}

interface ModelOption {
  provider: string;
  model: string;
  model_string: string;
  is_default: boolean;
}
```

Add state and fetch logic inside the component:

```typescript
const [models, setModels] = useState<ModelOption[]>([]);
const [selectedModel, setSelectedModel] = useState<string>('');

useEffect(() => {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
  fetch(`${apiUrl}/api/models`)
    .then(res => res.json())
    .then((data: ModelOption[]) => {
      setModels(data);
      const defaultModel = data.find(m => m.is_default);
      if (defaultModel) setSelectedModel(defaultModel.model_string);
    })
    .catch(err => console.error('Failed to fetch models:', err));
}, []);
```

Add a dropdown after the Summary Format select:

```tsx
{models.length > 0 && (
  <div>
    <label htmlFor="model" className="block text-sm font-medium text-gray-300 mb-2">
      LLM Model
    </label>
    <select
      id="model"
      value={selectedModel}
      onChange={(e) => setSelectedModel(e.target.value)}
      className="w-full px-4 py-3 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-black focus:border-black text-black bg-white disabled:bg-gray-50 disabled:text-gray-600"
      disabled={disabled}
    >
      {models.map((m) => (
        <option key={m.model_string} value={m.model_string}>
          {m.provider}/{m.model}{m.is_default ? ' (default)' : ''}
        </option>
      ))}
    </select>
  </div>
)}
```

Update `handleSubmit` to pass the model:

```typescript
onSubmit(query.trim(), summaryFormat, selectedAgents.length > 0 ? selectedAgents : undefined, selectedModel || undefined);
```

**Step 2: Update page.tsx to pass model in the API request**

In `ui-nextjs/app/page.tsx`, update the research submit handler to include the `model` field in the POST body to `/api/research`.

**Step 3: Verify manually**

Run: `cd ui-nextjs && npm run build`
Expected: Build succeeds with no type errors

**Step 4: Commit**

```bash
git add ui-nextjs/components/ResearchForm.tsx ui-nextjs/app/page.tsx
git commit -m "feat: add LLM model selector to research form"
```

---

### Task 6: Create GitHub Actions PR verification workflow

**Files:**
- Create: `.github/workflows/pr-checks.yml`

**Step 1: Create the workflow file**

```yaml
name: PR Checks

on:
  pull_request:
    branches: [main, 'epic/**']

jobs:
  python-checks:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
          cache: 'pip'
      - run: pip install -r requirements.txt
      - run: pip install ruff pytest pytest-asyncio httpx
      - name: Lint
        run: ruff check src/
      - name: Tests
        run: pytest tests/ -v --tb=short

  frontend-checks:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'
          cache-dependency-path: ui-nextjs/package-lock.json
      - name: Install dependencies
        run: cd ui-nextjs && npm ci
      - name: Lint
        run: cd ui-nextjs && npm run lint
      - name: Type check
        run: cd ui-nextjs && npx tsc --noEmit
      - name: Build
        run: cd ui-nextjs && npm run build

  docker-build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Build backend image
        run: docker build -t d4bl-api:test .
      - name: Build frontend image
        run: docker build -t d4bl-frontend:test ./ui-nextjs
```

**Step 2: Commit**

```bash
mkdir -p .github/workflows
git add .github/workflows/pr-checks.yml
git commit -m "ci: add PR verification workflow (lint, test, build)"
```

---

### Task 7: Create Fly.io configuration files

**Files:**
- Create: `fly.api.toml`
- Create: `fly.frontend.toml`
- Create: `fly.crawl4ai.toml`

**Step 1: Create fly.api.toml**

```toml
app = "d4bl-api"
primary_region = "iad"

[build]
  dockerfile = "Dockerfile"

[http_service]
  internal_port = 8000
  force_https = true
  auto_stop_machines = "stop"
  auto_start_machines = true
  min_machines_running = 0

[[vm]]
  size = "shared-cpu-1x"
  memory = "256mb"
```

**Step 2: Create fly.frontend.toml**

```toml
app = "d4bl-frontend"
primary_region = "iad"

[build]
  dockerfile = "ui-nextjs/Dockerfile"

[http_service]
  internal_port = 3000
  force_https = true
  auto_stop_machines = "stop"
  auto_start_machines = true
  min_machines_running = 0

[[vm]]
  size = "shared-cpu-1x"
  memory = "256mb"
```

**Step 3: Create fly.crawl4ai.toml**

```toml
app = "d4bl-crawl4ai"
primary_region = "iad"

[build]
  image = "unclecode/crawl4ai:latest"

[http_service]
  internal_port = 11235
  force_https = true
  auto_stop_machines = "stop"
  auto_start_machines = true
  min_machines_running = 0

[[vm]]
  size = "shared-cpu-1x"
  memory = "512mb"
```

**Step 4: Commit**

```bash
git add fly.api.toml fly.frontend.toml fly.crawl4ai.toml
git commit -m "ci: add Fly.io configuration for staging apps"
```

---

### Task 8: Create GitHub Actions deploy-to-staging workflow

**Files:**
- Create: `.github/workflows/deploy-staging.yml`

**Step 1: Create the deploy workflow**

```yaml
name: Deploy to Staging

on:
  push:
    branches: [main, 'epic/**']

jobs:
  deploy-api:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: superfly/flyctl-actions/setup-flyctl@master
      - run: flyctl deploy --config fly.api.toml --remote-only
        env:
          FLY_API_TOKEN: ${{ secrets.FLY_API_TOKEN }}

  deploy-frontend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: superfly/flyctl-actions/setup-flyctl@master
      - run: flyctl deploy --config fly.frontend.toml --remote-only
        env:
          FLY_API_TOKEN: ${{ secrets.FLY_API_TOKEN }}

  deploy-crawl4ai:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: superfly/flyctl-actions/setup-flyctl@master
      - run: flyctl deploy --config fly.crawl4ai.toml --remote-only
        env:
          FLY_API_TOKEN: ${{ secrets.FLY_API_TOKEN }}

  health-check:
    runs-on: ubuntu-latest
    needs: [deploy-api, deploy-frontend]
    steps:
      - name: Wait for deployment
        run: sleep 30
      - name: Check API health
        run: curl --fail --retry 5 --retry-delay 10 https://d4bl-api.fly.dev/api/health
      - name: Check frontend
        run: curl --fail --retry 5 --retry-delay 10 https://d4bl-frontend.fly.dev/
```

**Step 2: Commit**

```bash
git add .github/workflows/deploy-staging.yml
git commit -m "ci: add deploy-to-staging workflow for Fly.io"
```

---

### Task 9: Create stakeholder distribution package

**Files:**
- Create: `docker-compose.stakeholder.yml`
- Create: `.env.stakeholder.example`
- Create: `STAKEHOLDER_README.md`

**Step 1: Create docker-compose.stakeholder.yml**

```yaml
# Simplified Docker Compose for stakeholder local deployment.
# Runs frontend + backend locally with Ollama on host.
# Pushes data to shared Supabase Cloud database.
#
# Usage:
#   cp .env.stakeholder.example .env.stakeholder
#   # Edit .env.stakeholder with your tenant ID
#   docker compose -f docker-compose.stakeholder.yml --env-file .env.stakeholder up --build

services:
  d4bl-api:
    build: .
    container_name: d4bl-api
    ports:
      - "8000:8000"
    environment:
      - PYTHONPATH=/app/src
      - LLM_PROVIDER=ollama
      - LLM_MODEL=${LLM_MODEL:-mistral}
      - OLLAMA_BASE_URL=${OLLAMA_BASE_URL:-http://host.docker.internal:11434}
      - POSTGRES_HOST=${POSTGRES_HOST}
      - POSTGRES_PORT=${POSTGRES_PORT:-5432}
      - POSTGRES_USER=${POSTGRES_USER}
      - POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
      - POSTGRES_DB=${POSTGRES_DB:-postgres}
      - TENANT_ID=${TENANT_ID}
      - CRAWL_PROVIDER=${CRAWL_PROVIDER:-crawl4ai}
      - CRAWL4AI_BASE_URL=http://crawl4ai:11235
      - EMBEDDINGS_OLLAMA_BASE_URL=${OLLAMA_BASE_URL:-http://host.docker.internal:11434}
      - EMBEDDINGS_OLLAMA_MODEL_NAME=mxbai-embed-large
      - CORS_ALLOWED_ORIGINS=http://localhost:3000
    depends_on:
      - crawl4ai
    restart: unless-stopped
    networks:
      - stakeholder
    extra_hosts:
      - "host.docker.internal:host-gateway"

  d4bl-frontend:
    build:
      context: ./ui-nextjs
      dockerfile: Dockerfile
      args:
        NEXT_PUBLIC_API_URL: http://localhost:8000
    container_name: d4bl-frontend
    ports:
      - "3000:3000"
    environment:
      - NODE_ENV=production
      - NEXT_PUBLIC_API_URL=http://localhost:8000
      - API_INTERNAL_URL=http://d4bl-api:8000
    depends_on:
      - d4bl-api
    restart: unless-stopped
    networks:
      - stakeholder

  crawl4ai:
    image: unclecode/crawl4ai:latest
    container_name: crawl4ai
    restart: unless-stopped
    networks:
      - stakeholder
    ports:
      - "3100:11235"
    healthcheck:
      test: ["CMD", "wget", "--no-verbose", "--tries=1", "--spider", "http://localhost:11235/health"]
      interval: 20s
      timeout: 5s
      retries: 5
      start_period: 20s

networks:
  stakeholder:
    driver: bridge
```

**Step 2: Create .env.stakeholder.example**

```bash
# === REQUIRED ===
# Your organization/tenant identifier (provided by D4BL)
TENANT_ID=

# Shared database credentials (provided by D4BL)
POSTGRES_HOST=
POSTGRES_PORT=5432
POSTGRES_USER=
POSTGRES_PASSWORD=
POSTGRES_DB=postgres

# === OPTIONAL ===
# Ollama settings (defaults work if Ollama is running locally)
OLLAMA_BASE_URL=http://host.docker.internal:11434
LLM_MODEL=mistral

# Crawl provider
CRAWL_PROVIDER=crawl4ai
```

**Step 3: Create STAKEHOLDER_README.md**

```markdown
# D4BL AI Agent — Local Setup Guide

This guide helps you run the D4BL Research and Analysis Tool on your local machine.
Your research data is stored in a shared cloud database so all network members can
benefit from each other's work.

## Prerequisites

1. **Docker Desktop** — [Install Docker](https://docs.docker.com/get-docker/)
2. **Ollama** — [Install Ollama](https://ollama.com/download)

## Setup

### 1. Install and start Ollama

```bash
# After installing Ollama, pull the required models:
ollama pull mistral
ollama pull mxbai-embed-large
```

Make sure Ollama is running (it starts automatically on most systems).

### 2. Configure your environment

```bash
cp .env.stakeholder.example .env.stakeholder
```

Edit `.env.stakeholder` and fill in:
- `TENANT_ID` — your organization identifier (provided by D4BL)
- `POSTGRES_HOST` — shared database host (provided by D4BL)
- `POSTGRES_USER` — database username (provided by D4BL)
- `POSTGRES_PASSWORD` — database password (provided by D4BL)

### 3. Start the application

```bash
docker compose -f docker-compose.stakeholder.yml --env-file .env.stakeholder up --build
```

### 4. Open the app

Visit [http://localhost:3000](http://localhost:3000) in your browser.

## Stopping

```bash
docker compose -f docker-compose.stakeholder.yml down
```

## Troubleshooting

- **"Cannot connect to Ollama"** — Make sure Ollama is running: `ollama serve`
- **"Database connection failed"** — Check your `.env.stakeholder` credentials
- **Slow first run** — Docker needs to download images (~2-3 GB). Subsequent runs are fast.
```

**Step 4: Commit**

```bash
git add docker-compose.stakeholder.yml .env.stakeholder.example STAKEHOLDER_README.md
git commit -m "feat: add stakeholder distribution package with local Ollama + shared DB"
```

---

### Task 10: Add ruff config and lint fixes

**Files:**
- Create: `ruff.toml` (if not present)
- May modify various source files for lint compliance

**Step 1: Create ruff.toml if needed**

Check if `ruff.toml` or `[tool.ruff]` in `pyproject.toml` exists. If not, create `ruff.toml`:

```toml
line-length = 100
target-version = "py311"

[lint]
select = ["E", "F", "W", "I"]
ignore = ["E501"]  # line length handled by formatter
```

**Step 2: Run ruff and fix any issues**

Run: `ruff check src/ --fix`
Run: `ruff check tests/ --fix`

**Step 3: Run pytest to verify nothing broke**

Run: `pytest tests/ -v`
Expected: ALL PASS

**Step 4: Commit**

```bash
git add ruff.toml src/ tests/
git commit -m "chore: add ruff config and fix lint issues for CI"
```

---

## Task Dependencies

```
Task 1 (Settings) ──→ Task 2 (LLM provider) ──→ Task 3 (API endpoint)
                                                         │
Task 4 (Multi-tenancy) ─────────────────────────────────┘
                                                         │
Task 5 (Frontend LLM selector) ─────────────────────────┘
                                                         │
Task 6 (PR checks CI) ──→ Task 10 (Ruff/lint) ─────────┘
                                                         │
Task 7 (Fly.io config) ──→ Task 8 (Deploy CI) ─────────┘
                                                         │
Task 9 (Stakeholder package) ───────────────────────────┘
```

Tasks 1, 4, 6, 7, 9 can start in parallel. Tasks 2, 3, 5 are sequential. Task 10 should run after Task 6.
