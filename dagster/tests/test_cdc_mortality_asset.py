# dagster/tests/test_cdc_mortality_asset.py
"""Tests for CDC mortality ingestion assets."""


def test_cdc_mortality_model_importable():
    """CdcMortality model should be importable from database module."""
    from d4bl.infra.database import CdcMortality

    assert CdcMortality.__tablename__ == "cdc_mortality"


def test_cdc_mortality_model_has_unique_constraint():
    """CdcMortality should have a unique constraint for idempotent upserts."""
    from d4bl.infra.database import CdcMortality

    constraint_names = [
        c.name for c in CdcMortality.__table_args__
        if hasattr(c, "name") and c.name and c.name.startswith("uq_")
    ]
    assert len(constraint_names) == 1
    assert "uq_cdc_mortality_key" in constraint_names


def test_cdc_mortality_state_asset_exists():
    """The cdc_mortality_state asset should be importable."""
    from d4bl_pipelines.assets.apis.cdc_mortality import cdc_mortality_state

    assert cdc_mortality_state is not None


def test_cdc_mortality_state_asset_group():
    """Asset should belong to the 'apis' group."""
    from d4bl_pipelines.assets.apis.cdc_mortality import cdc_mortality_state

    spec = cdc_mortality_state.specs_by_key
    key = next(iter(spec))
    assert key.path[-1] == "cdc_mortality_state"
    assert spec[key].group_name == "apis"


def test_state_name_to_fips_mapping():
    """State name to FIPS mapping should cover all 50 states + DC."""
    from d4bl_pipelines.assets.apis.cdc_mortality import STATE_NAME_TO_FIPS

    assert len(STATE_NAME_TO_FIPS) >= 51
    assert STATE_NAME_TO_FIPS["Alabama"] == "01"
    assert STATE_NAME_TO_FIPS["District of Columbia"] == "11"
    assert STATE_NAME_TO_FIPS["Wyoming"] == "56"


def test_cdc_mortality_national_race_asset_exists():
    """The cdc_mortality_national_race asset should be importable."""
    from d4bl_pipelines.assets.apis.cdc_mortality import cdc_mortality_national_race

    assert cdc_mortality_national_race is not None


def test_cdc_mortality_national_race_asset_group():
    """Asset should belong to the 'apis' group."""
    from d4bl_pipelines.assets.apis.cdc_mortality import cdc_mortality_national_race

    spec = cdc_mortality_national_race.specs_by_key
    key = next(iter(spec))
    assert key.path[-1] == "cdc_mortality_national_race"
    assert spec[key].group_name == "apis"


def test_race_map_covers_standard_categories():
    """RACE_MAP should map to D4BL standard race values."""
    from d4bl_pipelines.assets.apis.cdc_mortality import RACE_MAP

    d4bl_races = set(RACE_MAP.values())
    assert "black" in d4bl_races
    assert "white" in d4bl_races
    assert "hispanic" in d4bl_races
    assert "asian" in d4bl_races
    assert "native_american" in d4bl_races


import pytest


@pytest.mark.integration
def test_cdc_mortality_state_soda_api_reachable():
    """Verify the SODA API endpoint returns data (requires network)."""
    import aiohttp
    import asyncio

    async def _fetch():
        url = "https://data.cdc.gov/resource/bi63-dtpu.json"
        params = {"$limit": "2", "$where": "year='2017' AND state='Alabama'"}
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as resp:
                assert resp.status == 200
                data = await resp.json()
                assert len(data) > 0
                assert "state" in data[0]
                assert "cause_name" in data[0]
                return data

    asyncio.run(_fetch())


@pytest.mark.integration
def test_cdc_mortality_national_race_soda_api_reachable():
    """Verify the excess deaths SODA API returns data (requires network)."""
    import aiohttp
    import asyncio

    async def _fetch():
        url = "https://data.cdc.gov/resource/m74n-4hbs.json"
        params = {
            "$limit": "2",
            "$where": "sex='All Sexes'",
            "$select": "mmwryear,raceethnicity,deaths_unweighted",
        }
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as resp:
                assert resp.status == 200
                data = await resp.json()
                assert len(data) > 0
                assert "raceethnicity" in data[0]
                return data

    asyncio.run(_fetch())
