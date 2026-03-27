"""Validation helpers for D4BL fine-tuned model outputs.

Each validator parses raw model output (string) and checks for required
fields and value constraints. Used by the registration script and
integration tests.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field


@dataclass
class ValidationResult:
    valid: bool
    parsed: dict | None
    errors: list[str] = field(default_factory=list)


_VALID_INTENTS = {"compare", "trend", "lookup", "aggregate"}
_JSON_RE = re.compile(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", re.DOTALL)


def _extract_json(raw: str) -> tuple[dict | None, str | None]:
    """Try to parse a JSON object from raw text, including extracting from wrapper text."""
    raw = raw.strip()
    try:
        obj = json.loads(raw)
        if not isinstance(obj, dict):
            return None, f"Invalid JSON: expected object, got {type(obj).__name__}"
        return obj, None
    except json.JSONDecodeError:
        pass
    match = _JSON_RE.search(raw)
    if match:
        try:
            obj = json.loads(match.group())
            if isinstance(obj, dict):
                return obj, None
        except json.JSONDecodeError:
            pass
    return None, "Invalid JSON: could not parse response"


def validate_parser_output(raw: str) -> ValidationResult:
    """Validate query parser model output.

    Accepts either the Modelfile schema (intent, metrics, ...) or the
    training data schema (entities, search_queries, data_sources, community_framing).
    """
    parsed, err = _extract_json(raw)
    if err:
        return ValidationResult(valid=False, parsed=None, errors=[err])

    errors = []
    # Accept either schema: Modelfile (intent) or training data (entities)
    has_modelfile_schema = "intent" in parsed
    has_training_schema = False

    if has_modelfile_schema:
        if not isinstance(parsed["intent"], str):
            errors.append(f"intent must be a string, got {type(parsed['intent']).__name__}")
        elif parsed["intent"] not in _VALID_INTENTS:
            errors.append(
                f"Invalid intent '{parsed['intent']}', must be one of: {_VALID_INTENTS}"
            )
    else:
        if "entities" in parsed:
            if not isinstance(parsed["entities"], list):
                errors.append(f"entities must be a list, got {type(parsed['entities']).__name__}")
            else:
                has_training_schema = True
        if "search_queries" in parsed:
            if not isinstance(parsed["search_queries"], list):
                errors.append(f"search_queries must be a list, got {type(parsed['search_queries']).__name__}")
            else:
                has_training_schema = True
        if "data_sources" in parsed and not isinstance(parsed["data_sources"], list):
            errors.append(f"data_sources must be a list, got {type(parsed['data_sources']).__name__}")
        if "community_framing" in parsed and not isinstance(parsed["community_framing"], dict):
            errors.append(f"community_framing must be an object, got {type(parsed['community_framing']).__name__}")
        if not has_training_schema:
            errors.append("Missing required fields: need 'intent' or 'entities'/'search_queries' (as lists)")

    return ValidationResult(valid=len(errors) == 0, parsed=parsed, errors=errors)


def validate_explainer_output(raw: str) -> ValidationResult:
    """Validate data explainer model output."""
    parsed, err = _extract_json(raw)
    if err:
        return ValidationResult(valid=False, parsed=None, errors=[err])

    errors = []
    if "narrative" not in parsed:
        errors.append("Missing required field: narrative")

    return ValidationResult(valid=len(errors) == 0, parsed=parsed, errors=errors)


def validate_evaluator_output(raw: str) -> ValidationResult:
    """Validate evaluator model output.

    Accepts either the Modelfile schema (score, explanation, issues) or the
    training data schema (task-specific fields like bias, relevance, equity_framing).
    """
    parsed, err = _extract_json(raw)
    if err:
        return ValidationResult(valid=False, parsed=None, errors=[err])

    _KNOWN_EVAL_FIELDS = {"score", "bias", "relevance", "equity_framing", "hallucination",
                          "explanation", "issues", "category", "context", "evaluation",
                          "supporting_evidence"}

    errors = []
    if "score" in parsed:
        if isinstance(parsed["score"], bool) or not isinstance(parsed["score"], (int, float)):
            errors.append(f"score must be a number, got {type(parsed['score']).__name__}")
        elif not (1 <= parsed["score"] <= 5):
            errors.append(f"Invalid score {parsed['score']}: must be 1-5")
    if "bias" in parsed and not isinstance(parsed["bias"], (bool, dict)):
        errors.append(f"bias must be a boolean or object, got {type(parsed['bias']).__name__}")
    if "relevance" in parsed and not isinstance(parsed["relevance"], (bool, dict)):
        errors.append(f"relevance must be a boolean or object, got {type(parsed['relevance']).__name__}")
    if "equity_framing" in parsed and not isinstance(parsed["equity_framing"], (dict, str)):
        errors.append(f"equity_framing must be an object or string, got {type(parsed['equity_framing']).__name__}")
    if "explanation" in parsed and not isinstance(parsed["explanation"], str):
        errors.append(f"explanation must be a string, got {type(parsed['explanation']).__name__}")
    if "issues" in parsed and not isinstance(parsed["issues"], list):
        errors.append(f"issues must be a list, got {type(parsed['issues']).__name__}")

    if not errors and not parsed:
        errors.append("Empty JSON object")
    elif not errors and not any(k in _KNOWN_EVAL_FIELDS for k in parsed):
        errors.append(f"No recognized evaluation fields in: {list(parsed.keys())}")

    return ValidationResult(valid=len(errors) == 0, parsed=parsed, errors=errors)
