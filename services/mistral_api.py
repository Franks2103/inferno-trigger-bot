from __future__ import annotations

import asyncio
import logging
import os

import requests

_MISTRAL_URL = "https://api.mistral.ai/v1/chat/completions"
logger = logging.getLogger(__name__)


def _call(system: str, user: str, max_tokens: int, temperature: float) -> str:
    api_key = os.getenv("MISTRAL_API_KEY", "")
    if not api_key:
        return ""
    model = os.getenv("MISTRAL_MODEL", "mistral-small-latest")
    resp = requests.post(
        _MISTRAL_URL,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
        },
        timeout=20,
    )
    if not resp.ok:
        logger.warning("Mistral API error %s: %s", resp.status_code, resp.text)
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


async def ask(
    system: str,
    user: str,
    *,
    max_tokens: int = 800,
    temperature: float = 0.7,
) -> str:
    """Generic async Mistral call. Returns '' on error or missing key."""
    if not os.getenv("MISTRAL_API_KEY", ""):
        return ""
    try:
        return await asyncio.to_thread(_call, system, user, max_tokens, temperature)
    except Exception as e:
        logger.warning("Mistral ask error: %s", e)
        return ""
