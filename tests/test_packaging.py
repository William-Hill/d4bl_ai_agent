"""Verify pyproject.toml contains all previously-listed packages."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

REQUIRED_PACKAGES = [
    "fastapi",
    "uvicorn",
    "sqlalchemy",
    "asyncpg",
    "aiohttp",
    "langfuse",
    "openinference-instrumentation-crewai",
    "openinference-instrumentation-litellm",
    "pandas",
    "alembic",
    "ollama",
    "pypdf",
]


def test_pyproject_contains_all_required_packages():
    """pyproject.toml must list all runtime dependencies that were in requirements.txt."""
    root = Path(__file__).parent.parent
    pyproject_text = (root / "pyproject.toml").read_text()

    missing = [pkg for pkg in REQUIRED_PACKAGES if pkg not in pyproject_text]
    assert not missing, f"Missing from pyproject.toml: {missing}"


def test_requirements_txt_removed():
    """requirements.txt should not exist — all deps managed in pyproject.toml."""
    root = Path(__file__).parent.parent
    assert not (root / "requirements.txt").exists(), \
        "requirements.txt should be deleted; use pyproject.toml instead"
