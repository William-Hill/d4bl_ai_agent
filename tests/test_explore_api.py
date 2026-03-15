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


class TestCdcHealthEndpoint:
    @pytest.mark.asyncio
    async def test_returns_200_with_explore_response(self, override_auth):
        app = override_auth
        from d4bl.infra.database import get_db

        mock_result = MagicMock()
        mock_result.mappings.return_value.all.return_value = [
            {"state_fips": "28", "avg_value": 12.5, "measure": "Asthma", "year": 2022}
        ]

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        async def override_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_get_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/api/explore/cdc",
                params={"state_fips": "28", "measure": "Asthma"},
            )

        assert response.status_code == 200
        data = response.json()
        assert "rows" in data
        assert "national_average" in data
        assert "available_metrics" in data
        assert "available_years" in data
        assert "available_races" in data
        assert len(data["rows"]) == 1
        assert data["rows"][0]["state_fips"] == "28"
        assert data["rows"][0]["value"] == 12.5
        assert data["rows"][0]["metric"] == "Asthma"
        assert data["national_average"] == 12.5
        assert data["available_metrics"] == ["Asthma"]
        assert data["available_years"] == [2022]
        assert data["available_races"] == []


class TestEpaEndpoint:
    @pytest.mark.asyncio
    async def test_returns_200_with_explore_response(self, override_auth):
        app = override_auth
        from d4bl.infra.database import get_db

        mock_result = MagicMock()
        mock_result.mappings.return_value.all.return_value = [
            {"state_fips": "06", "state_name": "California", "avg_value": 10.5, "indicator": "PM2.5", "year": 2022}
        ]

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        async def override_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_get_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/api/explore/epa",
                params={"state_fips": "06", "indicator": "PM2.5"},
            )

        assert response.status_code == 200
        data = response.json()
        assert len(data["rows"]) == 1
        assert data["rows"][0]["state_fips"] == "06"
        assert data["rows"][0]["value"] == 10.5
        assert data["rows"][0]["metric"] == "PM2.5"
        assert data["national_average"] == 10.5
        assert data["available_races"] == []


class TestFbiEndpoint:
    @pytest.mark.asyncio
    async def test_returns_200_with_explore_response(self, override_auth):
        app = override_auth
        from d4bl.infra.database import get_db

        mock_row = MagicMock()
        mock_row.state_abbrev = "MS"
        mock_row.state_name = "Mississippi"
        mock_row.value = 120.0
        mock_row.offense = "Aggravated Assault"
        mock_row.year = 2022
        mock_row.race = "Black"

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
                "/api/explore/fbi",
                params={"state_fips": "28", "offense": "Aggravated Assault"},
            )

        assert response.status_code == 200
        data = response.json()
        assert len(data["rows"]) == 1
        assert data["rows"][0]["state_fips"] == "28"
        assert data["rows"][0]["value"] == 120.0
        assert data["rows"][0]["metric"] == "Aggravated Assault"
        assert data["rows"][0]["race"] == "Black"
        assert data["available_races"] == ["Black"]


class TestBlsEndpoint:
    @pytest.mark.asyncio
    async def test_returns_200_with_explore_response(self, override_auth):
        app = override_auth
        from d4bl.infra.database import get_db

        mock_row = MagicMock()
        mock_row.state_fips = "28"
        mock_row.state_name = "Mississippi"
        mock_row.value = 5.2
        mock_row.metric = "unemployment_rate"
        mock_row.year = 2023
        mock_row.race = "Black"

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
                "/api/explore/bls",
                params={"state_fips": "28", "metric": "unemployment_rate"},
            )

        assert response.status_code == 200
        data = response.json()
        assert len(data["rows"]) == 1
        assert data["rows"][0]["state_fips"] == "28"
        assert data["rows"][0]["value"] == 5.2
        assert data["rows"][0]["race"] == "Black"
        assert data["available_races"] == ["Black"]


class TestHudEndpoint:
    @pytest.mark.asyncio
    async def test_returns_200_with_explore_response(self, override_auth):
        app = override_auth
        from d4bl.infra.database import get_db

        mock_result = MagicMock()
        mock_result.mappings.return_value.all.return_value = [
            {"state_fips": "28", "avg_value": 0.45, "indicator": "Dissimilarity Index", "year": 2020}
        ]

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        async def override_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_get_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/api/explore/hud",
                params={"state_fips": "28", "indicator": "Dissimilarity Index"},
            )

        assert response.status_code == 200
        data = response.json()
        assert len(data["rows"]) == 1
        assert data["rows"][0]["state_fips"] == "28"
        assert data["rows"][0]["state_name"] == "Mississippi"
        assert data["rows"][0]["value"] == 0.45
        assert data["rows"][0]["metric"] == "Dissimilarity Index"
        assert data["available_races"] == []


class TestUsdaEndpoint:
    @pytest.mark.asyncio
    async def test_returns_200_with_explore_response(self, override_auth):
        app = override_auth
        from d4bl.infra.database import get_db

        mock_result = MagicMock()
        mock_result.mappings.return_value.all.return_value = [
            {"state_fips": "28", "state_name": "Mississippi", "avg_value": 22.3, "indicator": "Low Access", "year": 2019}
        ]

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        async def override_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_get_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/api/explore/usda",
                params={"state_fips": "28"},
            )

        assert response.status_code == 200
        data = response.json()
        assert len(data["rows"]) == 1
        assert data["rows"][0]["value"] == 22.3
        assert data["rows"][0]["metric"] == "Low Access"
        assert data["available_races"] == []


class TestDoeEndpoint:
    @pytest.mark.asyncio
    async def test_returns_200_with_explore_response(self, override_auth):
        app = override_auth
        from d4bl.infra.database import get_db

        mock_result = MagicMock()
        mock_result.mappings.return_value.all.return_value = [
            {"state": "MS", "state_name": "Mississippi", "avg_value": 3.5, "metric_name": "Suspensions", "race": "Black", "school_year": "2020-2021"}
        ]

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        async def override_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_get_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/api/explore/doe",
                params={"state": "MS", "metric": "Suspensions"},
            )

        assert response.status_code == 200
        data = response.json()
        assert len(data["rows"]) == 1
        assert data["rows"][0]["state_fips"] == "28"
        assert data["rows"][0]["value"] == 3.5
        assert data["rows"][0]["race"] == "Black"
        assert data["available_races"] == ["Black"]


class TestPoliceViolenceEndpoint:
    @pytest.mark.asyncio
    async def test_returns_200_with_explore_response(self, override_auth):
        app = override_auth
        from d4bl.infra.database import get_db

        mock_result = MagicMock()
        mock_result.mappings.return_value.all.return_value = [
            {"state": "MS", "race": "Black", "year": 2022, "count": 15}
        ]

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        async def override_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_get_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/api/explore/police-violence",
                params={"state": "MS", "year": 2022},
            )

        assert response.status_code == 200
        data = response.json()
        assert len(data["rows"]) == 1
        assert data["rows"][0]["state_fips"] == "28"
        assert data["rows"][0]["value"] == 15.0
        assert data["rows"][0]["metric"] == "incidents"
        assert data["rows"][0]["race"] == "Black"
        assert data["available_races"] == ["Black"]


class TestAllExploreEndpointsStandardShape:
    """Verify all 8 explore endpoints return the standardized ExploreResponse shape."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("path", [
        "/api/explore/cdc",
        "/api/explore/epa",
        "/api/explore/fbi",
        "/api/explore/bls",
        "/api/explore/hud",
        "/api/explore/usda",
        "/api/explore/doe",
        "/api/explore/police-violence",
    ])
    async def test_explore_endpoint_returns_standard_shape(self, override_auth, path):
        """All explore endpoints return ExploreResponse shape even with empty data."""
        app = override_auth
        from d4bl.infra.database import get_db

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_result.mappings.return_value.all.return_value = []

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        async def override_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_get_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.get(path)

        assert res.status_code == 200, f"{path} returned {res.status_code}: {res.text}"
        body = res.json()
        assert isinstance(body["rows"], list), f"{path}: rows should be a list"
        assert "national_average" in body, f"{path}: missing national_average"
        assert isinstance(body["available_metrics"], list), f"{path}: available_metrics should be list"
        assert isinstance(body["available_years"], list), f"{path}: available_years should be list"
        assert isinstance(body["available_races"], list), f"{path}: available_races should be list"


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

