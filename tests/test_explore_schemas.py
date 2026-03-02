"""Tests for explore endpoint Pydantic schemas."""
import pytest

from d4bl.app.schemas import (
    IndicatorItem,
    PolicyBillItem,
    StateSummaryItem,
)


class TestIndicatorItem:
    def test_serializes_correctly(self):
        item = IndicatorItem(
            fips_code="28",
            geography_name="Mississippi",
            state_fips="28",
            geography_type="state",
            year=2022,
            race="black",
            metric="homeownership_rate",
            value=43.2,
            margin_of_error=None,
        )
        d = item.model_dump()
        assert d["fips_code"] == "28"
        assert d["margin_of_error"] is None

    def test_metric_required(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            IndicatorItem(
                fips_code="28",
                geography_name="Mississippi",
                state_fips="28",
                geography_type="state",
                year=2022,
                race="black",
                value=43.2,
                margin_of_error=None,
            )  # type: ignore[call-arg]


class TestPolicyBillItem:
    def test_serializes_correctly(self):
        bill = PolicyBillItem(
            state="MS",
            state_name="Mississippi",
            bill_number="SB 1234",
            title="Housing Equity Act",
            summary=None,
            status="introduced",
            topic_tags=["housing"],
            introduced_date=None,
            last_action_date=None,
            url="https://legislature.ms.gov/sb1234",
        )
        d = bill.model_dump()
        assert d["state"] == "MS"
        assert d["topic_tags"] == ["housing"]


class TestStateSummaryItem:
    def test_serializes_correctly(self):
        item = StateSummaryItem(
            state_fips="28",
            state_name="Mississippi",
            available_metrics=["homeownership_rate", "poverty_rate"],
            bill_count=12,
            latest_year=2022,
        )
        d = item.model_dump()
        assert d["bill_count"] == 12
        assert len(d["available_metrics"]) == 2

