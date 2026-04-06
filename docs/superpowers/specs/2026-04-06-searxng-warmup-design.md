# SearXNG Pre-Warm on Job Start — Design Spec

**Issue:** #173
**Date:** 2026-04-06

## Problem

SearXNG on Fly.io auto-stops when idle. The first research job after idle gets empty search results because the machine takes 3-10s to wake up. The agent's search tool times out or returns errors, and the agent falls back to LLM-only knowledge — producing reports without web sources.

Impact: `source_urls: []`, hallucination eval score drops, report quality degrades.

## Solution

Inline warmup in `run_research_job` with phase-aware progress messages.

## Design

### Phase System

All progress WebSocket messages include a `phase` field so the frontend can track the current job stage:

```
warmup → init → research → evaluation → complete
```

### Backend: `research_runner.py`

1. Add optional `phase` parameter to `notify_progress`.
2. After the OpenTelemetry span starts, send `notify_progress("Warming up search services...", phase="warmup")`.
3. Use `httpx.AsyncClient` to `GET {SEARXNG_BASE_URL}/healthz` with a 15s timeout.
4. If it succeeds or fails, log the result and proceed — no retry.
5. Continue with `notify_progress("Initializing research crew...", phase="init")`.
6. Tag all subsequent progress messages with their phase: `init`, `research`, `evaluation`.

Access `SEARXNG_BASE_URL` from settings. If empty or search provider isn't SearXNG, skip warmup entirely.

The ping is `await`ed (not fire-and-forget) so it completes before crew kickoff.

### Frontend: `types.ts`

Add `phase?: string` to `WsProgressMessage`. Optional for backwards compatibility.

### Frontend: `page.tsx`

- New state: `const [phase, setPhase] = useState<string | null>(null)`
- In the `'progress'` WebSocket case, extract `data.phase` and call `setPhase()`
- Pass `phase` to `ProgressCard`
- Reset `phase` to `null` on job complete/error

### Frontend: `ProgressCard.tsx`

Accept new `phase` prop. Three visual states for the connection indicator:

| State | Dot color | Label |
|-------|-----------|-------|
| `phase === "warmup"` | Amber pulsing (`bg-amber-500 animate-pulse`) | "Warming up..." |
| `isConnected` | Green (`bg-[#00ff32]`) | "Connected" |
| disconnected | Red (`bg-red-500`) | "Disconnected" |

Progress bar: amber pulse during warmup, green pulse otherwise. Transitions automatically when phase advances past `"warmup"`.

Matches existing design system: dark theme (`#333333` cards), neon green (`#00ff32`) accent, `animate-pulse` pattern.

## Error Handling

- **Warmup failure:** Log warning, proceed. Agents already handle search failures gracefully.
- **SearXNG not configured:** Skip warmup if `SEARXNG_BASE_URL` is empty or search provider isn't SearXNG.
- **WebSocket not connected:** Fallback polling doesn't surface `phase` — acceptable since warmup is a brief transient state and polling is the degraded path.

## Files to Change

- `src/d4bl/services/research_runner.py` — warmup ping + phase on all progress messages
- `ui-nextjs/lib/types.ts` — add `phase?` to `WsProgressMessage`
- `ui-nextjs/app/page.tsx` — track phase state, pass to ProgressCard
- `ui-nextjs/components/ProgressCard.tsx` — amber warmup visual state

## Test Plan

- [ ] Job start sends "Warming up search services..." progress message with `phase: "warmup"`
- [ ] SearXNG `/healthz` is pinged before crew kickoff
- [ ] ProgressCard shows amber warmup state during warmup phase
- [ ] After warmup, transitions to normal green progress state
- [ ] All progress messages include a `phase` field
- [ ] If SearXNG is down, job still completes (graceful degradation)
- [ ] If SearXNG is not configured, warmup is skipped
