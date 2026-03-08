"""Tests for /api/explore/* endpoints."""
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient


class TestIndicatorsEndpoint:
    @pytest.mark.asyncio
    async def test_returns_200_with_list(self, override_auth):
        app = override_auth
        from d4bl.infra.database import get_db

        mock_row = MagicMock()
        mock_row.fips_code = "28"
        mock_row.geography_name = "Mississippi"
        mock_row.state_fips = "28"
        mock_row.geography_type = "state"
        mock_row.year = 2022
        mock_row.race = "black"
        mock_row.metric = "homeownership_rate"
        mock_row.value = 43.2
        mock_row.margin_of_error = None

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_row]

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        async def override_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_get_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/api/explore/indicators",
                params={"state_fips": "28", "metric": "homeownership_rate"},
            )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["fips_code"] == "28"
        assert data[0]["value"] == 43.2

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_data(self, override_auth):
        app = override_auth
        from d4bl.infra.database import get_db

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        async def override_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_get_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/explore/indicators")

        assert response.status_code == 200
        assert response.json() == []


class TestPoliciesEndpoint:
    @pytest.mark.asyncio
    async def test_returns_200_with_list(self, override_auth):
        app = override_auth
        from d4bl.infra.database import get_db

        mock_row = MagicMock()
        mock_row.state = "MS"
        mock_row.state_name = "Mississippi"
        mock_row.bill_number = "SB 1234"
        mock_row.title = "Housing Equity Act"
        mock_row.summary = None
        mock_row.status = "introduced"
        mock_row.topic_tags = ["housing"]
        mock_row.introduced_date = None
        mock_row.last_action_date = None
        mock_row.url = "https://legislature.ms.gov/sb1234"

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_row]

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        async def override_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_get_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/api/explore/policies",
                params={"state": "MS"},
            )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert data[0]["state"] == "MS"
        assert data[0]["topic_tags"] == ["housing"]


class TestStatesEndpoint:
    @pytest.mark.asyncio
    async def test_returns_200_with_state_list(self, override_auth):
        app = override_auth
        from d4bl.infra.database import get_db

        # metrics aggregate result: (state_fips, state_name, metrics_list, latest_year)
        mock_metrics_row = MagicMock()
        mock_metrics_row._mapping = {
            "state_fips": "28",
            "state_name": "Mississippi",
            "metrics": "homeownership_rate,poverty_rate",
            "latest_year": 2022,
        }

        # bill count result: (state_name, bill_count) -- API groups by state_name
        mock_bills_row = MagicMock()
        mock_bills_row._mapping = {
            "state_name": "Mississippi",
            "bill_count": 7,
        }

        mock_result_metrics = MagicMock()
        mock_result_metrics.mappings.return_value.all.return_value = [mock_metrics_row._mapping]

        mock_result_bills = MagicMock()
        mock_result_bills.mappings.return_value.all.return_value = [mock_bills_row._mapping]

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(side_effect=[mock_result_metrics, mock_result_bills])

        async def override_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_get_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/explore/states")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["state_fips"] == "28"
        assert data[0]["state_name"] == "Mississippi"
        assert data[0]["bill_count"] == 7

