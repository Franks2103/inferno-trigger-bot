# ui/history_view.py
from __future__ import annotations

import discord


def build_history_embed(entries: list[dict], guild: discord.Guild) -> discord.Embed:
    embed = discord.Embed(
        title=f"📜 Historial de {guild.name}",
        color=discord.Color.blurple(),
    )
    if not entries:
        embed.description = "No hay historial disponible."
        return embed
    lines = []
    for i, e in enumerate(reversed(entries[-20:]), 1):
        lines.append(f"`{i}.` [{e['title']}]({e['webpage_url']}) — {e['requester_name']}")
    embed.description = "\n".join(lines)
    return embed
