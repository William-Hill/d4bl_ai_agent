from __future__ import annotations

import logging
import time
from typing import Any

from d4bl.llm import get_ollama_llm

logger = logging.getLogger(__name__)


def get_eval_llm():
    """Return the LLM to use for Langfuse evaluations."""
    return get_ollama_llm()


def call_llm_text(llm: Any, prompt: str, max_retries: int = 2, retry_delay: float = 2.0) -> str:
    """
    Call an LLM and return text content, retrying on failure.
    Supports callable llm or objects with .call(prompt).
    """
    last_error: Exception | None = None
    for attempt in range(max_retries):
        try:
            if hasattr(llm, "call"):
                result = llm.call(prompt)
            elif callable(llm):
                result = llm(prompt)
            else:
                raise ValueError("LLM object is not callable and has no .call method")

            text = str(result.content) if hasattr(result, "content") else str(result)
            if not text or not text.strip():
                raise ValueError("LLM returned empty response")
            return text
        except Exception as e:  # pragma: no cover - defensive
            last_error = e
            if attempt < max_retries - 1:
                wait_time = retry_delay * (attempt + 1)
                logger.warning(
                    "LLM call failed (attempt %s/%s), retrying in %ss: %s",
                    attempt + 1,
                    max_retries,
                    wait_time,
                    e,
                )
                time.sleep(wait_time)
            else:
                logger.error("LLM call failed after %s attempts: %s", max_retries, e, exc_info=True)
                raise ValueError(f"LLM invocation failed: {str(e)}") from e

    raise ValueError(f"LLM invocation failed: {str(last_error)}")
