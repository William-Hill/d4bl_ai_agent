"""
Extract token usage from CrewAI results and estimate LLM cost.

CrewAI's ``CrewOutput.token_usage`` is a Pydantic ``UsageMetrics`` model with:
  total_tokens, prompt_tokens, completion_tokens, cached_prompt_tokens,
  successful_requests

This module converts that into a plain dict suitable for JSONB storage and
adds an ``estimated_cost_usd`` field based on the active LLM provider.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# ---- Per-model pricing (USD per 1 M tokens) ----
# Updated 2026-04. Only the models we actually use are listed.
# Ollama is free (local inference), so cost is always 0.
_PRICING: dict[str, dict[str, float]] = {
    "gemini/gemini-2.5-flash": {"prompt": 0.15, "completion": 0.60},
    "gemini/gemini-2.0-flash": {"prompt": 0.10, "completion": 0.40},
    "gemini/gemini-1.5-flash": {"prompt": 0.075, "completion": 0.30},
    "gemini/gemini-2.5-pro": {"prompt": 1.25, "completion": 10.00},
}

# Fallback pricing when the exact model is not in the table.
_DEFAULT_PRICING = {"prompt": 0.15, "completion": 0.60}


def _estimate_cost(
    prompt_tokens: int,
    completion_tokens: int,
    provider: str,
    model: str,
) -> float:
    """Return estimated cost in USD for the given token counts."""
    if provider == "ollama":
        return 0.0

    # Try exact match first, then prefix match
    pricing = _PRICING.get(model)
    if pricing is None:
        for key in _PRICING:
            if model.startswith(key.split("/")[-1]):
                pricing = _PRICING[key]
                break

    if pricing is None:
        pricing = _DEFAULT_PRICING
        logger.debug("No pricing entry for model=%s, using default", model)

    cost = (prompt_tokens * pricing["prompt"] + completion_tokens * pricing["completion"]) / 1_000_000
    return round(cost, 6)


def extract_usage(crew_result: Any, provider: str = "", model: str = "") -> dict | None:
    """Extract token usage from a CrewAI ``CrewOutput`` and return a JSONB-ready dict.

    Returns ``None`` when usage data is unavailable (e.g. partial-failure mock results).
    """
    usage_metrics = getattr(crew_result, "token_usage", None)
    if usage_metrics is None:
        return None

    # UsageMetrics is a Pydantic model; grab fields directly.
    try:
        total_tokens = int(getattr(usage_metrics, "total_tokens", 0) or 0)
        prompt_tokens = int(getattr(usage_metrics, "prompt_tokens", 0) or 0)
        completion_tokens = int(getattr(usage_metrics, "completion_tokens", 0) or 0)
        successful_requests = int(getattr(usage_metrics, "successful_requests", 0) or 0)
    except (TypeError, ValueError):
        logger.warning("Could not parse token_usage from crew result")
        return None

    if total_tokens == 0 and prompt_tokens == 0 and completion_tokens == 0:
        return None

    estimated_cost = _estimate_cost(prompt_tokens, completion_tokens, provider, model)

    return {
        "total_tokens": total_tokens,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "successful_requests": successful_requests,
        "estimated_cost_usd": estimated_cost,
        "model": model,
        "provider": provider,
    }
