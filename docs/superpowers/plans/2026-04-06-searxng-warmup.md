# SearXNG Pre-Warm Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Pre-warm SearXNG on Fly.io before crew kickoff so the first search succeeds, and show a phase-aware warmup state in the frontend.

**Architecture:** Add an async `httpx` health check ping to `run_research_job` before crew kickoff. Introduce a `phase` field on all WebSocket progress messages so the frontend can distinguish warmup/init/research/evaluation stages. ProgressCard renders an amber pulsing indicator during warmup.

**Tech Stack:** Python (httpx, asyncio), TypeScript (React, Next.js), Tailwind CSS

---

## File Map

| Action | File | Responsibility |
|--------|------|---------------|
| Modify | `src/d4bl/services/research_runner.py` | Warmup ping + phase on all progress messages |
| Modify | `ui-nextjs/lib/types.ts` | Add `phase?` to `WsProgressMessage` |
| Modify | `ui-nextjs/app/page.tsx` | Track phase state, pass to ProgressCard, reset on complete/error |
| Modify | `ui-nextjs/components/ProgressCard.tsx` | Amber warmup visual state, accept phase prop |
| Create | `tests/test_warmup.py` | Backend tests for warmup + phase behavior |

---

### Task 1: Add `phase` to WebSocket progress type

**Files:**
- Modify: `ui-nextjs/lib/types.ts:58`

- [ ] **Step 1: Add `phase` to `WsProgressMessage`**

In `ui-nextjs/lib/types.ts`, change line 58 from:

```typescript
export interface WsProgressMessage { type: 'progress'; message: string; logs?: string[] }
```

to:

```typescript
export interface WsProgressMessage { type: 'progress'; message: string; phase?: string; logs?: string[] }
```

- [ ] **Step 2: Commit**

```bash
git add ui-nextjs/lib/types.ts
git commit -m "feat(types): add phase field to WsProgressMessage (#173)"
```

---

### Task 2: Write backend tests for warmup and phase

**Files:**
- Create: `tests/test_warmup.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_warmup.py`:

```python
"""Tests for SearXNG warmup and phase-aware progress messages."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest


@pytest.fixture
def mock_websocket_updates():
    """Capture all WebSocket updates sent during a job."""
    updates = []
    original_send = None

    async def capture_update(job_id, data):
        updates.append(data)

    return updates, capture_update


@pytest.fixture
def mock_settings_searxng():
    """Settings with SearXNG configured."""
    settings = MagicMock()
    settings.searxng_base_url = "http://searxng:8080"
    settings.search_provider = "searxng"
    return settings


@pytest.fixture
def mock_settings_no_searxng():
    """Settings with SearXNG NOT configured (different provider)."""
    settings = MagicMock()
    settings.searxng_base_url = "http://searxng:8080"
    settings.search_provider = "google"
    return settings


class TestWarmupPing:
    """Test the SearXNG warmup ping behavior."""

    @pytest.mark.asyncio
    async def test_warmup_pings_healthz(self, mock_settings_searxng):
        """Warmup sends GET to SEARXNG_BASE_URL/healthz."""
        from d4bl.services.research_runner import warmup_searxng

        with patch("d4bl.services.research_runner.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=MagicMock(status_code=200))
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await warmup_searxng(mock_settings_searxng)

            mock_client.get.assert_called_once_with(
                "http://searxng:8080/healthz", timeout=15.0
            )
            assert result is True

    @pytest.mark.asyncio
    async def test_warmup_skipped_when_not_searxng(self, mock_settings_no_searxng):
        """Warmup is skipped when search_provider != 'searxng'."""
        from d4bl.services.research_runner import warmup_searxng

        with patch("d4bl.services.research_runner.httpx.AsyncClient") as MockClient:
            result = await warmup_searxng(mock_settings_no_searxng)

            MockClient.assert_not_called()
            assert result is False

    @pytest.mark.asyncio
    async def test_warmup_skipped_when_url_empty(self):
        """Warmup is skipped when searxng_base_url is empty."""
        from d4bl.services.research_runner import warmup_searxng

        settings = MagicMock()
        settings.searxng_base_url = ""
        settings.search_provider = "searxng"

        with patch("d4bl.services.research_runner.httpx.AsyncClient") as MockClient:
            result = await warmup_searxng(settings)

            MockClient.assert_not_called()
            assert result is False

    @pytest.mark.asyncio
    async def test_warmup_handles_timeout(self, mock_settings_searxng):
        """Warmup returns False on timeout but does not raise."""
        from d4bl.services.research_runner import warmup_searxng

        with patch("d4bl.services.research_runner.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await warmup_searxng(mock_settings_searxng)

            assert result is False

    @pytest.mark.asyncio
    async def test_warmup_handles_connection_error(self, mock_settings_searxng):
        """Warmup returns False on connection error but does not raise."""
        from d4bl.services.research_runner import warmup_searxng

        with patch("d4bl.services.research_runner.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(
                side_effect=httpx.ConnectError("connection refused")
            )
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await warmup_searxng(mock_settings_searxng)

            assert result is False


class TestPhaseInProgress:
    """Test that progress messages include the phase field."""

    @pytest.mark.asyncio
    async def test_notify_progress_includes_phase(self):
        """notify_progress sends phase in WebSocket update."""
        captured = []

        async def fake_send(job_id, data):
            captured.append(data)

        mock_db = AsyncMock()

        async def fake_get_db():
            yield mock_db

        with patch(
            "d4bl.services.research_runner.send_websocket_update", side_effect=fake_send
        ), patch(
            "d4bl.services.research_runner.update_job_status", new_callable=AsyncMock
        ), patch(
            "d4bl.services.research_runner.get_db", fake_get_db
        ):
            from d4bl.services.research_runner import _make_notify_progress

            notify = _make_notify_progress("test-job-id", None)
            await notify("Warming up search services...", phase="warmup")

            assert len(captured) == 1
            msg = captured[0]
            assert msg["phase"] == "warmup"
            assert msg["message"] == "Warming up search services..."
            assert msg["type"] == "progress"

    @pytest.mark.asyncio
    async def test_notify_progress_omits_phase_when_none(self):
        """notify_progress does not include phase key when phase is None."""
        captured = []

        async def fake_send(job_id, data):
            captured.append(data)

        mock_db = AsyncMock()

        async def fake_get_db():
            yield mock_db

        with patch(
            "d4bl.services.research_runner.send_websocket_update", side_effect=fake_send
        ), patch(
            "d4bl.services.research_runner.update_job_status", new_callable=AsyncMock
        ), patch(
            "d4bl.services.research_runner.get_db", fake_get_db
        ):
            from d4bl.services.research_runner import _make_notify_progress

            notify = _make_notify_progress("test-job-id", None)
            await notify("Some progress message")

            assert len(captured) == 1
            assert "phase" not in captured[0]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/william-meroxa/Development/d4bl_ai_agent && python -m pytest tests/test_warmup.py -v`

Expected: FAIL — `warmup_searxng` and `_make_notify_progress` do not exist yet.

- [ ] **Step 3: Commit failing tests**

```bash
git add tests/test_warmup.py
git commit -m "test: add failing tests for SearXNG warmup and phase progress (#173)"
```

---

### Task 3: Implement backend warmup and phase-aware progress

**Files:**
- Modify: `src/d4bl/services/research_runner.py`

- [ ] **Step 1: Add httpx import and warmup_searxng function**

At the top of `research_runner.py`, add `httpx` to imports (after the existing import block around line 15):

```python
import httpx
```

After the `validate_research_relevance` function (after line 88), add:

```python
async def warmup_searxng(settings) -> bool:
    """Ping SearXNG /healthz to wake Fly.io machine. Returns True if healthy."""
    if settings.search_provider != "searxng" or not settings.searxng_base_url:
        return False

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{settings.searxng_base_url}/healthz", timeout=15.0
            )
            logger.info("SearXNG warmup: %s (status %d)", settings.searxng_base_url, resp.status_code)
            return True
    except (httpx.TimeoutException, httpx.ConnectError, httpx.HTTPError) as exc:
        logger.warning("SearXNG warmup failed (will proceed anyway): %s", exc)
        return False
```

- [ ] **Step 2: Extract `_make_notify_progress` factory and add phase support**

The existing `notify_progress` is a closure inside `run_research_job`. Extract a factory so it can be tested and accepts a `phase` parameter.

After the `warmup_searxng` function, add:

```python
def _make_notify_progress(job_id: str, trace_id_hex: str | None):
    """Create a notify_progress coroutine for a given job. Testable factory."""

    async def notify_progress(progress_msg: str, phase: str | None = None) -> None:
        """Update DB status and push progress via WebSocket in one call."""
        async for db in get_db():
            try:
                await update_job_status(db, job_id, "running", progress=progress_msg)
                break
            except Exception as update_err:
                print(f"Error updating job status: {update_err}")
                break

        ws_payload = {
            "type": "progress",
            "job_id": job_id,
            "status": "running",
            "message": progress_msg,
            "progress": progress_msg,
            "trace_id": trace_id_hex,
        }
        if phase is not None:
            ws_payload["phase"] = phase
        await send_websocket_update(job_id, ws_payload)

    return notify_progress
```

Note: The payload includes both `"message"` (matches the frontend `WsProgressMessage` type) and `"progress"` (used by the polling fallback path).

- [ ] **Step 3: Update `run_research_job` to use the factory and add warmup**

Three changes inside `run_research_job`:

**3a. Keep `set_status` closure as-is** (lines 201-229). It's used for final status updates — do not modify it.

**3b. Delete the old `notify_progress` closure** (lines 231-244) and replace with:

```python
            notify_progress = _make_notify_progress(job_id, trace_id_hex)
```

**3c. Replace the init sequence** (lines 250-258, starting at `await notify_progress("Initializing research crew...")`) with:

```python
            # -- Warmup SearXNG (wakes Fly.io machine) --
            from d4bl.settings import get_settings

            settings = get_settings()
            if settings.search_provider == "searxng" and settings.searxng_base_url:
                await notify_progress("Warming up search services...", phase="warmup")
                await warmup_searxng(settings)

            await notify_progress("Initializing research crew...", phase="init")

            inputs = {
                "query": query,
                "summary_format": summary_format,
                "current_year": str(datetime.now().year),
            }

            await notify_progress("Starting research task...", phase="research")
```

- [ ] **Step 4: Tag remaining progress messages with phases**

Find the remaining `notify_progress` calls in the function and add phases:

1. Line ~344 (after crew execution): change `await notify_progress("Research completed, processing results...")` to:
   ```python
   await notify_progress("Research completed, processing results...", phase="evaluation")
   ```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /Users/william-meroxa/Development/d4bl_ai_agent && python -m pytest tests/test_warmup.py -v`

Expected: All 7 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add src/d4bl/services/research_runner.py
git commit -m "feat(backend): add SearXNG warmup ping and phase-aware progress (#173)"
```

---

### Task 4: Frontend phase tracking in page.tsx

**Files:**
- Modify: `ui-nextjs/app/page.tsx`

- [ ] **Step 1: Add phase state**

After the existing `useState` declarations (around line 28), add:

```typescript
const [phase, setPhase] = useState<string | null>(null);
```

- [ ] **Step 2: Extract phase from progress messages**

In the WebSocket message handler's `'progress'` case (line 53-55), change:

```typescript
          case 'progress':
            updateLogs(data);
            setProgress(data.message || 'Processing...');
            break;
```

to:

```typescript
          case 'progress':
            updateLogs(data);
            setProgress(data.message || 'Processing...');
            setPhase(data.phase ?? null);
            break;
```

- [ ] **Step 3: Reset phase on complete and error**

In the `'complete'` case (line 56-60), add `setPhase(null)` after `setResults`:

```typescript
          case 'complete':
            updateLogs(data);
            setProgress('Research completed!');
            setResults(data.result);
            setPhase(null);
            setJobId(null);
            break;
```

In the `'error'` case (line 61-64), add `setPhase(null)` after `setError`:

```typescript
          case 'error':
            updateLogs(data);
            setError(data.error || data.message || 'An error occurred during research');
            setPhase(null);
            setJobId(null);
            break;
```

- [ ] **Step 4: Pass phase to ProgressCard**

In the JSX (around line 253), change:

```tsx
                  <ProgressCard
                    progress={progress}
                    isConnected={isConnected}
                  />
```

to:

```tsx
                  <ProgressCard
                    progress={progress}
                    isConnected={isConnected}
                    phase={phase}
                  />
```

- [ ] **Step 5: Commit**

```bash
git add ui-nextjs/app/page.tsx
git commit -m "feat(frontend): track phase state from WebSocket progress messages (#173)"
```

---

### Task 5: ProgressCard warmup visual state

**Files:**
- Modify: `ui-nextjs/components/ProgressCard.tsx`

- [ ] **Step 1: Update ProgressCard to accept phase and render warmup state**

Replace the entire contents of `ui-nextjs/components/ProgressCard.tsx` with:

```tsx
'use client';

interface ProgressCardProps {
  progress: string;
  isConnected: boolean;
  phase?: string | null;
}

export default function ProgressCard({ progress, isConnected, phase }: ProgressCardProps) {
  const isWarmup = phase === 'warmup';

  // Dot: amber pulsing during warmup, green when connected, red when disconnected
  const dotClass = isWarmup
    ? 'bg-amber-500 animate-pulse'
    : isConnected
      ? 'bg-[#00ff32]'
      : 'bg-red-500';

  const statusLabel = isWarmup
    ? 'Warming up...'
    : isConnected
      ? 'Connected'
      : 'Disconnected';

  // Progress bar: amber during warmup, green otherwise
  const barClass = isWarmup
    ? 'bg-amber-500/50 h-2 rounded-full w-full animate-pulse'
    : 'bg-[#00ff32]/50 h-2 rounded-full w-full animate-pulse';

  return (
    <div className="bg-[#333333] border border-[#404040] rounded-lg p-8 shadow-sm">
      <h2 className="text-2xl font-bold text-white mb-6">
        Research Progress
      </h2>
      <div className="space-y-4">
        <div className="w-full bg-[#1a1a1a] rounded-full h-2">
          <div className={barClass} />
        </div>
        <div className="flex items-center justify-between">
          <p className="text-gray-200 font-medium">{progress || 'Processing...'}</p>
          <div className="flex items-center space-x-2">
            <div className={`w-2 h-2 rounded-full ${dotClass}`} />
            <span className="text-sm text-gray-300 font-medium">
              {statusLabel}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add ui-nextjs/components/ProgressCard.tsx
git commit -m "feat(frontend): add amber warmup state to ProgressCard (#173)"
```

---

### Task 6: Build verification

- [ ] **Step 1: Run backend tests**

Run: `cd /Users/william-meroxa/Development/d4bl_ai_agent && python -m pytest tests/test_warmup.py -v`

Expected: All tests PASS.

- [ ] **Step 2: Run frontend lint**

Run: `cd /Users/william-meroxa/Development/d4bl_ai_agent/ui-nextjs && npm run lint`

Expected: No errors.

- [ ] **Step 3: Run frontend build**

Run: `cd /Users/william-meroxa/Development/d4bl_ai_agent/ui-nextjs && npm run build`

Expected: Build succeeds.

- [ ] **Step 4: Fix any issues and commit**

If any step fails, fix the issue and commit the fix.
