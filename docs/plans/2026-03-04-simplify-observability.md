# Plan: Simplify observability/ module

> Closes #25. No regressions — all changes preserve existing behavior.

## Task 1: Remove dead code and duplicate messages (findings 2.1, 2.5)

**Files**: `src/d4bl/observability/langfuse.py`

### Changes

- Remove lines 43-46: env var re-set guards that are always False (the values were just read from `os.getenv`, so the `if not os.getenv(...)` check never triggers)
- Remove the duplicate success message on line 85 ("CrewAI instrumentation initialized") — line 88 already prints the same thing with more detail

### Tests

- Existing imports and initialization still work
- No behavioral change

---

## Task 2: Replace `print()` with `logger` (finding 2.2)

**Files**: `src/d4bl/observability/langfuse.py`

### Changes

- Replace all 15 `print()` calls with appropriate `logger` calls:
  - Success messages → `logger.info`
  - Warnings → `logger.warning`
  - Debug details (host URLs, endpoints) → `logger.debug`
- The module already declares `logger = logging.getLogger(__name__)` but never uses it

### Tests

- Verify no `print()` calls remain in the file
- Module still initializes correctly

---

## Task 3: Add `check_langfuse_service_available` + fix init sentinel (findings 2.3, 2.6)

**Files**: `src/d4bl/observability/langfuse.py`, `src/d4bl/app/api.py`

### 3a: Add missing function (finding 2.3)

`api.py:100` imports `check_langfuse_service_available` from `observability.langfuse`, but it doesn't exist. The ImportError is silently caught, so the availability check is skipped entirely.

Add a simple implementation:

```python
def check_langfuse_service_available(host: str, timeout: float = 3.0) -> bool:
    """Check if Langfuse service is reachable via HTTP GET."""
    import urllib.request
    try:
        urllib.request.urlopen(f"{host}/api/public/health", timeout=timeout)
        return True
    except Exception:
        return False
```

Use `urllib.request` (stdlib) to avoid adding a dependency.

### 3b: Fix initialization sentinel (finding 2.6)

Currently `_langfuse_initialized` is `False` after failure, so `get_langfuse_client()` re-attempts init on every call (potentially slow/timeout). Use a three-state sentinel:

- `None` → not yet attempted
- `True` → succeeded
- `False` → failed, don't retry

```python
_langfuse_init_state: bool | None = None  # None=untried, True=ok, False=failed

def initialize_langfuse() -> Langfuse | None:
    global _langfuse_init_state, _langfuse_client
    if _langfuse_init_state is not None:
        return _langfuse_client
    ...
    # on success:
    _langfuse_init_state = True
    # on failure:
    _langfuse_init_state = False
```

Export `check_langfuse_service_available` from `__init__.py`.

### Tests

- Test `check_langfuse_service_available` returns False on unreachable host
- Test that init is not re-attempted after failure

---

## Task 4: Unify Docker host adjustment + return type annotations (findings 1.2, 2.4)

**Files**: `src/d4bl/observability/langfuse.py`, `src/d4bl/services/langfuse/client.py`, `src/d4bl/app/api.py`

### 4a: Extract shared Docker host helper (finding 1.2)

Three places adjust the Langfuse host for Docker with slightly different logic. Extract into `observability/langfuse.py`:

```python
def _resolve_langfuse_host(settings: Settings) -> str:
    """Return the effective Langfuse host, adjusted for Docker if needed."""
    host = settings.langfuse_host
    if settings.is_docker and "localhost" in host:
        host = host.replace("localhost", "langfuse-web")
        if ":3002" in host:
            host = host.replace(":3002", ":3000")
    return host
```

- Use in `initialize_langfuse()` (replaces inline logic)
- Use in `services/langfuse/client.py` `get_langfuse_eval_client()` (import from observability)
- Use in `app/api.py` lifespan (import from observability, remove inline Docker adjustment)

### 4b: Add return type annotations (finding 2.4)

- `initialize_langfuse() -> Langfuse | None` (already addressed in Task 3)
- `get_langfuse_client() -> Langfuse | None`

### Tests

- Test `_resolve_langfuse_host` with Docker and non-Docker settings
- Verify all three call sites work with the shared helper

---

## Task 5: Open PR

- Run full test suite
- Push branch, open PR closing #25
