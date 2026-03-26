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


def get_llm_for_task(task: str) -> LLM:
    """Get an LLM instance for a specific task.

    If a task-specific model is configured (e.g. EVALUATOR_MODEL env var),
    creates a new LLM for that model. Otherwise returns the default LLM.

    Note: Task-specific instances are NOT cached as singletons — they are
    lightweight wrappers and creating them is cheap. This avoids stale state
    if env vars change.
    """
    from d4bl.llm.ollama_client import TASK_MODEL_ATTRS, model_for_task

    settings = get_settings()

    # If no task-specific model is configured, return the shared default
    attr = TASK_MODEL_ATTRS.get(task)
    task_setting = getattr(settings, attr, "") if attr else ""
    if not task_setting:
        return get_llm()

    task_model = model_for_task(task)

    provider = settings.llm_provider
    model_string = build_llm_model_string(provider, task_model)

    kwargs: dict = {
        "model": model_string,
        "temperature": 0.1,
        "timeout": 180.0,
        "num_retries": 5,
    }

    if provider == "ollama":
        kwargs["base_url"] = settings.ollama_base_url
    elif settings.llm_api_key:
        kwargs["api_key"] = settings.llm_api_key
    else:
        logger.warning(
            "No LLM_API_KEY set for provider '%s' (task=%s) — calls may fail",
            provider, task,
        )

    logger.info("Creating task-specific LLM (task=%s, model=%s)", task, task_model)
    return LLM(**kwargs)


def get_available_models() -> list[dict]:
    """Return available models based on current configuration.

    Includes the default model plus any configured task-specific models.
    """
    settings = get_settings()
    current_model_string = build_llm_model_string(
        settings.llm_provider, settings.llm_model
    )
    models = [
        {
            "provider": settings.llm_provider,
            "model": settings.llm_model,
            "model_string": current_model_string,
            "is_default": True,
            "task": "general",
        }
    ]

    from d4bl.llm.ollama_client import TASK_MODEL_ATTRS

    seen = {settings.llm_model}
    for task, attr in TASK_MODEL_ATTRS.items():
        model_name = getattr(settings, attr, "")
        if model_name and model_name not in seen:
            seen.add(model_name)
            models.append({
                "provider": settings.llm_provider,
                "model": model_name,
                "model_string": build_llm_model_string(settings.llm_provider, model_name),
                "is_default": False,
                "task": task,
            })

    return models
