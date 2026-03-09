"""Unit tests for lineage API schemas and structured search provenance."""

from __future__ import annotations

from d4bl.app.schemas import (
    LineageGraphNode,
    LineageGraphResponse,
    LineageRecordResponse,
    ConnectionTestResponse,
)
from d4bl.query.structured import ProvenanceInfo


class TestLineageSchemas:
    """Validate lineage Pydantic models."""

    def test_lineage_record_response_minimal(self):
        resp = LineageRecordResponse(
            id="abc",
            ingestion_run_id="run-1",
            target_table="census_indicators",
            record_id="rec-1",
        )
        assert resp.target_table == "census_indicators"
        assert resp.data_source_name is None

    def test_lineage_record_response_full(self):
        resp = LineageRecordResponse(
            id="abc",
            ingestion_run_id="run-1",
            target_table="census_indicators",
            record_id="rec-1",
            source_url="https://api.census.gov",
            quality_score=4.2,
            data_source_name="Census ACS",
            data_source_type="api",
        )
        assert resp.data_source_name == "Census ACS"
        assert resp.quality_score == 4.2

    def test_lineage_graph_response(self):
        node = LineageGraphNode(
            asset_key="census_acs",
            source_name="Census ACS",
            source_type="api",
            record_count=1500,
        )
        graph = LineageGraphResponse(nodes=[node])
        assert len(graph.nodes) == 1
        assert graph.nodes[0].record_count == 1500

    def test_lineage_graph_empty(self):
        graph = LineageGraphResponse(nodes=[])
        assert graph.nodes == []


class TestTestConnectionSchema:
    def test_success(self):
        resp = ConnectionTestResponse(success=True, message="HTTP 200")
        assert resp.success is True

    def test_failure_with_details(self):
        resp = ConnectionTestResponse(
            success=False,
            message="HTTP 503",
            details={"status_code": 503},
        )
        assert resp.success is False
        assert resp.details["status_code"] == 503


class TestProvenanceInfo:
    def test_basic(self):
        p = ProvenanceInfo(
            data_source_name="Census ACS",
            quality_score=3.8,
            coverage_gaps=["Missing tribal data"],
        )
        assert p.data_source_name == "Census ACS"
        assert p.quality_score == 3.8
        assert "Missing tribal data" in p.coverage_gaps

    def test_defaults(self):
        p = ProvenanceInfo(data_source_name="Test")
        assert p.quality_score is None
        assert p.coverage_gaps == []
