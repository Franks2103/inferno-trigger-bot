from __future__ import annotations

from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands

from services import ai_memory, mistral_api
from ui.embeds import error_embed, safe_reply

_FOOTER = "Powered by Bandelion"

# ── /ia group ─────────────────────────────────────────────────────────────────

_ia = app_commands.Group(name="ia", description="Asistente IA con memoria personalizada")
_memory = app_commands.Group(name="memory", description="Gestión de tu memoria de IA")
_style = app_commands.Group(name="style", description="Estilo de respuesta de la IA")
_ia.add_command(_memory)
_ia.add_command(_style)


# ── /ia pregunta ──────────────────────────────────────────────────────────────

@_ia.command(name="pregunta", description="Hacele una pregunta al asistente IA")
@app_commands.describe(pregunta="Tu pregunta o pedido")
async def ia_pregunta(interaction: discord.Interaction, pregunta: str) -> None:
    if interaction.guild_id is None or interaction.guild is None:
        return await interaction.response.send_message(
            embed=error_embed("Este comando solo funciona dentro de un servidor."), ephemeral=True
        )
    await interaction.response.defer()
    memory = ai_memory.get_user_memory(interaction.guild_id, interaction.user.id)
    system, user = ai_memory.build_ia_prompt(
        guild_context={"id": interaction.guild_id, "name": interaction.guild.name},
        user_memory=memory,
        recent_context=None,
        user_message=pregunta,
    )
    result = await mistral_api.ask(system, user, max_tokens=700, temperature=0.8)
    if not result:
        return await interaction.followup.send(
            embed=error_embed("No pude responder ahora. Revisá que `MISTRAL_API_KEY` esté configurada.")
        )
    embed = discord.Embed(description=result, color=discord.Color.purple())
    embed.set_author(
        name=f"Pregunta de {interaction.user.display_name}",
        icon_url=interaction.user.display_avatar.url,
    )
    embed.set_footer(text=f"❓ {pregunta[:80]}{'…' if len(pregunta) > 80 else ''} · {_FOOTER}")
    await interaction.followup.send(embed=embed)


# ── /ia memory set ────────────────────────────────────────────────────────────

@_memory.command(name="set", description="Guarda o agrega una preferencia de estilo")
@app_commands.describe(texto="Tu preferencia, ej: 'habláme como un paisa'")
async def ia_memory_set(interaction: discord.Interaction, texto: str) -> None:
    if interaction.guild_id is None:
        return await interaction.response.send_message(
            embed=error_embed("Este comando solo funciona dentro de un servidor."), ephemeral=True
        )
    try:
        ai_memory.add_preference(interaction.guild_id, interaction.user.id, texto)
    except ValueError as e:
        return await interaction.response.send_message(embed=error_embed(str(e)), ephemeral=True)
    embed = discord.Embed(
        description="✅ Listo, guardé tu preferencia para este servidor.",
        color=discord.Color.green(),
    )
    embed.set_footer(text=_FOOTER)
    await interaction.response.send_message(embed=embed, ephemeral=True)


# ── /ia memory view ───────────────────────────────────────────────────────────

@_memory.command(name="view", description="Muestra tu memoria actual")
async def ia_memory_view(interaction: discord.Interaction) -> None:
    if interaction.guild_id is None:
        return await interaction.response.send_message(
            embed=error_embed("Este comando solo funciona dentro de un servidor."), ephemeral=True
        )
    mem = ai_memory.get_user_memory(interaction.guild_id, interaction.user.id)
    preset = mem.get("style_preset", "neutral")
    custom_tone = mem.get("custom_tone", "")
    prefs: list[str] = mem.get("preferences", [])
    updated = mem.get("updated_at", "")

    lines = [f"**Estilo activo:** `{preset}`"]
    if custom_tone:
        lines.append(f"**Tono personalizado (prioritario):** {custom_tone}")
    if prefs:
        lines.append(f"\n**Preferencias ({len(prefs)}):**")
        for i, p in enumerate(prefs, 1):
            lines.append(f"`{i}.` {p}")
    else:
        lines.append("\n*No tenés preferencias guardadas. Usá `/ia memory set` para agregar.*")

    embed = discord.Embed(
        title="🧠 Tu memoria de IA",
        description="\n".join(lines),
        color=discord.Color.blurple(),
    )
    if updated:
        embed.set_footer(text=f"{_FOOTER} · Última actualización: {updated[:10]}")
    else:
        embed.set_footer(text=_FOOTER)
    await interaction.response.send_message(embed=embed, ephemeral=True)


# ── /ia memory clear ──────────────────────────────────────────────────────────

@_memory.command(name="clear", description="Borra toda tu memoria de IA en este servidor")
async def ia_memory_clear(interaction: discord.Interaction) -> None:
    if interaction.guild_id is None:
        return await interaction.response.send_message(
            embed=error_embed("Este comando solo funciona dentro de un servidor."), ephemeral=True
        )
    ai_memory.clear_user_memory(interaction.guild_id, interaction.user.id)
    embed = discord.Embed(
        description="🗑️ Borré tu memoria de IA en este servidor.",
        color=discord.Color.orange(),
    )
    embed.set_footer(text=_FOOTER)
    await interaction.response.send_message(embed=embed, ephemeral=True)


# ── /ia memory remove ─────────────────────────────────────────────────────────

@_memory.command(name="remove", description="Elimina una preferencia por número")
@app_commands.describe(indice="Número de la preferencia a eliminar (ver con /ia memory view)")
async def ia_memory_remove(interaction: discord.Interaction, indice: int) -> None:
    if interaction.guild_id is None:
        return await interaction.response.send_message(
            embed=error_embed("Este comando solo funciona dentro de un servidor."), ephemeral=True
        )
    try:
        removed = ai_memory.remove_preference(interaction.guild_id, interaction.user.id, indice)
    except IndexError as e:
        return await interaction.response.send_message(embed=error_embed(str(e)), ephemeral=True)
    embed = discord.Embed(
        description=f"✅ Eliminé: *{removed}*",
        color=discord.Color.green(),
    )
    embed.set_footer(text=_FOOTER)
    await interaction.response.send_message(embed=embed, ephemeral=True)


# ── /ia style set ─────────────────────────────────────────────────────────────

@_style.command(name="set", description="Elige un estilo de respuesta")
@app_commands.describe(preset="Estilo predefinido")
@app_commands.choices(preset=[
    app_commands.Choice(name=k, value=k) for k in ai_memory.STYLE_PRESETS
])
async def ia_style_set(interaction: discord.Interaction, preset: str) -> None:
    if interaction.guild_id is None:
        return await interaction.response.send_message(
            embed=error_embed("Este comando solo funciona dentro de un servidor."), ephemeral=True
        )
    try:
        ai_memory.set_style_preset(interaction.guild_id, interaction.user.id, preset)
    except ValueError as e:
        return await interaction.response.send_message(embed=error_embed(str(e)), ephemeral=True)
    desc = ai_memory.STYLE_PRESETS[preset]
    embed = discord.Embed(
        title=f"✅ Estilo `{preset}` activado",
        description=desc,
        color=discord.Color.green(),
    )
    embed.set_footer(text=_FOOTER)
    await interaction.response.send_message(embed=embed, ephemeral=True)


# ── /ia style custom ──────────────────────────────────────────────────────────

@_style.command(name="custom", description="Define tu tono personalizado (prioridad sobre presets)")
@app_commands.describe(tono="Ej.: 'hablame como un andaluz, casual y breve'")
async def ia_style_custom(interaction: discord.Interaction, tono: str) -> None:
    if interaction.guild_id is None:
        return await interaction.response.send_message(
            embed=error_embed("Este comando solo funciona dentro de un servidor."), ephemeral=True
        )
    try:
        ai_memory.set_custom_tone(interaction.guild_id, interaction.user.id, tono)
    except ValueError as e:
        return await interaction.response.send_message(embed=error_embed(str(e)), ephemeral=True)
    embed = discord.Embed(
        title="✅ Tono personalizado guardado",
        description="Se aplicará antes que los presets de estilo.\n\n" + tono,
        color=discord.Color.green(),
    )
    embed.set_footer(text=_FOOTER)
    await interaction.response.send_message(embed=embed, ephemeral=True)


# ── /ia style reset ───────────────────────────────────────────────────────────

@_style.command(name="reset", description="Restablece el estilo a neutral")
async def ia_style_reset(interaction: discord.Interaction) -> None:
    if interaction.guild_id is None:
        return await interaction.response.send_message(
            embed=error_embed("Este comando solo funciona dentro de un servidor."), ephemeral=True
        )
    ai_memory.set_style_preset(interaction.guild_id, interaction.user.id, "neutral")
    ai_memory.clear_custom_tone(interaction.guild_id, interaction.user.id)
    embed = discord.Embed(
        description="✅ Estilo y tono personalizado restablecidos a **neutral**.",
        color=discord.Color.green(),
    )
    embed.set_footer(text=_FOOTER)
    await interaction.response.send_message(embed=embed, ephemeral=True)


# ── /summary ──────────────────────────────────────────────────────────────────

_summary = app_commands.Group(name="summary", description="Resume mensajes de un canal con IA")


@_summary.command(name="canal", description="Resume los mensajes recientes de un canal")
@app_commands.describe(
    canal="Canal a resumir (por defecto el actual)",
    horas="Últimas N horas a resumir (1-24)",
)
async def summary_canal(
    interaction: discord.Interaction,
    canal: discord.TextChannel | None = None,
    horas: app_commands.Range[int, 1, 24] = 24,
) -> None:
    await interaction.response.defer()
    target = canal or interaction.channel
    since = datetime.now(timezone.utc) - timedelta(hours=horas)

    try:
        messages = [
            m
            async for m in target.history(after=since, limit=300, oldest_first=True)
            if m.content and not m.author.bot
        ]
    except discord.Forbidden:
        return await interaction.followup.send(
            embed=error_embed(f"No tengo permiso para leer mensajes en {target.mention}."),
            ephemeral=True,
        )

    if not messages:
        return await interaction.followup.send(
            embed=discord.Embed(
                description=f"No hay mensajes de usuarios en {target.mention} de las últimas {horas} hora(s).",
                color=discord.Color.greyple(),
            )
        )

    lines = []
    for m in messages:
        ts = m.created_at.strftime("%H:%M")
        content = m.content[:200] + ("…" if len(m.content) > 200 else "")
        lines.append(f"[{ts}] {m.author.display_name}: {content}")

    chat_text = "\n".join(lines)
    if len(chat_text) > 6000:
        chat_text = chat_text[-6000:]

    system = (
        "Sos un asistente que resume conversaciones de Discord en español. "
        "Identificá los temas principales, decisiones tomadas, links importantes y pendientes. "
        "Sé conciso y claro. Usá viñetas (-)."
    )
    user = (
        f"Resumí la conversación del canal #{target.name} "
        f"(últimas {horas} hora(s), {len(messages)} mensajes):\n\n{chat_text}"
    )

    result = await mistral_api.ask(system, user, max_tokens=600)
    if not result:
        return await interaction.followup.send(
            embed=error_embed("No pude generar el resumen. Revisá que `MISTRAL_API_KEY` esté configurada.")
        )

    embed = discord.Embed(
        title=f"📋 Resumen de #{target.name}",
        description=result,
        color=discord.Color.blurple(),
    )
    embed.set_footer(text=f"{_FOOTER} · Últimas {horas} hora(s) · {len(messages)} mensajes")
    await interaction.followup.send(embed=embed)


# ── Cog ───────────────────────────────────────────────────────────────────────

class AICog(commands.Cog, name="AI"):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def cog_load(self) -> None:
        self.bot.tree.add_command(_ia)
        self.bot.tree.add_command(_summary)

    async def cog_unload(self) -> None:
        self.bot.tree.remove_command("ia")
        self.bot.tree.remove_command("summary")

    async def cog_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        await safe_reply(interaction, embed=error_embed(str(error)), ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AICog(bot))
