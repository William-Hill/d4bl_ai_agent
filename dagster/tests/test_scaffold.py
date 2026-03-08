# dagster/tests/test_scaffold.py
from d4bl_pipelines import defs


def test_definitions_load():
    """Verify Dagster definitions load without error."""
    assert defs is not None
    assert defs.get_all_asset_specs() is not None
