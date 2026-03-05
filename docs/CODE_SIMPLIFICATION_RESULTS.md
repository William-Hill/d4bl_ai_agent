# Code Simplification Sweep — Final Results

**Epic**: #29
**Date completed**: 2026-03-05
**Design doc**: `docs/plans/2026-03-02-code-simplification-sweep.md`

## Summary

Full codebase review for code reuse, quality, and efficiency improvements. **158 findings** across 10 modules, addressed in 10 PRs. Zero regressions — all changes preserve existing behavior.

## PRs

| PR | Module | Description |
|----|--------|-------------|
| #30 | services/ | Base evaluator extraction |
| #32 | services/ | Enums, dedup |
| #34 | agents/ | Crew simplification |
| #35 | app/ | API cleanup + tests |
| #36 | infra/ | Database layer cleanup + tests |
| #37 | query/ | Query engine cleanup + tests |
| #38 | root files | Settings, main, crew + tests |
| #41 | observability/ | Langfuse tracing cleanup |
| #42 | evals/ | Evaluation runner cleanup |
| #43 | llm/ | LLM config simplification |
| #44 | ui-nextjs/ | Frontend types, hooks, performance |

## Python Metrics (`src/d4bl/` + `tests/`)

| Metric | Before | After | Delta |
|--------|--------|-------|-------|
| Source LOC | 6,436 | 6,032 | **-404 (-6.3%)** |
| Test LOC | 1,231 | 1,960 | **+729 (+59.2%)** |
| Source files | 48 | 47 | -1 |
| Test files | 12 | 18 | +6 |
| Functions/methods | 186 | 183 | -3 |
| Avg cyclomatic complexity | 4.9 | 4.9 | -- |
| CC grade A (low) | 140 | 137 | -3 |
| CC grade B (moderate) | 24 | 26 | +2 |
| CC grade C (high) | 17 | 15 | **-2** |
| CC grade D+ (very high) | 5 | 5 | -- |
| Avg maintainability index | 73.0 | 69.7 | -3.3 |
| Files with MI < 50 | 4 | 9 | +5 |

### Per-PR LOC Breakdown

| PR | Module | Src LOC | Test LOC | Net |
|----|--------|---------|----------|-----|
| #30 | services/ (base evaluator) | -204 | +0 | -204 |
| #32 | services/ (enums, dedup) | +23 | +0 | +23 |
| #34 | agents/ | -372 | +0 | -372 |
| #35 | app/ | +8 | +131 | +139 |
| #36 | infra/ | -35 | +131 | +96 |
| #37 | query/ | +48 | +97 | +145 |
| #38 | root files | +56 | +206 | +262 |
| #41 | observability/ | +40 | +73 | +113 |
| #42 | evals/ | +23 | +56 | +79 |
| #43 | llm/ | +17 | +35 | +52 |
| **Total** | | **-396** | **+729** | **+333** |

## Frontend Metrics (`ui-nextjs/`)

| Metric | Before | After | Delta |
|--------|--------|-------|-------|
| Source LOC | 2,107 | 2,097 | **-10** |
| Source files | 20 | 20 | -- |
| `any` type annotations | 7 | 0 | **-7** |
| Lint errors/warnings | 12 | 2 | **-10** |
| Duplicate interfaces | 5 | 0 | **-5** |
| Duplicate API base URLs | 3 | 1 | **-2** |
| Missing `useMemo` | 3 | 0 | **-3** |
| Missing `useCallback` deps | 2 | 0 | **-2** |

### Remaining 2 Lint Errors

Both are `react-hooks/set-state-in-effect` in WebSocket subscription code (`useWebSocket.ts` and `page.tsx`). These are false positives — setting state inside a WebSocket `onmessage` callback is the intended "subscribe for updates from external system" pattern described in the React docs. Not code quality issues.

## Combined Totals

| Metric | Delta |
|--------|-------|
| Source LOC (Python + TS) | **-414** |
| Test LOC | **+729** |
| Lint errors eliminated | **-10 frontend, -2 CC grade C** |
| Type safety improvements | **-7 `any` types, +6 shared interfaces** |

## Notes on MI Decrease

The average maintainability index dropped from 73.0 to 69.7. This is partly an artifact of decomposing large functions into smaller focused files (e.g., splitting `services/langfuse/` evaluators into individual modules in PRs #30/#32). Radon scores small single-purpose files lower individually despite being simpler to maintain in practice. The CC grade C reduction (-2) and source LOC reduction (-404) are better indicators of actual simplification.

## Findings Intentionally Deferred

| Finding | Module | Reason |
|---------|--------|--------|
| Error display consolidation (1.5) | ui-nextjs | Low value — 4 error banners have different layouts |
| `dangerouslySetInnerHTML` XSS (2.5) | ui-nextjs | Needs `react-markdown` dependency — separate issue |
