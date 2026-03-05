"""Shared async helper for Ollama /api/generate calls."""
from __future__ import annotations

import logging

import aiohttp

from d4bl.settings import get_settings

logger = logging.getLogger(__name__)


async def ollama_generate(
    *,
    base_url: str,
    prompt: str,
    model: str | None = None,
    temperature: float = 0.1,
    timeout_seconds: int = 30,
) -> str:
    """Call Ollama /api/generate and return the response text.

    Args:
        base_url: Ollama base URL (e.g. "http://localhost:11434").
        prompt: The prompt to send.
        model: Model name. Defaults to ``Settings.ollama_model``.
        temperature: Sampling temperature (default: 0.1).
        timeout_seconds: HTTP timeout in seconds (default: 30).

    Returns:
        The "response" field from Ollama, stripped of whitespace.

    Raises:
        RuntimeError: If Ollama returns a non-200 status.
    """
    if model is None:
        model = get_settings().ollama_model

    timeout = aiohttp.ClientTimeout(total=timeout_seconds)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(
            f"{base_url}/api/generate",
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": temperature},
            },
        ) as response:
            if response.status != 200:
                body = await response.text()
                raise RuntimeError(
                    f"Ollama returned status {response.status}: {body}"
                )
            data = await response.json()

    return data.get("response", "").strip()
