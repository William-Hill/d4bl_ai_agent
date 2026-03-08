"""Integration test: verify Dagster definitions load with all assets and resources."""

import uuid

from dagster import validate_run_config
from d4bl_pipelines import defs
from d4bl_pipelines.assets.apis.census_acs import census_acs_indicators
from d4bl_pipelines.quality.lineage import build_lineage_record


def test_all_assets_registered():
    """All expected assets should be in the Definitions."""
    specs = list(defs.resolve_all_asset_specs())
    asset_names = [spec.key.path[-1] for spec in specs]
    assert "census_acs_indicators" in asset_names


def test_resources_configured():
    """Resources should include db_url."""
    resource_defs = defs.resources
    assert "db_url" in resource_defs


def test_lineage_integrates_with_asset_metadata():
    """Lineage records should be buildable from asset output metadata."""
    record = build_lineage_record(
        ingestion_run_id=uuid.uuid4(),
        target_table="census_indicators",
        record_id=uuid.uuid4(),
        source_url="https://api.census.gov/data/2022/acs/acs5",
        source_hash="test_hash",
        quality_score=3.8,
        coverage_metadata={
            "geography": {
                "covered": ["28"],
                "missing": [],
                "level": "state",
            },
            "demographics": {
                "races": ["total", "black", "white", "hispanic"],
            },
            "temporal": {
                "start_year": 2022,
                "end_year": 2022,
                "frequency": "annual",
            },
        },
        bias_flags={
            "source_concentration": "Single source (Census ACS)",
            "methodology_notes": "ACS uses sampling",
        },
    )
    assert record["quality_score"] == 3.8
    assert record["target_table"] == "census_indicators"
    assert "source_concentration" in record["bias_flags"]
