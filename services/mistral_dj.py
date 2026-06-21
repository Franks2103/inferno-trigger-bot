from __future__ import annotations

import asyncio
import json
import logging
import os
import re

import requests

from services import history_store
from services import stats as stats_store

_MISTRAL_URL = "https://api.mistral.ai/v1/chat/completions"
logger = logging.getLogger(__name__)


def _build_prompt(guild_id: int, mood: str | None, count: int) -> tuple[str, str]:
    history = history_store.get_all(guild_id)
    recent_titles = [h["title"] for h in history[-20:]]
    top = stats_store.top_songs(guild_id, limit=5)

    system_prompt = (
        "Sos un DJ experto. Basándote en el historial musical del servidor, sugerí canciones "
        "similares que le gustarían a la audiencia. Responde ÚNICAMENTE con un array JSON de "
        'strings, sin explicación ni texto adicional. Formato exacto: ["artista - canción", ...]'
    )

    history_text = ", ".join(recent_titles) if recent_titles else "Sin historial"
    top_text = (
        ", ".join(f"{s['title']} ({s['count']} veces)" for s in top)
        if top
        else "Sin datos"
    )

    user_parts = [
        f"Historial reciente: {history_text}",
        f"Más pedidas: {top_text}",
    ]
    if mood:
        user_parts.append(f"El mood pedido es: {mood}. Adaptá las sugerencias a ese estilo.")
    user_parts.append(
        f"Sugerí exactamente {count} canciones que NO estén en el historial reciente."
    )

    return system_prompt, "\n".join(user_parts)


def _call_mistral(system_prompt: str, user_prompt: str) -> str:
    api_key = os.getenv("MISTRAL_API_KEY", "")
    if not api_key:
        logger.warning("MISTRAL_API_KEY no configurada — DJ no disponible")
        return ""

    model = os.getenv("MISTRAL_MODEL", "ministral-3b")
    response = requests.post(
        _MISTRAL_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "max_tokens": 300,
            "temperature": 0.8,
        },
        timeout=15,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


def _parse_suggestions(text: str, recent_titles: list[str], count: int) -> list[str]:
    text = text.strip()
    try:
        suggestions = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\[.*?\]", text, re.DOTALL)
        if not match:
            return []
        try:
            suggestions = json.loads(match.group())
        except json.JSONDecodeError:
            return []

    if not isinstance(suggestions, list):
        return []

    recent_lower = [t.lower() for t in recent_titles]
    filtered: list[str] = []
    for s in suggestions:
        if not isinstance(s, str):
            continue
        s_lower = s.lower()
        if any(r in s_lower or s_lower in r for r in recent_lower):
            continue
        filtered.append(s)
        if len(filtered) >= count:
            break
    return filtered


async def get_recommendations(
    guild_id: int,
    *,
    mood: str | None = None,
    count: int = 5,
) -> list[str]:
    if not os.getenv("MISTRAL_API_KEY", ""):
        return []

    system_prompt, user_prompt = _build_prompt(guild_id, mood, count)
    try:
        raw = await asyncio.to_thread(_call_mistral, system_prompt, user_prompt)
    except Exception as e:
        logger.warning("Mistral DJ error guild=%s error=%s", guild_id, e)
        return []

    if not raw:
        return []

    recent_titles = [h["title"] for h in history_store.get_all(guild_id)[-20:]]
    return _parse_suggestions(raw, recent_titles, count)
