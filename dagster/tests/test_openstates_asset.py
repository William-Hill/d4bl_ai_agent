from d4bl_pipelines.assets.apis.openstates import (
    openstates_bills,
    FOCUS_SUBJECTS,
    STATE_MAP,
    STATUS_MAP,
    _map_status,
)


def test_openstates_asset_exists():
    """The openstates_bills asset should be importable."""
    assert openstates_bills is not None


def test_openstates_asset_has_metadata():
    """Asset should have group and description metadata."""
    spec = openstates_bills.specs_by_key
    key = next(iter(spec))
    assert key.path[-1] == "openstates_bills"


def test_openstates_asset_group_name():
    """Asset should belong to the 'apis' group."""
    spec = openstates_bills.specs_by_key
    key = next(iter(spec))
    assert spec[key].group_name == "apis"


def test_openstates_asset_has_description():
    """Asset should have a non-empty description."""
    spec = openstates_bills.specs_by_key
    key = next(iter(spec))
    assert spec[key].description
    assert "policy bills" in spec[key].description.lower()


def test_focus_subjects_non_empty():
    """FOCUS_SUBJECTS should have expected topics."""
    assert len(FOCUS_SUBJECTS) == 7
    assert "housing" in FOCUS_SUBJECTS
    assert "health care" in FOCUS_SUBJECTS


def test_state_map_has_50_states():
    """STATE_MAP should cover all 50 US states."""
    assert len(STATE_MAP) == 50


def test_map_status_known():
    """Known status strings should map correctly."""
    assert _map_status("Introduced") == "introduced"
    assert _map_status("Passed") == "passed"
    assert _map_status("Signed") == "signed"
    assert _map_status("Vetoed") == "failed"
    assert _map_status("Dead") == "failed"


def test_map_status_unknown():
    """Unknown or None status should return 'other'."""
    assert _map_status(None) == "other"
    assert _map_status("some random text") == "other"


def test_map_status_partial_match():
    """Status mapping should match substrings."""
    assert _map_status("In Committee") == "introduced"
    assert _map_status("Passed Upper") == "passed"
    assert _map_status("Referred to Committee") == "introduced"
