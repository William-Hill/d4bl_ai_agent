"""Tests verifying the Census ACS endpoint returns ExploreResponse shape."""
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient


class TestCensusUnifiedResponse:
    """Verify /api/explore/indicators returns ExploreResponse (not list[IndicatorItem])."""

    @pytest.mark.asyncio
    async def test_response_has_explore_response_keys(self, override_auth):
        """Response must have rows, national_average, available_metrics/years/races."""
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
            response = await client.get("/api/explore/indicators")

        assert response.status_code == 200
        data = response.json()

        # ExploreResponse shape
        assert "rows" in data
        assert "national_average" in data
        assert "available_metrics" in data
        assert "available_years" in data
        assert "available_races" in data

    @pytest.mark.asyncio
    async def test_each_row_has_explore_row_fields(self, override_auth):
        """Each row has state_fips, state_name, value, metric, year, race."""
        app = override_auth
        from d4bl.infra.database import get_db

        mock_row = MagicMock()
        mock_row.fips_code = "06"
        mock_row.geography_name = "California"
        mock_row.state_fips = "06"
        mock_row.geography_type = "state"
        mock_row.year = 2022
        mock_row.race = "total"
        mock_row.metric = "poverty_rate"
        mock_row.value = 11.8
        mock_row.margin_of_error = 0.3

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_row]

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        async def override_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_get_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/explore/indicators")

        data = response.json()
        row = data["rows"][0]
        assert row["state_fips"] == "06"
        assert row["state_name"] == "California"
        assert row["value"] == 11.8
        assert row["metric"] == "poverty_rate"
        assert row["year"] == 2022
        assert row["race"] == "total"

    @pytest.mark.asyncio
    async def test_national_average_computed(self, override_auth):
        """national_average should be the mean of row values."""
        app = override_auth
        from d4bl.infra.database import get_db

        rows = []
        for fips, name, val in [("28", "Mississippi", 40.0), ("06", "California", 60.0)]:
            r = MagicMock()
            r.fips_code = fips
            r.geography_name = name
            r.state_fips = fips
            r.geography_type = "state"
            r.year = 2022
            r.race = "total"
            r.metric = "homeownership_rate"
            r.value = val
            r.margin_of_error = None
            rows.append(r)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = rows

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        async def override_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_get_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/explore/indicators")

        data = response.json()
        assert data["national_average"] == 50.0

    @pytest.mark.asyncio
    async def test_empty_response(self, override_auth):
        """Empty DB returns empty rows and null average."""
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
        data = response.json()
        assert data["rows"] == []
        assert data["national_average"] is None
        assert data["available_metrics"] == []
        assert data["available_years"] == []
        assert data["available_races"] == []

    @pytest.mark.asyncio
    async def test_distinct_values_populated(self, override_auth):
        """available_metrics, available_years, available_races are populated correctly."""
        app = override_auth
        from d4bl.infra.database import get_db

        rows = []
        for race in ["black", "white", "total"]:
            r = MagicMock()
            r.fips_code = "28"
            r.geography_name = "Mississippi"
            r.state_fips = "28"
            r.geography_type = "state"
            r.year = 2022
            r.race = race
            r.metric = "homeownership_rate"
            r.value = 45.0
            r.margin_of_error = None
            rows.append(r)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = rows

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        async def override_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_get_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/explore/indicators")

        data = response.json()
        assert data["available_metrics"] == ["homeownership_rate"]
        assert data["available_years"] == [2022]
        assert sorted(data["available_races"]) == ["black", "total", "white"]

    @pytest.mark.asyncio
    async def test_db_error_returns_500(self, override_auth):
        """DB failure returns 500, not an unhandled exception."""
        app = override_auth
        from d4bl.infra.database import get_db

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(side_effect=Exception("db connection lost"))

        async def override_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_get_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/explore/indicators")

        assert response.status_code == 500
