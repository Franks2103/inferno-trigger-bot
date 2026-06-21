from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from services import mistral_dj
from services import permissions as perms
from services.extractor import search_tracks
from ui.embeds import error_embed, safe_reply, success_embed


class DJCog(commands.Cog, name="DJ"):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    def _get_service(self, interaction: discord.Interaction):
        music_cog = self.bot.cogs.get("Music")
        if music_cog is None:
            return None
        return music_cog.get_service_for_guild(interaction.guild_id)

    def _get_or_create_service(self, interaction: discord.Interaction):
        music_cog = self.bot.cogs.get("Music")
        if music_cog is None:
            return None
        return music_cog.get_or_create_service_for_guild(interaction.guild)

    @app_commands.command(name="dj", description="Controla el modo DJ automático")
    @app_commands.describe(
        accion="Acción a realizar: start, stop o status",
        mood="Mood opcional para start (ej: energético, lo-fi, reggaeton)",
    )
    @app_commands.choices(accion=[
        app_commands.Choice(name="start", value="start"),
        app_commands.Choice(name="stop", value="stop"),
        app_commands.Choice(name="status", value="status"),
    ])
    async def dj(
        self,
        interaction: discord.Interaction,
        accion: str,
        mood: str | None = None,
    ) -> None:
        if accion in ("start", "stop"):
            perms.check(interaction, f"dj-{accion}")
        else:
            perms.check(interaction, "dj-status")

        service = self._get_service(interaction)

        if accion == "start":
            if interaction.user.voice is None or interaction.user.voice.channel is None:
                return await interaction.response.send_message(
                    embed=error_embed("Tenés que estar en un canal de voz para activar el DJ."),
                    ephemeral=True,
                )

            await interaction.response.defer()

            # Join voice if not already connected
            voice_channel = interaction.user.voice.channel
            vc = interaction.guild.voice_client
            if vc is None:
                await voice_channel.connect()
            elif vc.channel != voice_channel:
                await vc.move_to(voice_channel)

            service = self._get_or_create_service(interaction)
            if service is None:
                return await interaction.followup.send(
                    embed=error_embed("No se pudo iniciar la sesión de música."), ephemeral=True
                )

            service.dj_mode = True
            service.dj_mood = mood or None
            service.text_channel = interaction.channel

            suggestions, commentary = await mistral_dj.get_recommendations(
                interaction.guild_id, mood=mood, count=5
            )
            if not suggestions:
                service.dj_mode = False
                return await interaction.followup.send(
                    embed=error_embed("No pude generar sugerencias. Revisá que `MISTRAL_API_KEY` esté configurada e intentá de nuevo.")
                )

            queued: list[str] = []
            for title in suggestions:
                try:
                    tracks = await search_tracks(title, interaction.user, limit=1)
                    if tracks:
                        service.add(tracks[0])
                        queued.append(tracks[0].title)
                except Exception:
                    continue

            if not queued:
                service.dj_mode = False
                return await interaction.followup.send(
                    embed=error_embed("No pude encontrar las canciones sugeridas en YouTube.")
                )

            mood_text = f" · Mood: `{mood}`" if mood else ""
            lines = "\n".join(f"`{i + 1}.` {t}" for i, t in enumerate(queued))
            embed = discord.Embed(
                title="🎧 Modo DJ activado",
                description=f"Agregué {len(queued)} canciones a la cola{mood_text}:\n{lines}",
                color=discord.Color.purple(),
            )
            if commentary:
                embed.add_field(name="🎙️ Bandelion DJ", value=commentary, inline=False)
            embed.set_footer(text="El DJ seguirá agregando canciones automáticamente.")
            await interaction.followup.send(embed=embed)

        elif accion == "stop":
            if service is None or not service.dj_mode:
                return await interaction.response.send_message(
                    embed=error_embed("El modo DJ no está activo."), ephemeral=True
                )
            service.dj_mode = False
            service.dj_mood = None
            await interaction.response.send_message(
                embed=success_embed("Modo DJ desactivado. La cola actual sigue sonando.")
            )

        elif accion == "status":
            if service is None or not service.dj_mode:
                embed = discord.Embed(
                    description="El modo DJ está **desactivado**.",
                    color=discord.Color.greyple(),
                )
            else:
                mood_text = f"`{service.dj_mood}`" if service.dj_mood else "ninguno (basado en historial)"
                embed = discord.Embed(
                    title="🎧 DJ activo",
                    color=discord.Color.purple(),
                )
                embed.add_field(name="Mood", value=mood_text, inline=True)
                embed.add_field(name="Canciones en cola", value=str(len(service.queue)), inline=True)
            await interaction.response.send_message(embed=embed)

    async def cog_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        await safe_reply(interaction, embed=error_embed(str(error)), ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(DJCog(bot))
