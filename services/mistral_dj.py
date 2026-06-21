from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from collections import Counter

import requests

from services import history_store
from services import stats as stats_store

_MISTRAL_URL = "https://api.mistral.ai/v1/chat/completions"
logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
Eres Bandelion DJ, un curador musical inteligente para un servidor de Discord.

Tu tarea no es solo recomendar canciones similares. Debes analizar patrones musicales y \
construir una mini-sesión coherente como un DJ humano.

Analiza estas señales:
1. Artistas repetidos: detecta artistas con alta frecuencia. Considera recencia y variedad \
de canciones. No asumas gusto fuerte si solo aparece una canción aislada.
2. Géneros y subgéneros: clasifica artistas en géneros aproximados (reggaetón chill, latin \
urban, alternative rock, nu metal, electronic, pop latino, etc.). Detecta energía, mood, \
idioma y era aproximada.
3. Clusters de gusto: agrupa el historial en clusters musicales y decide si conviene continuar \
el cluster dominante o mezclar con uno compatible.
4. Canciones puente: incluye canciones que conecten géneros o artistas del perfil. \
Una canción puente debe sentirse natural, no aleatoria.
5. Variedad: máximo 1 canción por artista, máximo 2 del mismo subgénero exacto. \
Incluye al menos 2 canciones muy alineadas al gusto actual, 1 puente y 1 de descubrimiento.
6. Mood: úsalo como filtro del gusto, no como reemplazo. energético=más tempo/intensidad, \
chill=más melódico/suave, nostalgia=artistas históricos del perfil, \
sorpresa=canciones cercanas pero menos obvias.
7. Anti-repetición: no recomiendes canciones del listado de evitar. No repitas artistas \
que ya sonaron demasiado.

Devuelve ÚNICAMENTE JSON válido con este formato exacto:
{
  "djCommentary": "comentario breve y natural como un DJ, máximo 2 oraciones",
  "recommendations": [
    {
      "query": "artista - canción",
      "type": "core_taste | bridge | discovery | nostalgic | mood_match",
      "genre": "género aproximado",
      "energy": "low | medium | high"
    }
  ]
}
Reglas: todas las canciones deben ser reales y buscables en YouTube. \
No incluyas texto fuera del JSON.\
"""


def _artist(title: str) -> str | None:
    return title.split(" - ")[0].strip() if " - " in title else None


def _build_prompt(guild_id: int, mood: str | None, count: int) -> tuple[str, str]:
    history = history_store.get_all(guild_id)
    recent = history[-20:]
    avoid_titles = [h["title"] for h in history[-10:]]
    top = stats_store.top_songs(guild_id, limit=10)

    # Separate full plays (liked) from skipped (disliked) — old entries default to full_play
    liked_artist_counts: Counter[str] = Counter()
    skipped_artist_counts: Counter[str] = Counter()
    for h in history:
        a = _artist(h["title"])
        if not a:
            continue
        if h.get("skipped", False):
            skipped_artist_counts[a] += 1
        else:
            liked_artist_counts[a] += 1

    # Strong affinity: appeared in multiple sessions or high full-play count
    session_ids_per_artist: dict[str, set[str]] = {}
    for h in history:
        a = _artist(h["title"])
        sid = h.get("session_id", "")
        if a and sid:
            session_ids_per_artist.setdefault(a, set()).add(sid)

    def _affinity(artist: str) -> str:
        plays = liked_artist_counts[artist]
        sessions = len(session_ids_per_artist.get(artist, set()))
        skips = skipped_artist_counts.get(artist, 0)
        if plays >= 3 and sessions >= 2:
            return "fuerte"
        if plays >= 2 and skips == 0:
            return "positiva"
        if skips > plays:
            return "baja (muchos skips)"
        return "moderada"

    top_artists_text = "\n".join(
        f"  - {a}: {liked_artist_counts[a]} plays completos, "
        f"{skipped_artist_counts.get(a, 0)} skips, "
        f"{len(session_ids_per_artist.get(a, set()))} sesiones distintas — afinidad {_affinity(a)}"
        for a, _ in liked_artist_counts.most_common(8)
    ) or "  Sin datos"

    skipped_artists_text = (
        "\n".join(
            f"  - {a}: {cnt} skips"
            for a, cnt in skipped_artist_counts.most_common(5)
            if cnt > liked_artist_counts.get(a, 0)
        )
        or "  Ninguno"
    )

    top_songs_text = "\n".join(
        f"  - {s['title']} ({s['count']} veces)" for s in top
    ) or "  Sin datos"

    recent_text = "\n".join(
        f"  - {h['title']}"
        + (" [SKIPEADA]" if h.get("skipped") else " [completa]" if h.get("full_play") else "")
        for h in recent
    ) or "  Sin historial"

    avoid_text = "\n".join(f"  - {t}" for t in avoid_titles) or "  Ninguna"

    parts = [
        f"Artistas del servidor (con señales de calidad):\n{top_artists_text}",
        f"\nArtistas frecuentemente skipeados (evitar recomendar):\n{skipped_artists_text}",
        f"\nCanciones más pedidas:\n{top_songs_text}",
        f"\nHistorial reciente (con señal de escucha):\n{recent_text}",
        f"\nCanciones a evitar por reproducción reciente:\n{avoid_text}",
    ]
    if mood:
        parts.append(f"\nMood solicitado: {mood}")
    parts.append(f"\nGenera exactamente {count} recomendaciones.")

    return _SYSTEM_PROMPT, "\n".join(parts)


def _call_mistral(system_prompt: str, user_prompt: str) -> str:
    api_key = os.getenv("MISTRAL_API_KEY", "")
    if not api_key:
        logger.warning("MISTRAL_API_KEY no configurada — DJ no disponible")
        return ""

    model = os.getenv("MISTRAL_MODEL", "mistral-small-latest")
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
            "max_tokens": 1000,
            "temperature": 0.7,
            "response_format": {"type": "json_object"},
        },
        timeout=20,
    )
    if not response.ok:
        logger.warning("Mistral API error %s: %s", response.status_code, response.text)
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


def _parse_suggestions(
    text: str, recent_titles: list[str], count: int
) -> tuple[list[str], str]:
    text = text.strip()
    data: dict | None = None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group())
            except json.JSONDecodeError:
                pass

    if not data:
        return [], ""

    commentary: str = data.get("djCommentary", "") if isinstance(data, dict) else ""
    raw_recs = data.get("recommendations", []) if isinstance(data, dict) else []

    recent_lower = [t.lower() for t in recent_titles]
    filtered: list[str] = []
    for rec in raw_recs:
        if not isinstance(rec, dict):
            continue
        query = rec.get("query", "")
        if not isinstance(query, str) or not query:
            continue
        q_lower = query.lower()
        if any(r in q_lower or q_lower in r for r in recent_lower):
            continue
        filtered.append(query)
        if len(filtered) >= count:
            break

    return filtered, commentary


async def get_recommendations(
    guild_id: int,
    *,
    mood: str | None = None,
    count: int = 5,
) -> tuple[list[str], str]:
    """Return (song_queries, dj_commentary). Never raises."""
    if not os.getenv("MISTRAL_API_KEY", ""):
        return [], ""

    system_prompt, user_prompt = _build_prompt(guild_id, mood, count)
    try:
        raw = await asyncio.to_thread(_call_mistral, system_prompt, user_prompt)
    except Exception as e:
        logger.warning("Mistral DJ error guild=%s error=%s", guild_id, e)
        return [], ""

    if not raw:
        return [], ""

    recent_titles = [h["title"] for h in history_store.get_all(guild_id)[-10:]]
    return _parse_suggestions(raw, recent_titles, count)
