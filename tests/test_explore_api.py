"""Tests for /api/explore/* endpoints."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from d4bl.app.api import app
from d4bl.infra.database import get_db


class TestIndicatorsEndpoint:
    @pytest.mark.asyncio
    async def test_returns_200_with_explore_response(self, override_auth):
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
        assert "rows" in data
        assert "national_average" in data
        assert "available_metrics" in data
        assert "available_years" in data
        assert "available_races" in data
        assert len(data["rows"]) == 1
        assert data["rows"][0]["state_fips"] == "28"
        assert data["rows"][0]["state_name"] == "Mississippi"
        assert data["rows"][0]["value"] == 43.2
        assert data["rows"][0]["metric"] == "homeownership_rate"
        assert data["rows"][0]["year"] == 2022
        assert data["rows"][0]["race"] == "black"
        assert data["national_average"] == 43.2
        assert data["available_metrics"] == ["homeownership_rate"]
        assert data["available_years"] == [2022]
        assert data["available_races"] == ["black"]

    @pytest.mark.asyncio
    async def test_returns_empty_rows_when_no_data(self, override_auth):
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

        mock_row = MagicMock()
        mock_row.state_fips = "06"
        mock_row.state_name = "California"
        mock_row.value = 10.5
        mock_row.metric = "PM2.5"
        mock_row.year = 2022
        mock_row.race = "total"

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
        assert data["available_races"] == ["total"]


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
            {
                "state_fips": "28",
                "avg_value": 0.45,
                "indicator": "Dissimilarity Index",
                "year": 2020,
            }
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

        mock_row = MagicMock()
        mock_row.state_fips = "28"
        mock_row.state_name = "Mississippi"
        mock_row.value = 22.3
        mock_row.metric = "Low Access"
        mock_row.year = 2019
        mock_row.race = "total"

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
                "/api/explore/usda",
                params={"state_fips": "28"},
            )

        assert response.status_code == 200
        data = response.json()
        assert len(data["rows"]) == 1
        assert data["rows"][0]["value"] == 22.3
        assert data["rows"][0]["metric"] == "Low Access"
        assert data["available_races"] == ["total"]


class TestDoeEndpoint:
    @pytest.mark.asyncio
    async def test_returns_200_with_explore_response(self, override_auth):
        app = override_auth
        from d4bl.infra.database import get_db

        mock_row = MagicMock()
        mock_row.state_fips = "28"
        mock_row.state_name = "Mississippi"
        mock_row.value = 3.5
        mock_row.metric = "Suspensions"
        mock_row.year = 2020
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
                "/api/explore/doe",
                params={"metric": "Suspensions"},
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
    async def test_returns_200_with_race_and_total_rows(self, override_auth):
        app = override_auth
        from d4bl.infra.database import get_db

        # Per-race query result
        mock_race_result = MagicMock()
        mock_race_result.mappings.return_value.all.return_value = [
            {"state": "MS", "race": "Black", "year": 2022, "count": 15}
        ]
        # State-total query result
        mock_total_result = MagicMock()
        mock_total_result.mappings.return_value.all.return_value = [
            {"state": "MS", "year": 2022, "count": 20}
        ]

        mock_freshness = MagicMock()
        mock_freshness.scalar.return_value = None

        real_results = [mock_race_result, mock_total_result]
        call_idx = {"i": 0}

        async def _mock_execute(stmt, *a, **kw):
            s = str(stmt)
            if "ingestion_run" in s.lower():
                return mock_freshness
            result = real_results[call_idx["i"]]
            call_idx["i"] += 1
            return result

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(side_effect=_mock_execute)

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
        assert len(data["rows"]) == 2  # 1 race + 1 total
        race_row = [r for r in data["rows"] if r["race"] == "Black"][0]
        total_row = [r for r in data["rows"] if r["race"] == "total"][0]
        assert race_row["state_fips"] == "28"
        assert race_row["value"] == 15.0
        assert total_row["value"] == 20.0
        assert "total" in data["available_races"]


class TestCensusDemographicsEndpoint:
    @pytest.mark.asyncio
    async def test_returns_200_with_explore_response(self, override_auth):
        app = override_auth
        from d4bl.infra.database import get_db

        mock_row = MagicMock()
        mock_row.state_fips = "28"
        mock_row.state_name = "Mississippi"
        mock_row.value = 1000000.0
        mock_row.metric = "population"
        mock_row.year = 2020
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
                "/api/explore/census-demographics",
                params={"state_fips": "28", "metric": "population"},
            )

        assert response.status_code == 200
        data = response.json()
        assert len(data["rows"]) == 1
        assert data["rows"][0]["state_fips"] == "28"
        assert data["rows"][0]["state_name"] == "Mississippi"
        assert data["rows"][0]["race"] == "Black"
        assert data["available_races"] == ["Black"]
        assert data["available_years"] == [2020]


class TestCdcMortalityEndpoint:
    @pytest.mark.asyncio
    async def test_returns_200_with_explore_response(self, override_auth):
        app = override_auth
        from d4bl.infra.database import get_db

        mock_row = MagicMock()
        mock_row.state_fips = "28"
        mock_row.state_name = "Mississippi"
        mock_row.age_adjusted_rate = 85.3
        mock_row.cause_of_death = "Heart Disease"
        mock_row.year = 2021
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
                "/api/explore/cdc-mortality",
                params={"state_fips": "28", "cause_of_death": "Heart Disease"},
            )

        assert response.status_code == 200
        data = response.json()
        assert len(data["rows"]) == 1
        assert data["rows"][0]["state_fips"] == "28"
        assert data["rows"][0]["value"] == 85.3
        assert data["rows"][0]["metric"] == "Heart Disease"
        assert data["rows"][0]["race"] == "Black"
        assert data["available_races"] == ["Black"]


class TestBjsEndpoint:
    @pytest.mark.asyncio
    async def test_returns_200_with_explore_response(self, override_auth):
        app = override_auth
        from d4bl.infra.database import get_db

        mock_row = MagicMock()
        mock_row.state_abbrev = "MS"
        mock_row.state_name = "Mississippi"
        mock_row.value = 573.0
        mock_row.metric = "incarceration_rate"
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
                "/api/explore/bjs",
                params={"state_fips": "28", "metric": "incarceration_rate"},
            )

        assert response.status_code == 200
        data = response.json()
        assert len(data["rows"]) == 1
        assert data["rows"][0]["state_fips"] == "28"
        assert data["rows"][0]["state_name"] == "Mississippi"
        assert data["rows"][0]["value"] == 573.0
        assert data["rows"][0]["metric"] == "incarceration_rate"
        assert data["rows"][0]["race"] == "Black"
        assert data["available_races"] == ["Black"]


class TestAllExploreEndpointsStandardShape:
    """Verify all 12 explore endpoints return the standardized ExploreResponse shape."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "path",
        [
            "/api/explore/indicators",
            "/api/explore/cdc",
            "/api/explore/epa",
            "/api/explore/fbi",
            "/api/explore/bls",
            "/api/explore/hud",
            "/api/explore/usda",
            "/api/explore/doe",
            "/api/explore/police-violence",
            "/api/explore/census-demographics",
            "/api/explore/cdc-mortality",
            "/api/explore/bjs",
        ],
    )
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
        assert isinstance(body["available_metrics"], list), (
            f"{path}: available_metrics should be list"
        )
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

        # Build a mock DB that handles freshness check + two real queries.
        # The freshness check may or may not fire (throttled to every 30s),
        # so we use a stateful side_effect that returns freshness results for
        # IngestionRun queries and real results in order for everything else.
        real_results = [mock_result_metrics, mock_result_bills]
        real_idx = {"i": 0}
        mock_freshness_result = MagicMock()
        mock_freshness_result.scalar.return_value = None

        async def _mock_execute(stmt, *args, **kwargs):
            stmt_str = str(stmt)
            if "ingestion_run" in stmt_str.lower():
                return mock_freshness_result
            result = real_results[real_idx["i"]]
            real_idx["i"] += 1
            return result

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(side_effect=_mock_execute)

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


@pytest.fixture
async def user_client(override_auth):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def unauth_client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def override_db(mock_db_session):
    app.dependency_overrides[get_db] = lambda: mock_db_session
    yield mock_db_session
    app.dependency_overrides.pop(get_db, None)


class TestStaffUploadsAvailable:

    @pytest.mark.asyncio
    async def test_available_returns_only_approved_datasource_uploads(
        self, user_client, override_db
    ):
        mock_db = override_db
        rows = [
            {
                "id": "00000000-0000-0000-0000-00000000a001",
                "metadata": {
                    "source_name": "Eviction Rates 2023",
                    "geographic_level": "county",
                    "data_year": 2023,
                    "mapping": {
                        "metric_name": "eviction_rate",
                        "race_column": "race",
                    },
                    "row_count": 3142,
                },
                "reviewed_at": None,
                "uploader_name": "Alice",
            },
        ]
        fetch_result = MagicMock()
        fetch_result.mappings.return_value.all.return_value = rows
        mock_db.execute = AsyncMock(return_value=fetch_result)

        resp = await user_client.get("/api/explore/staff-uploads/available")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert data[0]["metric_name"] == "eviction_rate"
        assert data[0]["has_race"] is True
        assert data[0]["row_count"] == 3142

    @pytest.mark.asyncio
    async def test_available_requires_auth(self, unauth_client):
        resp = await unauth_client.get("/api/explore/staff-uploads/available")
        assert resp.status_code == 401


class TestStaffUploadsExplore:

    @pytest.mark.asyncio
    async def test_returns_explore_response_shape(self, user_client, override_db):
        mock_db = override_db
        # First call: fetch metadata + metric_name.
        meta_result = MagicMock()
        meta_result.mappings.return_value.first.return_value = {
            "source_name": "Eviction Rates 2023",
            "mapping": {"metric_name": "eviction_rate", "race_column": "race"},
        }
        # Second call: aggregated rows.
        rows_result = MagicMock()
        rows_result.mappings.return_value.all.return_value = [
            {"state_fips": "13", "value": 14.3, "race": "Black", "year": 2023},
            {"state_fips": "06", "value": 9.1, "race": None, "year": 2023},
        ]
        mock_db.execute = AsyncMock(side_effect=[meta_result, rows_result])

        resp = await user_client.get(
            "/api/explore/staff-uploads?upload_id=00000000-0000-0000-0000-00000000a001"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["available_metrics"] == ["eviction_rate"]
        assert len(data["rows"]) == 2
        assert data["rows"][0]["metric"] == "eviction_rate"
        assert data["rows"][0]["state_name"]  # non-empty string

    @pytest.mark.asyncio
    async def test_missing_upload_id_returns_422(self, user_client, override_db):
        resp = await user_client.get("/api/explore/staff-uploads")
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_non_approved_upload_returns_404(self, user_client, override_db):
        mock_db = override_db
        meta_result = MagicMock()
        meta_result.mappings.return_value.first.return_value = None
        mock_db.execute = AsyncMock(return_value=meta_result)

        resp = await user_client.get(
            "/api/explore/staff-uploads?upload_id=00000000-0000-0000-0000-00000000dead"
        )
        assert resp.status_code == 404
