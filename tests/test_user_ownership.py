"""Tests for user_id ownership on ResearchJob."""

from __future__ import annotations

from uuid import uuid4

from d4bl.infra.database import ResearchJob


def test_research_job_has_user_id_column():
    """ResearchJob model should have a user_id column."""
    assert hasattr(ResearchJob, "user_id")


def test_research_job_to_dict_includes_user_id():
    """to_dict() should include user_id."""
    uid = uuid4()
    job = ResearchJob(query="test", status="pending", user_id=uid)
    d = job.to_dict()
    assert "user_id" in d
    assert d["user_id"] == str(uid)


def test_research_job_user_id_nullable():
    """user_id should be nullable (for legacy jobs)."""
    job = ResearchJob(query="test", status="pending")
    assert job.user_id is None