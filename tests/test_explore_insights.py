"""Tests for /api/explore/state-summary endpoint."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient


def _make_summary_row(
    *,
    source="census",
    state_fips="28",
    state_name="Mississippi",
    metric="median_household_income",
    race="total",
    year=2022,
    value=45000.0,
    sample_size=None,
):
    row = MagicMock()
    row.source = source
    row.state_fips = state_fips
    row.state_name = state_name
    row.metric = metric
    row.race = race
    row.year = year
    row.value = value
    row.sample_size = sample_size
    return row


class TestStateSummaryRankPercentile:
    """Rank/percentile computation with 3 mock states."""

    @pytest.mark.asyncio
    async def test_rank_and_percentile_computation(self, override_auth):
        app = override_auth
        from d4bl.infra.database import get_db

        # 3 states: CA=80000, NY=60000, MS=45000
        rows_total = [
            _make_summary_row(state_fips="06", state_name="California", value=80000),
            _make_summary_row(state_fips="36", state_name="New York", value=60000),
            _make_summary_row(state_fips="28", state_name="Mississippi", value=45000),
        ]
        # No race-disaggregated data
        rows_race: list = []

        call_count = {"n": 0}

        async def _mock_execute(stmt, *args, **kwargs):
            result = MagicMock()
            if call_count["n"] == 0:
                # First call: all states with race=total
                result.scalars.return_value.all.return_value = rows_total
            else:
                # Second call: race != total for target state
                result.scalars.return_value.all.return_value = rows_race
            call_count["n"] += 1
            return result

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(side_effect=_mock_execute)

        async def override_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_get_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                "/api/explore/state-summary",
                params={
                    "source": "census",
                    "state_fips": "28",
                    "metric": "median_household_income",
                },
            )

        assert resp.status_code == 200
        data = resp.json()

        assert data["state_fips"] == "28"
        assert data["state_name"] == "Mississippi"
        assert data["national_rank"] == 3  # lowest of 3
        assert data["national_rank_total"] == 3
        # Percentile: 1 out of 3 states <= 45000 => 33.3%
        assert data["percentile"] == pytest.approx(33.3, abs=0.1)
        # National average: (80000+60000+45000)/3
        expected_avg = round((80000 + 60000 + 45000) / 3, 4)
        assert data["national_average"] == pytest.approx(expected_avg, abs=0.01)
        assert data["racial_gap"] is None
        assert data["source"] == "census"
        assert data["year"] == 2022

    @pytest.mark.asyncio
    async def test_racial_gap_returned(self, override_auth):
        app = override_auth
        from d4bl.infra.database import get_db

        rows_total = [
            _make_summary_row(state_fips="28", value=45000),
        ]
        rows_race = [
            _make_summary_row(state_fips="28", race="white", value=55000),
            _make_summary_row(state_fips="28", race="black", value=30000),
        ]

        call_count = {"n": 0}

        async def _mock_execute(stmt, *args, **kwargs):
            result = MagicMock()
            if call_count["n"] == 0:
                result.scalars.return_value.all.return_value = rows_total
            else:
                result.scalars.return_value.all.return_value = rows_race
            call_count["n"] += 1
            return result

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(side_effect=_mock_execute)

        async def override_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_get_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                "/api/explore/state-summary",
                params={
                    "source": "census",
                    "state_fips": "28",
                    "metric": "median_household_income",
                },
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["racial_gap"] is not None
        gap = data["racial_gap"]
        assert len(gap["groups"]) == 2
        assert gap["max_ratio"] == pytest.approx(1.83, abs=0.01)
        assert "white" in gap["max_ratio_label"]
        assert "black" in gap["max_ratio_label"]


class TestStateSummary404:
    """Test 404 when state or data not found."""

    @pytest.mark.asyncio
    async def test_404_no_data(self, override_auth):
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
            resp = await client.get(
                "/api/explore/state-summary",
                params={
                    "source": "census",
                    "state_fips": "99",
                    "metric": "nonexistent",
                },
            )

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_404_state_not_in_results(self, override_auth):
        app = override_auth
        from d4bl.infra.database import get_db

        # Data exists for other states but not the requested one
        rows_total = [
            _make_summary_row(state_fips="06", state_name="California", value=80000),
        ]

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = rows_total

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        async def override_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_get_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                "/api/explore/state-summary",
                params={
                    "source": "census",
                    "state_fips": "28",
                    "metric": "median_household_income",
                },
            )

        assert resp.status_code == 404


class TestExploreQuery:
    """Tests for POST /api/explore/query endpoint."""

    @pytest.mark.asyncio
    async def test_explore_query_success(self, override_auth, monkeypatch):
        app = override_auth
        from d4bl.infra.database import get_db

        mock_db = AsyncMock()

        async def override_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_get_db

        # Mock the query engine
        mock_result = MagicMock()
        mock_result.answer = "Test answer about poverty rates"

        mock_engine = MagicMock()
        mock_engine.query = AsyncMock(return_value=mock_result)

        import d4bl.app.explore_insights as ei_mod

        monkeypatch.setattr(ei_mod, "_get_query_engine", lambda: mock_engine)

        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/explore/query",
                json={
                    "question": "Which states improved?",
                    "context": {
                        "source": "census",
                        "metric": "poverty_rate",
                        "state_fips": "28",
                    },
                },
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["answer"] == "Test answer about poverty rates"
        assert data["data"] is None
        assert data["visualization_hint"] is None

        # Verify the augmented question was passed correctly
        call_kwargs = mock_engine.query.call_args
        question_arg = call_kwargs.kwargs.get(
            "question", call_kwargs.args[0] if call_kwargs.args else ""
        )
        assert "Data source: census" in question_arg
        assert "Metric: poverty_rate" in question_arg
        assert "State FIPS: 28" in question_arg

    @pytest.mark.asyncio
    async def test_explore_query_503_on_failure(
        self, override_auth, monkeypatch
    ):
        app = override_auth
        from d4bl.infra.database import get_db

        mock_db = AsyncMock()

        async def override_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_get_db

        mock_engine = MagicMock()
        mock_engine.query = AsyncMock(
            side_effect=RuntimeError("LLM unavailable")
        )

        import d4bl.app.explore_insights as ei_mod

        monkeypatch.setattr(ei_mod, "_get_query_engine", lambda: mock_engine)

        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/explore/query",
                json={
                    "question": "Tell me about this data",
                    "context": {"source": "cdc"},
                },
            )

        assert resp.status_code == 503
