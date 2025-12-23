from __future__ import annotations

import os
from crewai import LLM

from d4bl.settings import get_settings

_ollama_llm = None


def get_ollama_llm():
    """Get or create the Ollama LLM instance (lazy initialization)."""
    global _ollama_llm
    if _ollama_llm is None:
        try:
            settings = get_settings()
            ollama_base_url = settings.ollama_base_url.rstrip("/")

            # Set environment variable for LiteLLM to use
            os.environ["OLLAMA_API_BASE"] = ollama_base_url

            _ollama_llm = LLM(
                model="ollama/mistral",
                base_url=ollama_base_url,
                temperature=0.5,
                timeout=180.0,
                num_retries=5,
            )
            print(f"✅ Initialized Ollama LLM with base_url: {ollama_base_url}")
            print(
                "   Note: Configure Ollama server queue settings (OLLAMA_MAX_QUEUE, "
                "OLLAMA_NUM_PARALLEL) when starting Ollama"
            )
        except ImportError as e:
            raise ImportError(
                "LiteLLM is required for Ollama support. "
                "Please install it with: pip install litellm"
            ) from e
        except Exception as e:
            print(f"⚠️ Error initializing Ollama LLM: {e}")
            raise
    return _ollama_llm


def reset_ollama_llm():
    """Reset the Ollama LLM instance (useful for connection issues)."""
    global _ollama_llm
    _ollama_llm = None
    print("🔄 Reset Ollama LLM instance")

