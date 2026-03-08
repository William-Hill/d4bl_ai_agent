import uuid
from d4bl_pipelines.quality.lineage import build_lineage_record


def test_build_lineage_record():
    run_id = uuid.uuid4()
    record = build_lineage_record(
        ingestion_run_id=run_id,
        target_table="census_indicators",
        record_id=uuid.uuid4(),
        source_url="https://api.census.gov/data/2022/acs/acs5",
        source_hash="abc123",
        transformation={"steps": ["fetch", "compute_rate", "upsert"]},
        quality_score=4.0,
        coverage_metadata={"geography": {"covered": ["AL"]}},
        bias_flags={"demographic_gaps": ["Asian data absent"]},
    )

    assert record["ingestion_run_id"] == run_id
    assert record["target_table"] == "census_indicators"
    assert record["quality_score"] == 4.0
    assert "demographic_gaps" in record["bias_flags"]


def test_build_lineage_record_minimal():
    record = build_lineage_record(
        ingestion_run_id=uuid.uuid4(),
        target_table="policy_bills",
        record_id=uuid.uuid4(),
    )
    assert record["quality_score"] is None
    assert record["bias_flags"] is None
