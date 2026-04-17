"""Tests for staff upload API schemas and endpoints."""

import pytest
from pydantic import ValidationError


class TestUploadSchemas:
    """Validate upload request/response schemas."""

    def test_datasource_upload_valid(self):
        from d4bl.app.schemas import DataSourceUploadRequest

        req = DataSourceUploadRequest(
            source_name="County Health Rankings 2024",
            description="County-level health outcomes by race",
            geographic_level="county",
            data_year=2024,
        )
        assert req.source_name == "County Health Rankings 2024"
        assert req.geographic_level == "county"

    def test_datasource_upload_invalid_geo_level(self):
        from d4bl.app.schemas import DataSourceUploadRequest

        with pytest.raises(ValidationError):
            DataSourceUploadRequest(
                source_name="Test",
                description="Test",
                geographic_level="zipcode",
                data_year=2024,
            )

    def test_datasource_upload_blank_name(self):
        from d4bl.app.schemas import DataSourceUploadRequest

        with pytest.raises(ValidationError):
            DataSourceUploadRequest(
                source_name="  ",
                description="Test",
                geographic_level="county",
                data_year=2024,
            )

    def test_document_upload_valid(self):
        from d4bl.app.schemas import DocumentUploadRequest

        req = DocumentUploadRequest(
            title="Vera Incarceration Report",
            document_type="report",
            topic_tags=["incarceration", "racial-disparity"],
        )
        assert req.title == "Vera Incarceration Report"

    def test_document_upload_invalid_type(self):
        from d4bl.app.schemas import DocumentUploadRequest

        with pytest.raises(ValidationError):
            DocumentUploadRequest(
                title="Test",
                document_type="spreadsheet",
                topic_tags=[],
            )

    def test_example_query_valid(self):
        from d4bl.app.schemas import ExampleQueryRequest

        req = ExampleQueryRequest(
            query_text="What are the racial disparities in housing discrimination in Mississippi?",
            summary_format="detailed",
            description="Tests equity-focused housing query",
        )
        assert req.summary_format == "detailed"

    def test_example_query_too_long(self):
        from d4bl.app.schemas import ExampleQueryRequest

        with pytest.raises(ValidationError):
            ExampleQueryRequest(
                query_text="x" * 2001,
                summary_format="detailed",
                description="Too long",
            )

    def test_feature_request_valid(self):
        from d4bl.app.schemas import FeatureRequestCreate

        req = FeatureRequestCreate(
            title="Add HMDA mortgage data",
            description="Include Home Mortgage Disclosure Act data for lending disparity analysis",
            who_benefits="Researchers studying housing discrimination",
        )
        assert req.title == "Add HMDA mortgage data"

    def test_feature_request_blank_title(self):
        from d4bl.app.schemas import FeatureRequestCreate

        with pytest.raises(ValidationError):
            FeatureRequestCreate(
                title="",
                description="Test",
                who_benefits="Test",
            )

    def test_upload_review_valid(self):
        from d4bl.app.schemas import UploadReviewRequest

        req = UploadReviewRequest(action="approve", notes="Looks good")
        assert req.action == "approve"

    def test_upload_review_reject_requires_notes(self):
        from d4bl.app.schemas import UploadReviewRequest

        with pytest.raises(ValidationError):
            UploadReviewRequest(action="reject", notes=None)

    def test_upload_response_schema(self):
        from d4bl.app.schemas import UploadResponse

        resp = UploadResponse(
            id="00000000-0000-0000-0000-000000000001",
            upload_type="datasource",
            status="pending_review",
            original_filename="data.csv",
            metadata={"source_name": "Test"},
            created_at="2026-04-17T00:00:00Z",
        )
        assert resp.status == "pending_review"
