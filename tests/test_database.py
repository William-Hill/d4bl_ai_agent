"""Tests for database model defaults and helpers."""

from d4bl.infra.database import (
    CensusIndicator,
    EvaluationResult,
    PolicyBill,
    ResearchJob,
    _utc_now,
)


class TestUtcNow:
    """Verify _utc_now produces timezone-aware UTC values."""

    def test_utc_now_returns_aware_datetime(self):
        result = _utc_now()
        assert result.tzinfo is not None

    def test_utc_now_is_utc(self):
        from datetime import timezone

        result = _utc_now()
        assert result.tzinfo == timezone.utc


def _get_column_default(model_class, column_name: str) -> object | None:
    """Extract the default callable from a SQLAlchemy column."""
    col = model_class.__table__.columns[column_name]
    if col.default is not None:
        return col.default.arg
    return None


def _get_column_onupdate(model_class, column_name: str) -> object | None:
    """Extract the onupdate callable from a SQLAlchemy column."""
    col = model_class.__table__.columns[column_name]
    if col.onupdate is not None:
        return col.onupdate.arg
    return None


class TestDatetimeDefaults:
    """Verify all datetime columns use _utc_now."""

    def test_research_job_created_at_uses_utc_now(self):
        fn = _get_column_default(ResearchJob, "created_at")
        assert fn.__name__ == "_utc_now"

    def test_research_job_updated_at_uses_utc_now(self):
        assert _get_column_default(ResearchJob, "updated_at").__name__ == "_utc_now"

    def test_research_job_updated_at_onupdate_uses_utc_now(self):
        assert _get_column_onupdate(ResearchJob, "updated_at").__name__ == "_utc_now"

    def test_evaluation_result_created_at_uses_utc_now(self):
        assert _get_column_default(EvaluationResult, "created_at").__name__ == "_utc_now"

    def test_census_indicator_created_at_uses_utc_now(self):
        assert _get_column_default(CensusIndicator, "created_at").__name__ == "_utc_now"

    def test_policy_bill_created_at_uses_utc_now(self):
        assert _get_column_default(PolicyBill, "created_at").__name__ == "_utc_now"

    def test_policy_bill_updated_at_uses_utc_now(self):
        assert _get_column_default(PolicyBill, "updated_at").__name__ == "_utc_now"

    def test_policy_bill_updated_at_onupdate_uses_utc_now(self):
        assert _get_column_onupdate(PolicyBill, "updated_at").__name__ == "_utc_now"

    def test_get_column_default_returns_none_when_missing(self):
        assert _get_column_default(ResearchJob, "completed_at") is None

    def test_get_column_onupdate_returns_none_when_missing(self):
        assert _get_column_onupdate(ResearchJob, "completed_at") is None
