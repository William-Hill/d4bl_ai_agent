# Code Simplification Report

Ongoing metrics report for the code simplification sweep ([Epic #29](https://github.com/William-Hill/d4bl_ai_agent/issues/29)).

**Methodology**: Source metrics measured with [radon](https://radon.readthedocs.io/) (cyclomatic complexity, maintainability index) and `wc -l` (LOC). All measurements exclude `__pycache__/` directories.

---

## Overall Progress

| Metric | Before Sweep | Current | Delta |
|--------|-------------|---------|-------|
| Source LOC (`src/d4bl/`) | 6,436 | 5,960 | **-476 (-7.4%)** |
| Test LOC (`tests/`) | 1,231 | 1,796 | **+565 (+45.9%)** |
| Source files | 48 | 47 | -1 |
| Test files | 12 | 17 | +5 |
| Functions/methods | 186 | 181 | -5 |
| Avg cyclomatic complexity | 4.9 | 4.9 | — |
| CC grade C+ (high or worse) | 22 | 19 | **-3** |
| Avg maintainability index | 73.0 | 69.8 | -3.2 |
| Files with MI < 50 | 4 | 9 | +5 |

> **Note on MI**: The maintainability index decreased partly because PR #30 decomposed large monolithic functions into smaller focused files (e.g., splitting `services/langfuse/` into individual evaluator modules). Radon scores these smaller files lower individually despite them being simpler to maintain. The CC grade C reduction and source LOC reduction are better indicators of actual simplification.

---

## Completed Modules

### services/ (PRs #30, #32)

| Metric | Before | After | Delta |
|--------|--------|-------|-------|
| Source LOC | — | — | -204 net |

**Key changes**: Base evaluator eliminated ~250 LOC boilerplate, enum types replaced string constants, parallel eval execution

### agents/ (PR #34)

| Metric | Before | After | Delta |
|--------|--------|-------|-------|
| Source LOC | — | — | -372 net |

**Key changes**: Removed dead `crew.py` (255 LOC), dead scaffold, consolidated domain lists

### app/ (PR #35)

| Metric | Before | After | Delta |
|--------|--------|-------|-------|
| Source LOC | — | — | +8 net |
| Test LOC | — | — | +131 |

**Key changes**: UUID helper, deprecated FastAPI patterns, WS manager cleanup

### infra/ (PR #36)

| Metric | Before | After | Delta |
|--------|--------|-------|-------|
| Source LOC | — | — | -35 net |
| Test LOC | — | — | +131 |

**Key changes**: Async blocking fix, fragile SQL index access, dead Docker check

### query/ (PR #37)

| Metric | Before | After | Delta |
|--------|--------|-------|-------|
| Source LOC | — | — | +48 net |
| Test LOC | — | — | +97 |

**Key changes**: Shared Ollama HTTP helper, format bug fix, unused LLM intent parsing removed

### Root files (PR #38)

| Metric | Before | After | Delta |
|--------|--------|-------|-------|
| Source LOC | — | — | +56 net |
| Test LOC | — | — | +206 |

**Key changes**: Deferred env reads in Settings, removed catch-and-re-raise, lazy imports

---

## Remaining Modules

### observability/ (#25) — PR #TBD

| Metric | Baseline | After | Delta |
|--------|----------|-------|-------|
| Source LOC | 120 | 152 | +32 (+27%) |
| Source files | 2 | 2 | — |
| Functions/methods | 2 | 4 | +2 |
| Avg cyclomatic complexity | 11.0 | 6.0 | **-5.0 (-45%)** |
| CC grades | A:1, C:1 | A:3, C:1 | +2 A |
| Avg maintainability index | 76.2 | 79.5 | **+3.3** |
| `print()` calls | 15 | 0 | **-15** |
| `os.getenv` bypassing Settings | 3 | 4 | +1 |
| Test LOC added | — | 158 | +158 |

> LOC increased because two new functions were added (`resolve_langfuse_host`, `check_langfuse_service_available`) and print calls were replaced with more verbose logger calls. Average CC dropped significantly because the new functions are low-complexity.

### evals/ (#26)

| Metric | Baseline | After | Delta |
|--------|----------|-------|-------|
| Source LOC | 100 | | |
| Source files | 2 | | |
| Functions/methods | 1 | | |
| Avg cyclomatic complexity | 7.0 | | |
| CC grades | B:1 | | |
| Avg maintainability index | 85.0 | | |

### llm/ (#27)

| Metric | Baseline | After | Delta |
|--------|----------|-------|-------|
| Source LOC | 108 | | |
| Source files | 3 | | |
| Functions/methods | 3 | | |
| Avg cyclomatic complexity | 2.3 | | |
| CC grades | A:3 | | |
| Avg maintainability index | 90.3 | | |
| `print()` calls | 4 | | |

### ui-nextjs/ (#28)

> TypeScript — radon metrics don't apply. Track LOC, `any` types, and ESLint warnings.

---

## Files with Lowest Maintainability (MI < 50)

These files are the hardest to maintain. Improving them has the highest impact.

| File | MI (Before) | MI (Current) | Status |
|------|-------------|--------------|--------|
| `services/research_runner.py` | 26.4 | 27.6 | Needs work |
| `agents/tools/crawl_tools/crawl4ai.py` | 31.7 | 31.3 | Needs work |
| `app/api.py` | 33.4 | 34.6 | Improved slightly |
| `services/langfuse/runner.py` | 41.2 | 39.5 | Needs work |
| `services/langfuse/content_relevance.py` | — | 38.6 | New file (from split) |
| `services/langfuse/report_relevance.py` | — | 41.7 | New file (from split) |
| `services/langfuse/quality.py` | — | 45.6 | New file (from split) |
| `services/langfuse/source_relevance.py` | — | 45.9 | New file (from split) |
| `agents/crew.py` | — | 49.8 | Borderline |

---

## How to Regenerate

```bash
# Overall metrics
find src/d4bl -name '*.py' -not -path '*__pycache__*' | xargs wc -l | tail -1
find tests -name '*.py' -not -path '*__pycache__*' | xargs wc -l | tail -1
radon cc src/d4bl -s -a --no-assert
radon mi src/d4bl -s

# Per-module metrics
radon cc src/d4bl/<module> -s -a --no-assert
radon mi src/d4bl/<module> -s

# Complexity grade distribution (JSON)
radon cc src/d4bl -s --no-assert -j | python3 -c "
import json, sys
from collections import Counter
data = json.load(sys.stdin)
grades = Counter()
total_cc = 0
count = 0
for filepath, blocks in data.items():
    for block in blocks:
        grades[block['rank']] += 1
        total_cc += block['complexity']
        count += 1
print(f'Total functions/methods: {count}')
print(f'Average complexity: {total_cc/count:.1f}' if count else 'Average complexity: N/A')
for grade in sorted(grades.keys()):
    print(f'  Grade {grade}: {grades[grade]}')
"
```
