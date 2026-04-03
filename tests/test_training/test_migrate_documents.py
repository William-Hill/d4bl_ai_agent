"""Tests for document migration logic."""

from scripts.training.migrate_documents import (
    extract_research_job_text,
    policy_bill_to_document,
)


class TestPolicyBillToDocument:
    def test_converts_bill_to_document_dict(self):
        bill = {
            "id": 1,
            "title": "Housing Protection Act",
            "summary": "Protects tenants from unfair eviction.",
            "state": "AL",
            "status": "introduced",
            "topic_tags": ["housing", "tenant_rights"],
            "session": "2025",
            "url": "https://openstates.org/al/bills/HB123",
            "bill_number": "HB 123",
        }
        doc = policy_bill_to_document(bill)
        assert doc["title"] == "Housing Protection Act"
        assert doc["content_type"] == "policy_bill"
        assert doc["source_url"] == "https://openstates.org/al/bills/HB123"
        assert doc["metadata"]["state"] == "AL"
        assert doc["metadata"]["topic_tags"] == ["housing", "tenant_rights"]
        assert doc["text"] == "Protects tenants from unfair eviction."

    def test_handles_missing_summary(self):
        bill = {
            "id": 1,
            "title": "Some Bill",
            "summary": None,
            "state": "AK",
            "status": "introduced",
            "topic_tags": [],
            "session": "2025",
            "url": None,
            "bill_number": "SB 1",
        }
        doc = policy_bill_to_document(bill)
        assert doc["text"] == ""


class TestExtractResearchJobText:
    def test_extracts_from_result_dict(self):
        result = {"final_report": "This is the research finding about housing disparities."}
        text = extract_research_job_text(result, research_data=None)
        assert "housing disparities" in text

    def test_extracts_from_research_data(self):
        research_data = {"research_findings": "Incarceration rates are disproportionate."}
        text = extract_research_job_text(result=None, research_data=research_data)
        assert "Incarceration rates" in text

    def test_handles_none_gracefully(self):
        text = extract_research_job_text(result=None, research_data=None)
        assert text == ""

    def test_combines_result_and_research_data(self):
        result = {"final_report": "Report text."}
        research_data = {"research_findings": "Finding text."}
        text = extract_research_job_text(result, research_data)
        assert "Report text" in text
        assert "Finding text" in text