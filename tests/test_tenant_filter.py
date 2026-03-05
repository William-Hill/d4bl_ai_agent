"""Tests for tenant_id filtering on ResearchJob."""
from __future__ import annotations

from d4bl.infra.database import ResearchJob


def test_research_job_has_tenant_id_column():
    """ResearchJob model should have a tenant_id column."""
    assert hasattr(ResearchJob, "tenant_id")


def test_research_job_to_dict_includes_tenant_id():
    """to_dict() should include tenant_id."""
    job = ResearchJob(query="test", status="pending", tenant_id="org-test")
    d = job.to_dict()
    assert "tenant_id" in d
    assert d["tenant_id"] == "org-test"


def test_research_job_tenant_id_nullable():
    """tenant_id should be nullable (backward compatible)."""
    job = ResearchJob(query="test", status="pending")
    assert job.tenant_id is None
