import inspect
from unittest.mock import AsyncMock, MagicMock

import pytest

from d4bl_pipelines.assets.apis.census_acs import (
    _fetch_acs,
    census_acs_county_indicators,
    census_acs_indicators,
)
from d4bl_pipelines.schedules import STATIC_SCHEDULES


def _make_mock_session(json_data):
    """Build a mock aiohttp session with async context manager."""
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = AsyncMock(return_value=json_data)

    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=mock_resp)
    ctx.__aexit__ = AsyncMock(return_value=False)

    mock_session = MagicMock()
    mock_session.get.return_value = ctx
    return mock_session


def test_census_acs_asset_exists():
    """The census_acs_indicators asset should be importable."""
    assert census_acs_indicators is not None


def test_fetch_acs_accepts_geography_param():
    """_fetch_acs should accept a geography keyword argument."""
    sig = inspect.signature(_fetch_acs)
    assert "geography" in sig.parameters
    assert sig.parameters["geography"].default == "state:*"


@pytest.mark.asyncio
async def test_fetch_acs_state_params():
    """_fetch_acs should set for=state:06 when filtering."""
    mock_session = _make_mock_session(
        [["NAME", "state"], ["CA", "06"]]
    )
    await _fetch_acs(
        mock_session, 2022, ["B01001_001E"], state_fips="06"
    )
    params = mock_session.get.call_args.kwargs["params"]
    assert params["for"] == "state:06"
    assert "in" not in params


@pytest.mark.asyncio
async def test_fetch_acs_county_params():
    """_fetch_acs should set for=county:* for nationwide."""
    mock_session = _make_mock_session(
        [["NAME", "state", "county"], ["X", "01", "001"]]
    )
    await _fetch_acs(
        mock_session, 2022, ["B01001_001E"], geography="county:*"
    )
    params = mock_session.get.call_args.kwargs["params"]
    assert params["for"] == "county:*"
    assert "in" not in params


@pytest.mark.asyncio
async def test_fetch_acs_county_with_state_filter():
    """_fetch_acs should add in=state:06 for county + state_fips."""
    mock_session = _make_mock_session(
        [["NAME", "state", "county"], ["X", "06", "001"]]
    )
    await _fetch_acs(
        mock_session, 2022, ["B01001_001E"],
        state_fips="06", geography="county:*",
    )
    params = mock_session.get.call_args.kwargs["params"]
    assert params["for"] == "county:*"
    assert params["in"] == "state:06"


def test_census_acs_asset_has_metadata():
    """Asset should have group and description metadata."""
    spec = census_acs_indicators.specs_by_key
    key = next(iter(spec))
    assert key.path[-1] == "census_acs_indicators"


def test_census_acs_county_asset_exists():
    """The census_acs_county_indicators asset should be importable."""
    assert census_acs_county_indicators is not None


def test_census_acs_county_asset_has_metadata():
    """County asset should have correct group and description metadata."""
    spec = census_acs_county_indicators.specs_by_key
    key = next(iter(spec))
    assert key.path[-1] == "census_acs_county_indicators"


def test_county_schedule_registered():
    """County asset should have a static schedule."""
    assert "census_acs_county_indicators" in STATIC_SCHEDULES
