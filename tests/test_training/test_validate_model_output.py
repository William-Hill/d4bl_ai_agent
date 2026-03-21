"""Tests for model output validation helpers."""

from scripts.training.validate_model_output import (
    ValidationResult,
    validate_evaluator_output,
    validate_explainer_output,
    validate_parser_output,
)


class TestValidationResult:
    def test_valid_result(self):
        r = ValidationResult(valid=True, parsed={"key": "val"}, errors=[])
        assert r.valid
        assert r.parsed == {"key": "val"}

    def test_invalid_result(self):
        r = ValidationResult(valid=False, parsed=None, errors=["bad json"])
        assert not r.valid
        assert "bad json" in r.errors


class TestParserValidation:
    def test_valid_output(self):
        raw = '{"intent": "compare", "metrics": ["poverty_rate"], "geographies": ["Alabama"]}'
        result = validate_parser_output(raw)
        assert result.valid
        assert result.parsed["intent"] == "compare"

    def test_invalid_json(self):
        result = validate_parser_output("not json at all")
        assert not result.valid
        assert any("JSON" in e for e in result.errors)

    def test_missing_intent(self):
        raw = '{"metrics": ["poverty_rate"]}'
        result = validate_parser_output(raw)
        assert not result.valid
        assert any("intent" in e for e in result.errors)

    def test_invalid_intent_value(self):
        raw = '{"intent": "invalid_type", "metrics": ["poverty_rate"]}'
        result = validate_parser_output(raw)
        assert not result.valid

    def test_empty_metrics_allowed(self):
        raw = '{"intent": "lookup", "metrics": []}'
        result = validate_parser_output(raw)
        assert result.valid

    def test_extracts_json_from_wrapper_text(self):
        raw = 'Here is the result:\n{"intent": "lookup", "metrics": ["income"]}\nDone.'
        result = validate_parser_output(raw)
        assert result.valid


class TestExplainerValidation:
    def test_valid_output(self):
        raw = '{"narrative": "Poverty rates in Alabama...", "structural_context": "Historical redlining...", "policy_connection": "HB-123..."}'
        result = validate_explainer_output(raw)
        assert result.valid

    def test_invalid_json(self):
        result = validate_explainer_output("plain text narrative")
        assert not result.valid

    def test_missing_narrative(self):
        raw = '{"structural_context": "something"}'
        result = validate_explainer_output(raw)
        assert not result.valid
        assert any("narrative" in e for e in result.errors)


class TestEvaluatorValidation:
    def test_valid_output(self):
        raw = '{"score": 4, "explanation": "Good alignment", "issues": []}'
        result = validate_evaluator_output(raw)
        assert result.valid

    def test_score_out_of_range(self):
        raw = '{"score": 6, "explanation": "test", "issues": []}'
        result = validate_evaluator_output(raw)
        assert not result.valid
        assert any("score" in e for e in result.errors)

    def test_score_zero_invalid(self):
        raw = '{"score": 0, "explanation": "test", "issues": []}'
        result = validate_evaluator_output(raw)
        assert not result.valid

    def test_missing_score(self):
        raw = '{"explanation": "test", "issues": []}'
        result = validate_evaluator_output(raw)
        assert not result.valid
