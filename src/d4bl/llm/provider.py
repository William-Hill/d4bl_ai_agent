from __future__ import annotations

import logging
import os
import threading

from crewai import LLM

from d4bl.settings import get_settings

logger = logging.getLogger(__name__)

_llm: LLM | None = None
_lock = threading.Lock()


def build_llm_model_string(provider: str, model: str) -> str:
    """Build the LiteLLM model string: '{provider}/{model}'."""
    return f"{provider}/{model}"


def get_llm() -> LLM:
    """Get or create the LLM instance (lazy, thread-safe)."""
    global _llm
    if _llm is not None:
        return _llm

    with _lock:
        if _llm is not None:
            return _llm

        settings = get_settings()
        provider = settings.llm_provider
        model_string = build_llm_model_string(provider, settings.llm_model)

        kwargs: dict = {
            "model": model_string,
            "temperature": 0.5,
            "timeout": 180.0,
            "num_retries": 5,
        }

        if provider == "ollama":
            os.environ["OLLAMA_API_BASE"] = settings.ollama_base_url
            kwargs["base_url"] = settings.ollama_base_url
        else:
            if not settings.llm_api_key:
                raise ValueError(
                    f"LLM_API_KEY is required for provider '{provider}'. "
                    "Set the LLM_API_KEY environment variable."
                )
            kwargs["api_key"] = settings.llm_api_key

        _llm = LLM(**kwargs)
        logger.info(
            "Initialized LLM (provider=%s, model=%s)",
            provider,
            settings.llm_model,
        )
        return _llm


def reset_llm() -> None:
    """Reset the LLM instance."""
    global _llm
    with _lock:
        _llm = None
    logger.info("Reset LLM instance")


def get_available_models() -> list[dict]:
    """Return available models based on current configuration."""
    settings = get_settings()
    current_model_string = build_llm_model_string(
        settings.llm_provider, settings.llm_model
    )
    return [
        {
            "provider": settings.llm_provider,
            "model": settings.llm_model,
            "model_string": current_model_string,
            "is_default": True,
        }
    ]
