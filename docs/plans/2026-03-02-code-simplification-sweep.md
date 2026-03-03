# Code Simplification Sweep

**Date**: 2026-03-02
**Status**: Approved

## Goal

Review every module in the codebase for code reuse, quality, and efficiency issues. File actionable GitHub issues with concrete findings. **Zero regressions** — all suggested changes must preserve existing behavior.

## Modules (review order, largest first)

| # | Module | LOC | Description |
|---|--------|-----|-------------|
| 1 | `src/d4bl/services/` | 2,294 | Langfuse evaluators, research runner, error handling |
| 2 | `src/d4bl/agents/` | 1,464 | Crew definitions, crawl tools |
| 3 | `src/d4bl/app/` | 833 | FastAPI API, schemas, websocket manager |
| 4 | `src/d4bl/infra/` | 619 | Database models, vector store |
| 5 | `src/d4bl/query/` | 493 | NL query engine (parser, structured, fusion, engine) |
| 6 | Root files | 459 | settings.py, main.py, crew.py |
| 7 | `src/d4bl/observability/` | 120 | Langfuse tracing |
| 8 | `src/d4bl/evals/` | 100 | Evaluation runner |
| 9 | `src/d4bl/llm/` | 54 | Ollama LLM config |
| 10 | `ui-nextjs/` | 2,107 | Next.js frontend |

## Review Criteria

Three parallel review agents per module:

### Agent 1: Code Reuse
- Duplicated logic across files
- Utilities that already exist elsewhere in the codebase
- Hand-rolled patterns that could use existing helpers
- Inline logic replaceable by existing utilities

### Agent 2: Code Quality
- Redundant state (duplicates, derivable values)
- Parameter sprawl
- Copy-paste with slight variation
- Leaky abstractions
- Stringly-typed code where constants/enums exist

### Agent 3: Efficiency
- Redundant computations, repeated file reads, duplicate API calls
- Missed concurrency (sequential ops that could be parallel)
- Hot-path bloat
- Unnecessary existence checks (TOCTOU anti-pattern)
- Unbounded data structures, missing cleanup
- Overly broad operations

## Regression Constraint

Every finding is tagged with a risk level:

- **Safe** — Pure refactor, no behavior change (rename, extract, dedup)
- **Low risk** — Minor behavior change possible, needs manual verification
- **Needs tests** — Change could alter behavior, should not be attempted without test coverage

## GitHub Structure

- **Label**: `code-simplification` (color `#7B68EE`)
- **Epic issue**: "Code Simplification Sweep" with checkbox list linking to each module issue
- **Module issues**: One per module, containing:
  - Summary of findings by category (reuse/quality/efficiency)
  - Specific file:line references
  - Suggested fix for each finding
  - Risk level per finding
  - "No regressions" callout at the top

## Execution Plan

1. Create the `code-simplification` label
2. Run reviews on modules 1-5 in parallel (large modules)
3. Run reviews on modules 6-10 in parallel (small modules)
4. Aggregate all findings
5. Create the epic issue
6. Create the 10 module issues, linking back to the epic
