from __future__ import annotations

import logging
import os
import threading

from crewai import LLM

from d4bl.settings import get_settings

logger = logging.getLogger(__name__)

_ollama_llm: LLM | None = None
_lock = threading.Lock()


def get_ollama_llm() -> LLM:
    """Get or create the Ollama LLM instance (lazy, thread-safe)."""
    global _ollama_llm
    if _ollama_llm is not None:
        return _ollama_llm

    with _lock:
        # Double-checked locking
        if _ollama_llm is not None:
            return _ollama_llm

        settings = get_settings()

        # LiteLLM reads this env var for Ollama routing.
        os.environ["OLLAMA_API_BASE"] = settings.ollama_base_url

        _ollama_llm = LLM(
            model=f"ollama/{settings.ollama_model}",
            base_url=settings.ollama_base_url,
            temperature=0.5,
            timeout=180.0,
            num_retries=5,
        )
        logger.info(
            "Initialized Ollama LLM (model=%s, base_url=%s)",
            settings.ollama_model,
            settings.ollama_base_url,
        )
        return _ollama_llm


def reset_ollama_llm() -> None:
    """Reset the Ollama LLM instance (useful for connection issues)."""
    global _ollama_llm
    with _lock:
        _ollama_llm = None
    logger.info("Reset Ollama LLM instance")
