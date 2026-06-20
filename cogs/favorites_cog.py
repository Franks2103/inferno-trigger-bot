import discord
from discord import app_commands
from discord.ext import commands

from services import favorites as fav_service
from services.extractor import create_track


def _check_music_channel(interaction: discord.Interaction) -> str | None:
    """Returns error message string if wrong channel, else None."""
    from services import guild_config
    ch_id = guild_config.music_channel_id(interaction.guild_id)
    if ch_id and interaction.channel_id != ch_id:
        channel = interaction.guild.get_channel(ch_id)
        return f"Usá los comandos de música en {channel.mention if channel else f'<#{ch_id}>'}."
    return None


class FavoritesCog(commands.Cog, name="Favorites"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="fav-add", description="Guarda la canción actual en tus favoritos")
    async def fav_add(self, interaction: discord.Interaction) -> None:
        if err := _check_music_channel(interaction):
            return await interaction.response.send_message(err, ephemeral=True)
        # Find the MusicService for this guild via the MusicCog
        music_cog = self.bot.cogs.get("Music")
        service = music_cog.get_service_for_guild(interaction.guild_id) if music_cog else None

        if not service or not service.current:
            return await interaction.response.send_message(
                "No hay ninguna canción reproduciéndose.", ephemeral=True
            )

        track = service.current
        result = fav_service.add(
            interaction.user.id, track.title, track.webpage_url, track.thumbnail
        )

        if result == "duplicate":
            await interaction.response.send_message("Ya tenés esa canción en favoritos.", ephemeral=True)
        elif result == "full":
            await interaction.response.send_message(
                f"Llegaste al límite de {fav_service.MAX_PER_USER} favoritos.", ephemeral=True
            )
        else:
            await interaction.response.send_message(f"❤️ Guardado: **{track.title}**", ephemeral=True)

    @app_commands.command(name="fav-list", description="Muestra tu lista de canciones favoritas")
    async def fav_list(self, interaction: discord.Interaction) -> None:
        if err := _check_music_channel(interaction):
            return await interaction.response.send_message(err, ephemeral=True)
        favs = fav_service.get_all(interaction.user.id)
        if not favs:
            return await interaction.response.send_message("No tenés favoritos guardados.", ephemeral=True)

        embed = discord.Embed(
            title=f"❤️ Favoritos de {interaction.user.display_name}",
            color=discord.Color.red(),
        )
        lines = [f"`{i}.` [{f['title']}]({f['webpage_url']})" for i, f in enumerate(favs, 1)]
        embed.description = "\n".join(lines[:25])
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="fav-play", description="Encola un favorito por posición")
    async def fav_play(self, interaction: discord.Interaction, position: int) -> None:
        if err := _check_music_channel(interaction):
            return await interaction.response.send_message(err, ephemeral=True)
        favs = fav_service.get_all(interaction.user.id)
        if not 1 <= position <= len(favs):
            return await interaction.response.send_message(
                f"Posición inválida (1-{len(favs)}).", ephemeral=True
            )

        await interaction.response.defer()
        fav = favs[position - 1]
        track = await create_track(fav["webpage_url"], interaction.user)

        music_cog = self.bot.cogs.get("Music")
        if not music_cog:
            return await interaction.followup.send("Error interno.", ephemeral=True)

        service = music_cog.get_or_create_service(interaction)
        was_playing = service.current is not None

        # Ensure voice
        if interaction.user.voice and interaction.user.voice.channel:
            vc = interaction.guild.voice_client
            if vc is None:
                await interaction.user.voice.channel.connect()
            elif vc.channel != interaction.user.voice.channel:
                await vc.move_to(interaction.user.voice.channel)
        else:
            return await interaction.followup.send(
                "Debes estar en un canal de voz.", ephemeral=True
            )

        service.add(track)
        if was_playing:
            await interaction.followup.send(f"➕ Favorito encolado: **{track.title}**")
        else:
            await interaction.followup.send(f"🎶 Reproduciendo favorito: **{track.title}**")

    @app_commands.command(name="fav-remove", description="Elimina un favorito por posición")
    async def fav_remove(self, interaction: discord.Interaction, position: int) -> None:
        if err := _check_music_channel(interaction):
            return await interaction.response.send_message(err, ephemeral=True)
        removed = fav_service.remove(interaction.user.id, position)
        if not removed:
            favs = fav_service.get_all(interaction.user.id)
            return await interaction.response.send_message(
                f"Posición inválida (1-{len(favs)}).", ephemeral=True
            )
        await interaction.response.send_message(
            f"🗑️ Eliminado de favoritos: **{removed['title']}**", ephemeral=True
        )

    async def cog_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        from ui.embeds import error_embed, safe_reply
        await safe_reply(interaction, embed=error_embed(str(error)), ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(FavoritesCog(bot))
