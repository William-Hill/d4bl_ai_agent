"""Tests for Pydantic schema validation."""

import pytest
from pydantic import ValidationError

from d4bl.app.schemas import (
    AnalyzeResponse,
    CompareRequest,
    EvalRunItem,
    QueryRequest,
    ResearchRequest,
    SuggestionItem,
)


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


class TestCompareRequestModelFields:
    def test_accepts_pipeline_model_fields(self):
        r = CompareRequest(
            prompt="test query",
            pipeline_a_parser="mistral",
            pipeline_a_explainer="mistral",
            pipeline_b_parser="d4bl-query-parser",
            pipeline_b_explainer="d4bl-explainer",
        )
        assert r.pipeline_a_parser == "mistral"
        assert r.pipeline_b_explainer == "d4bl-explainer"

    def test_model_fields_optional_with_defaults(self):
        r = CompareRequest(prompt="test query")
        assert r.pipeline_a_parser is None
        assert r.pipeline_b_parser is None


class TestEvalRunItemSuggestions:
    def test_suggestions_field_present(self):
        item = EvalRunItem(
            model_name="test",
            model_version="v1.0",
            base_model_name="mistral",
            task="query_parser",
            metrics={"json_valid_rate": 0.99},
            ship_decision="ship",
            suggestions={"rules": [], "llm_analysis": None, "generated_at": "2026-03-27"},
        )
        assert item.suggestions is not None
        assert item.suggestions["rules"] == []


class TestSuggestionItem:
    def test_fields(self):
        s = SuggestionItem(
            metric="entity_f1",
            severity="blocking",
            current=0.72,
            target=0.80,
            suggestion="Add more diverse entities",
            category="training_data",
        )
        assert s.severity == "blocking"


class TestAnalyzeResponse:
    def test_fields(self):
        r = AnalyzeResponse(
            run_id="abc-123",
            suggestions={"rules": [], "llm_analysis": "test", "generated_at": "2026-03-27"},
        )
        assert r.suggestions["llm_analysis"] == "test"
