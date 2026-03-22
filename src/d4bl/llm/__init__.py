from d4bl.llm.ollama_client import ollama_generate
from d4bl.llm.provider import (
    build_llm_model_string,
    get_available_models,
    get_llm,
    get_llm_for_task,
    reset_llm,
)

# Backward compatibility aliases
get_ollama_llm = get_llm
reset_ollama_llm = reset_llm

__all__ = [
    "get_llm",
    "get_llm_for_task",
    "reset_llm",
    "get_available_models",
    "build_llm_model_string",
    "get_ollama_llm",
    "reset_ollama_llm",
    "ollama_generate",
]

