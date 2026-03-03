from __future__ import annotations

import json
import re
from typing import Any, Dict


def keyword_relevance(query: str, text: str) -> float:
    """Score relevance of *text* to *query* via simple keyword overlap (1.0-5.0)."""
    query_words = set(query.lower().split())
    if not query_words:
        return 3.0
    text_lower = text.lower()
    matches = sum(1 for word in query_words if word in text_lower and len(word) > 3)
    return max(1.0, min(5.0, (matches / len(query_words)) * 5))


def parse_first_json_block(text: str) -> Dict[str, Any]:
    json_match = re.search(r"\{[^{}]*\}", text, re.DOTALL)
    if not json_match:
        return {}
    try:
        return json.loads(json_match.group())
    except json.JSONDecodeError:
        return {}


def default_quality_scores(scores: Dict[str, Any], fallback_text: str) -> Dict[str, Any]:
    """Ensure all scores are floats and calculate overall score."""
    # Convert all score values to float, defaulting to 3.0 if invalid
    def to_float(value: Any, default: float = 3.0) -> float:
        try:
            return float(value)
        except (ValueError, TypeError):
            return default
    
    scores["relevance"] = to_float(scores.get("relevance"), 3.0)
    scores["completeness"] = to_float(scores.get("completeness"), 3.0)
    scores["accuracy"] = to_float(scores.get("accuracy"), 3.0)
    scores["bias"] = to_float(scores.get("bias"), 3.0)
    scores["clarity"] = to_float(scores.get("clarity"), 3.0)
    
    # Calculate overall as average of all scores
    scores["overall"] = (
        scores["relevance"] +
        scores["completeness"] +
        scores["accuracy"] +
        scores["bias"] +
        scores["clarity"]
    ) / 5.0
    
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


def parse_label_score(text: str, mapping: Dict[str, float], default_score: float = 3.0) -> tuple[float, str]:
    data = parse_first_json_block(text)
    if data:
        label = str(data.get("label", "")).strip().upper()
        if label in mapping:
            return mapping[label], data.get("explanation", text)

    upper_text = text.upper()
    for label, score in mapping.items():
        if label in upper_text:
            return score, text

    return default_score, text
