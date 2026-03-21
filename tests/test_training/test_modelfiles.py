"""Tests for Ollama Modelfile content and structure."""

from pathlib import Path

import pytest

MODELS_DIR = Path(__file__).resolve().parent.parent.parent / "models"

MODELFILES = {
    "query-parser": MODELS_DIR / "Modelfile.query-parser",
    "explainer": MODELS_DIR / "Modelfile.explainer",
    "evaluator": MODELS_DIR / "Modelfile.evaluator",
}


class TestModelfileStructure:
    """All Modelfiles must have FROM, PARAMETER, and SYSTEM directives."""

    @pytest.fixture(params=list(MODELFILES.keys()))
    def modelfile(self, request):
        path = MODELFILES[request.param]
        return request.param, path.read_text()

    def test_has_from_directive(self, modelfile):
        name, content = modelfile
        assert content.strip().startswith("FROM "), f"{name}: must start with FROM"

    def test_from_references_gguf(self, modelfile):
        name, content = modelfile
        from_line = next(
            (line for line in content.splitlines() if line.startswith("FROM ")),
            None,
        )
        assert from_line is not None, f"{name}: missing FROM directive"
        assert ".gguf" in from_line, f"{name}: FROM must reference a .gguf file"

    def test_has_temperature(self, modelfile):
        name, content = modelfile
        assert "PARAMETER temperature" in content, f"{name}: must set temperature"

    def test_has_num_ctx(self, modelfile):
        name, content = modelfile
        assert "PARAMETER num_ctx" in content, f"{name}: must set num_ctx"

    def test_has_stop_token(self, modelfile):
        name, content = modelfile
        assert "PARAMETER stop" in content, f"{name}: must set stop token"

    def test_has_system_prompt(self, modelfile):
        name, content = modelfile
        assert "SYSTEM" in content, f"{name}: must have SYSTEM prompt"

    def test_system_requests_json(self, modelfile):
        name, content = modelfile
        assert "JSON" in content, f"{name}: SYSTEM must request JSON output"


class TestModelfileSpecifics:
    """Task-specific parameter validation."""

    @pytest.mark.parametrize("model,param,value", [
        ("query-parser", "temperature", "0.1"),
        ("query-parser", "num_ctx", "2048"),
        ("explainer", "temperature", "0.3"),
        ("explainer", "num_ctx", "4096"),
        ("evaluator", "temperature", "0.1"),
        ("evaluator", "num_ctx", "2048"),
    ])
    def test_parameter_value(self, model, param, value):
        content = MODELFILES[model].read_text()
        assert f"PARAMETER {param} {value}" in content
