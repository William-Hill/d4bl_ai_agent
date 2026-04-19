"""Unit tests for related-documents API query parsing helpers."""

from d4bl.app.api import (
    _RELATED_DOC_CONTENT_TYPES,
    _normalize_metric_for_document_search,
    _parse_related_doc_types_param,
)

_EXPECTED_ALL_TYPES = sorted(_RELATED_DOC_CONTENT_TYPES)


def test_parse_types_default_all():
    assert _parse_related_doc_types_param(None) == _EXPECTED_ALL_TYPES
    assert _parse_related_doc_types_param("") == _EXPECTED_ALL_TYPES
    assert _parse_related_doc_types_param("   ") == _EXPECTED_ALL_TYPES


def test_parse_types_filters_unknown():
    assert _parse_related_doc_types_param("policy_bill,nope") == ["policy_bill"]


def test_parse_types_all_invalid_returns_empty():
    assert _parse_related_doc_types_param("nope,bad") == []


def test_parse_types_multiple():
    got = _parse_related_doc_types_param("scraped_web, policy_bill ")
    assert got == ["policy_bill", "scraped_web"]


def test_normalize_metric_empty():
    assert _normalize_metric_for_document_search(None) == (False, "", "")
    assert _normalize_metric_for_document_search("   ") == (False, "", "")


def test_normalize_metric_slug_and_human():
    has, slug, human = _normalize_metric_for_document_search("Median_Household_Income")
    assert has is True
    assert slug == "median_household_income"
    assert human == "median household income"


def test_normalize_metric_strips_unsafe_chars():
    has, slug, _ = _normalize_metric_for_document_search("test%drop")
    assert has is True
    assert slug == "testdrop"
