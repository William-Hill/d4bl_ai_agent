from __future__ import annotations

import json
import re
from typing import Any, Dict


def parse_first_json_block(text: str) -> Dict[str, Any]:
    json_match = re.search(r"\{[^{}]*\}", text, re.DOTALL)
    if not json_match:
        return {}
    try:
        return json.loads(json_match.group())
    except json.JSONDecodeError:
        return {}


def default_quality_scores(scores: Dict[str, Any], fallback_text: str) -> Dict[str, Any]:
    scores.setdefault("relevance", 3.0)
    scores.setdefault("completeness", 3.0)
    scores.setdefault("accuracy", 3.0)
    scores.setdefault("bias", 3.0)
    scores.setdefault("clarity", 3.0)
    scores.setdefault(
        "overall",
        sum([
            scores.get("relevance", 3.0),
            scores.get("completeness", 3.0),
            scores.get("accuracy", 3.0),
            scores.get("bias", 3.0),
            scores.get("clarity", 3.0),
        ]) / 5.0,
    )
    scores.setdefault("feedback", fallback_text[:500])
    return scores


def parse_bias_score(text: str) -> tuple[float, str]:
    data = parse_first_json_block(text)
    if data:
        try:
            score = float(data.get("bias_score", 3.0))
            feedback = data.get("feedback", text)
            return score, feedback
        except (ValueError, TypeError):
            pass

    score_match = re.search(r"bias[_\s]?score[:\s]+([0-9.]+)", text, re.IGNORECASE)
    if score_match:
        try:
            return float(score_match.group(1)), text
        except ValueError:
            return 3.0, text

    return 3.0, text
