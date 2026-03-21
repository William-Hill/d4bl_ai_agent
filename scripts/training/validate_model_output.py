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
    """Try to parse JSON from raw text, including extracting from wrapper text."""
    raw = raw.strip()
    try:
        return json.loads(raw), None
    except json.JSONDecodeError:
        pass
    match = _JSON_RE.search(raw)
    if match:
        try:
            return json.loads(match.group()), None
        except json.JSONDecodeError:
            pass
    return None, "Invalid JSON: could not parse response"


def validate_parser_output(raw: str) -> ValidationResult:
    """Validate query parser model output."""
    parsed, err = _extract_json(raw)
    if err:
        return ValidationResult(valid=False, parsed=None, errors=[err])

    errors = []
    if "intent" not in parsed:
        errors.append("Missing required field: intent")
    elif parsed["intent"] not in _VALID_INTENTS:
        errors.append(
            f"Invalid intent '{parsed['intent']}', must be one of: {_VALID_INTENTS}"
        )

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
    """Validate evaluator model output."""
    parsed, err = _extract_json(raw)
    if err:
        return ValidationResult(valid=False, parsed=None, errors=[err])

    errors = []
    if "score" not in parsed:
        errors.append("Missing required field: score")
    elif not isinstance(parsed["score"], (int, float)) or not (1 <= parsed["score"] <= 5):
        errors.append(f"Invalid score {parsed.get('score')}: must be 1-5")

    return ValidationResult(valid=len(errors) == 0, parsed=parsed, errors=errors)
