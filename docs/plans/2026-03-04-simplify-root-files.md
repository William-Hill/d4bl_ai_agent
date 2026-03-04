# Plan: Simplify Root Files (settings, main, crew)

> Closes #24. No regressions — all changes preserve existing behavior.

7 of the 15 original findings are already resolved from previous PRs. This plan addresses the remaining 7.

## Task 1: Use `Settings` for `LANGFUSE_HOST` in `client.py` (findings 1.3, 1.4)

**Files**: `src/d4bl/services/langfuse/client.py`

`client.py:30` reads `LANGFUSE_HOST` via raw `os.getenv` instead of `get_settings().langfuse_host`. Replace with `Settings` to ensure consistency.

### Changes

- Replace `langfuse_host = os.getenv("LANGFUSE_HOST", "http://localhost:3002")` with `langfuse_host = get_settings().langfuse_host`
- Remove `import os` if no longer needed
- The Docker adjustment logic on lines 41-46 can stay — it modifies the local variable

### Tests

- Existing tests (if any) should still pass
- Verify `get_langfuse_eval_client` still works with the Settings-backed value

---

## Task 2: Remove catch-and-re-raise in `main.py` (finding 2.4)

**Files**: `src/d4bl/main.py`

5 functions wrap their bodies in `try/except Exception as e: raise Exception(...)` which discards the original traceback and exception type. Remove these wrappers.

### Changes

- `run()`: Remove try/except around `crew_instance` kickoff (lines 89-99)
- `train()`: Remove try/except (lines 110-114)
- `replay()`: Remove try/except (lines 120-124)
- `test()`: Remove try/except (lines 135-139)
- `run_with_trigger()`: Remove try/except (lines 161-165)

### Tests

- No existing tests for main.py CLI functions
- Verify module still imports cleanly

---

## Task 3: Clean up `settings.py` (findings 2.6, 3.2)

**Files**: `src/d4bl/settings.py`

### 3a: Simplify `otlp_endpoint` (finding 2.6)

The triple-nested `os.getenv` on lines 33-36 is hard to read:

```python
otlp_endpoint: str = os.getenv(
    "OTEL_EXPORTER_OTLP_ENDPOINT",
    f"{os.getenv('LANGFUSE_OTEL_HOST', os.getenv('LANGFUSE_HOST', 'http://localhost:3002'))}/api/public/otel/v1/traces",
)
```

Use `__post_init__` to build from already-resolved fields.

### 3b: Defer `os.getenv` to instantiation (finding 3.2)

Currently field defaults call `os.getenv()` at class definition time, not instantiation. This creates fragile import ordering — if env vars are set after the module is first imported, `Settings()` picks up stale values.

Move env reads into `__post_init__` so they execute when `Settings()` is called (which is at first `get_settings()` call due to `@lru_cache`).

### Changes

- Convert all field defaults from `os.getenv(...)` to `field(default=None)` or similar
- Add `__post_init__` that reads env vars and sets fields via `object.__setattr__` (required for `frozen=True`)
- `otlp_endpoint` should fall back to `self.langfuse_otel_host or self.langfuse_host` + suffix

### Tests

- Add test that `get_settings()` reads env vars at call time, not import time
- Verify all existing code that calls `get_settings()` still works

---

## Task 4: Minor cleanups (findings 3.3, 3.4)

### 4a: Remove redundant `.rstrip("/")` (finding 3.3)

**File**: `src/d4bl/llm/ollama.py`

Line 17: `settings.ollama_base_url.rstrip("/")` — the `.rstrip("/")` is already applied in `Settings.ollama_base_url`. Remove the redundant call.

### 4b: Lazy-import `D4Bl` in `main.py` (finding 3.4)

**File**: `src/d4bl/main.py`

Move `from d4bl.agents.crew import D4Bl` from module scope into each function that uses it (`run()`, `train()`, `replay()`, `test()`, `run_with_trigger()`). This avoids loading CrewAI and all agent dependencies for CLI startup.

### Tests

- Verify module imports cleanly
- Verify functions still work with lazy import

---

## Task 5: Open PR

- Run full test suite (88+ tests)
- Push branch, open PR closing #24
