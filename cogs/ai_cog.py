from __future__ import annotations

from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands

from services import mistral_api
from ui.embeds import error_embed, safe_reply


class AICog(commands.Cog, name="AI"):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ── /summary ─────────────────────────────────────────────────────────────

    @app_commands.command(
        name="summary",
        description="Resume los mensajes recientes de un canal con IA",
    )
    @app_commands.describe(
        canal="Canal a resumir (por defecto el actual)",
        horas="Últimas N horas a resumir (mínimo 1, máximo 24)",
    )
    async def summary(
        self,
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

        # Format messages, truncating very long ones
        lines: list[str] = []
        for m in messages:
            ts = m.created_at.strftime("%H:%M")
            content = m.content[:200] + ("…" if len(m.content) > 200 else "")
            lines.append(f"[{ts}] {m.author.display_name}: {content}")

        # Truncate total to ~6000 chars to stay within Mistral context
        chat_text = "\n".join(lines)
        if len(chat_text) > 6000:
            chat_text = chat_text[-6000:]

        system = (
            "Sos un asistente que resume conversaciones de Discord en español. "
            "Identificá los temas principales, decisiones tomadas, links importantes y pendientes. "
            "Sé conciso y claro. Usá viñetas (-)."
        )
        user = (
            f"Resumí la siguiente conversación del canal #{target.name} "
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
        embed.set_footer(text=f"Últimas {horas} hora(s) · {len(messages)} mensajes analizados")
        await interaction.followup.send(embed=embed)

    # ── /ai ──────────────────────────────────────────────────────────────────

    @app_commands.command(
        name="ai",
        description="Hacele una pregunta al asistente IA del servidor",
    )
    @app_commands.describe(pregunta="Tu pregunta o pedido")
    async def ai(self, interaction: discord.Interaction, pregunta: str) -> None:
        await interaction.response.defer()

        guild = interaction.guild
        channel_names = ", ".join(
            f"#{c.name}" for c in guild.text_channels[:15]
        )

        system = (
            f"Sos el asistente IA del servidor de Discord '{guild.name}'. "
            f"Respondés en español, de forma clara y directa. "
            f"Canales del servidor: {channel_names}. "
            "Si te preguntan sobre el servidor, respondé con lo que sabés. "
            "Si es una pregunta general, respondé de forma útil y concisa."
        )

        result = await mistral_api.ask(system, pregunta, max_tokens=700, temperature=0.8)
        if not result:
            return await interaction.followup.send(
                embed=error_embed("No pude responder ahora. Revisá que `MISTRAL_API_KEY` esté configurada.")
            )

        embed = discord.Embed(
            description=result,
            color=discord.Color.purple(),
        )
        embed.set_author(
            name=f"Pregunta de {interaction.user.display_name}",
            icon_url=interaction.user.display_avatar.url,
        )
        embed.set_footer(text=f"❓ {pregunta[:80]}{'…' if len(pregunta) > 80 else ''}")
        await interaction.followup.send(embed=embed)

    async def cog_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        await safe_reply(interaction, embed=error_embed(str(error)), ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AICog(bot))
