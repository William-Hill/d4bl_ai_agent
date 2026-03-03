"""Tests for Pydantic schema validation."""
import pytest
from pydantic import ValidationError

from d4bl.app.schemas import ResearchRequest, QueryRequest


class TestResearchRequest:
    def test_valid_request(self):
        req = ResearchRequest(query="test query")
        assert req.query == "test query"
        assert req.summary_format == "detailed"

    def test_empty_query_rejected(self):
        with pytest.raises(ValidationError):
            ResearchRequest(query="")

    def test_whitespace_only_query_rejected(self):
        with pytest.raises(ValidationError):
            ResearchRequest(query="   ")

    def test_invalid_summary_format_rejected(self):
        with pytest.raises(ValidationError):
            ResearchRequest(query="test", summary_format="invalid")

    def test_valid_summary_formats(self):
        for fmt in ("brief", "detailed", "comprehensive"):
            req = ResearchRequest(query="test", summary_format=fmt)
            assert req.summary_format == fmt


class TestQueryRequest:
    def test_valid_request(self):
        req = QueryRequest(question="What is X?")
        assert req.question == "What is X?"

    def test_empty_question_rejected(self):
        with pytest.raises(ValidationError):
            QueryRequest(question="")

    def test_whitespace_only_question_rejected(self):
        with pytest.raises(ValidationError):
            QueryRequest(question="   ")
