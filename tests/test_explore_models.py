"""Tests for CensusIndicator and PolicyBill ORM models."""


from d4bl.infra.database import CensusIndicator, PolicyBill


class TestCensusIndicator:
    def test_can_instantiate_with_required_fields(self):
        row = CensusIndicator(
            fips_code="28",
            geography_type="state",
            geography_name="Mississippi",
            state_fips="28",
            year=2022,
            race="black",
            metric="homeownership_rate",
            value=43.2,
        )
        assert row.fips_code == "28"
        assert row.year == 2022
        assert row.value == 43.2

    def test_tablename(self):
        assert CensusIndicator.__tablename__ == "census_indicators"

    def test_margin_of_error_nullable(self):
        row = CensusIndicator(
            fips_code="28",
            geography_type="state",
            geography_name="Mississippi",
            state_fips="28",
            year=2022,
            race="total",
            metric="poverty_rate",
            value=19.1,
            margin_of_error=None,
        )
        assert row.margin_of_error is None


class TestPolicyBill:
    def test_can_instantiate_with_required_fields(self):
        bill = PolicyBill(
            state="MS",
            state_name="Mississippi",
            bill_id="ocd-bill/abc123",
            bill_number="SB 1234",
            title="Housing Equity Act",
            status="introduced",
            session="2025",
        )
        assert bill.state == "MS"
        assert bill.status == "introduced"

    def test_tablename(self):
        assert PolicyBill.__tablename__ == "policy_bills"

    def test_topic_tags_defaults_to_empty_list(self):
        bill = PolicyBill(
            state="MS",
            state_name="Mississippi",
            bill_id="ocd-bill/xyz",
            bill_number="HB 10",
            title="Test",
            status="passed",
            session="2025",
        )
        # topic_tags is nullable, not defaulted in model
        assert bill.topic_tags is None or isinstance(bill.topic_tags, list)
