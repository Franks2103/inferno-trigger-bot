import math

import discord
from discord import app_commands
from discord.ext import commands

from models.track import Track
from services import guild_config
from services import permissions as perms
from services.extractor import (
    create_track,
    create_track_from_spotify,
    create_tracks_from_playlist,
    looks_like_playlist_url,
    looks_like_spotify_url,
    looks_like_url,
    search_tracks,
)
from services.music_service import LoopMode, MusicService
from ui.player_view import NowPlayingView, build_now_playing_embed
from ui.search_view import SearchView, build_search_embed


class MusicCog(commands.Cog, name="Music"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._states: dict[int, MusicService] = {}

    def get_or_create_service(self, interaction: discord.Interaction) -> MusicService:
        guild_id = interaction.guild_id
        if guild_id not in self._states:
            service = MusicService(self.bot, interaction.guild)
            service.volume = guild_config.default_volume(guild_id)
            service.on_track_start = self._send_now_playing
            self._states[guild_id] = service
        self._states[guild_id].text_channel = interaction.channel
        return self._states[guild_id]

    def get_service_for_guild(self, guild_id: int) -> MusicService | None:
        """Public API for other cogs to read the current MusicService."""
        return self._states.get(guild_id)

    async def _send_now_playing(self, service: MusicService, track: Track) -> None:
        if not service.text_channel:
            return
        embed = build_now_playing_embed(track, service)
        view = NowPlayingView(service)
        await service.text_channel.send(embed=embed, view=view)

    async def _ensure_voice(self, interaction: discord.Interaction) -> discord.VoiceClient:
        if interaction.user.voice is None or interaction.user.voice.channel is None:
            raise app_commands.AppCommandError("Debes estar en un canal de voz primero.")
        target_channel = interaction.user.voice.channel
        voice_client = interaction.guild.voice_client
        if voice_client is None:
            return await target_channel.connect()
        if voice_client.channel != target_channel:
            await voice_client.move_to(target_channel)
        return voice_client

    def _check_channel(self, interaction: discord.Interaction) -> None:
        ch_id = guild_config.music_channel_id(interaction.guild_id)
        if ch_id and interaction.channel_id != ch_id:
            channel = interaction.guild.get_channel(ch_id)
            name = channel.mention if channel else f"<#{ch_id}>"
            raise app_commands.AppCommandError(f"Usá los comandos de música en {name}.")

    # ── Commands ──────────────────────────────────────────────────────────────

    @app_commands.command(name="join", description="Conecta al canal de voz actual")
    async def join(self, interaction: discord.Interaction) -> None:
        self._check_channel(interaction)
        await self._ensure_voice(interaction)
        await interaction.response.send_message("✅ Conectado al canal de voz.")

    @app_commands.command(name="play", description="Reproduce una canción, playlist de YouTube, link de Spotify o búsqueda")
    async def play(self, interaction: discord.Interaction, query: str) -> None:
        self._check_channel(interaction)
        await interaction.response.defer()
        await self._ensure_voice(interaction)
        service = self.get_or_create_service(interaction)

        max_q = guild_config.max_queue(interaction.guild_id)
        if len(service.queue) >= max_q:
            return await interaction.followup.send(
                f"⚠️ La cola está llena (máximo {max_q} canciones).", ephemeral=True
            )

        if looks_like_playlist_url(query):
            tracks = await create_tracks_from_playlist(query, interaction.user)
            # Respect max_queue limit
            available = max_q - len(service.queue)
            tracks = tracks[:available]
            for track in tracks:
                service.add(track)
            await interaction.followup.send(f"📋 Encoladas **{len(tracks)}** canciones de la playlist.")

        elif looks_like_spotify_url(query):
            track = await create_track_from_spotify(query, interaction.user)
            was_playing = service.current is not None
            service.add(track)
            if was_playing:
                await interaction.followup.send(f"➕ Añadida (vía Spotify): **{track.title}**")
            else:
                await interaction.followup.send(f"🎶 Preparando (vía Spotify): **{track.title}**")

        elif looks_like_url(query):
            was_playing = service.current is not None
            track = await create_track(query, interaction.user)
            service.add(track)
            if was_playing:
                await interaction.followup.send(f"➕ Añadida a la cola: **{track.title}**")
            else:
                await interaction.followup.send(f"🎶 Preparando: **{track.title}**")

        else:
            tracks = await search_tracks(query, interaction.user)
            if not tracks:
                return await interaction.followup.send("No encontré resultados para esa búsqueda.")
            embed = build_search_embed(tracks, query)
            view = SearchView(tracks, interaction.user, service)
            await interaction.followup.send(embed=embed, view=view)

    @app_commands.command(name="queue", description="Muestra la cola de reproducción")
    async def queue(self, interaction: discord.Interaction) -> None:
        self._check_channel(interaction)
        service = self.get_or_create_service(interaction)
        if not service.current and not service.queue:
            return await interaction.response.send_message("La cola está vacía.")
        lines = []
        if service.current:
            lines.append(f"▶️ Ahora: **{service.current.title}**")
        for i, track in enumerate(list(service.queue)[:10], start=1):
            lines.append(f"`{i}.` {track.title} — pedido por {track.requester.mention}")
        if len(service.queue) > 10:
            lines.append(f"*... y {len(service.queue) - 10} más*")
        await interaction.response.send_message("\n".join(lines))

    @app_commands.command(name="skip", description="Salta la canción actual")
    async def skip(self, interaction: discord.Interaction) -> None:
        self._check_channel(interaction)
        perms.check(interaction, "skip")
        vc = interaction.guild.voice_client
        if not vc or not (vc.is_playing() or vc.is_paused()):
            return await interaction.response.send_message("No hay nada reproduciéndose.")
        vc.stop()
        await interaction.response.send_message("⏭️ Saltando canción.")

    @app_commands.command(name="pause", description="Pausa la reproducción")
    async def pause(self, interaction: discord.Interaction) -> None:
        self._check_channel(interaction)
        vc = interaction.guild.voice_client
        if not vc or not vc.is_playing():
            return await interaction.response.send_message("No hay música sonando.")
        vc.pause()
        await interaction.response.send_message("⏸️ Pausado.")

    @app_commands.command(name="resume", description="Reanuda la reproducción")
    async def resume(self, interaction: discord.Interaction) -> None:
        self._check_channel(interaction)
        vc = interaction.guild.voice_client
        if not vc or not vc.is_paused():
            return await interaction.response.send_message("No hay música pausada.")
        vc.resume()
        await interaction.response.send_message("▶️ Reanudado.")

    @app_commands.command(name="volume", description="Cambia el volumen (0-100)")
    async def volume(self, interaction: discord.Interaction, value: int) -> None:
        self._check_channel(interaction)
        perms.check(interaction, "volume")
        if not 0 <= value <= 100:
            return await interaction.response.send_message("El volumen debe estar entre 0 y 100.")
        service = self.get_or_create_service(interaction)
        service.volume = value / 100
        vc = interaction.guild.voice_client
        if vc and isinstance(vc.source, discord.PCMVolumeTransformer):
            vc.source.volume = service.volume
        await interaction.response.send_message(f"🔊 Volumen: **{value}%**")

    @app_commands.command(name="now", description="Muestra la canción que suena ahora")
    async def now(self, interaction: discord.Interaction) -> None:
        self._check_channel(interaction)
        service = self.get_or_create_service(interaction)
        if not service.current:
            return await interaction.response.send_message("No hay nada reproduciéndose.")
        embed = build_now_playing_embed(service.current, service)
        view = NowPlayingView(service)
        await interaction.response.send_message(embed=embed, view=view)

    @app_commands.command(name="replay", description="Reinicia la canción actual desde el principio")
    async def replay(self, interaction: discord.Interaction) -> None:
        self._check_channel(interaction)
        service = self.get_or_create_service(interaction)
        if not service.current:
            return await interaction.response.send_message("No hay nada reproduciéndose.")
        vc = interaction.guild.voice_client
        if not vc or not (vc.is_playing() or vc.is_paused()):
            return await interaction.response.send_message("No hay nada reproduciéndose.")
        service.seek(0)
        vc.stop()
        await interaction.response.send_message("🔄 Reiniciando canción.")

    @app_commands.command(name="seek", description="Salta a un punto de la canción (formato: 1:30 o 90)")
    async def seek(self, interaction: discord.Interaction, tiempo: str) -> None:
        self._check_channel(interaction)
        service = self.get_or_create_service(interaction)
        if not service.current:
            return await interaction.response.send_message("No hay nada reproduciéndose.")

        seconds = _parse_time(tiempo)
        if seconds is None:
            return await interaction.response.send_message(
                "Formato inválido. Usá `1:30` o `90` (segundos).", ephemeral=True
            )

        vc = interaction.guild.voice_client
        if not vc or not (vc.is_playing() or vc.is_paused()):
            return await interaction.response.send_message("No hay nada reproduciéndose.")

        service.seek(seconds)
        vc.stop()
        m, s = divmod(seconds, 60)
        await interaction.response.send_message(f"⏩ Saltando a `{m}:{s:02d}`.")

    @app_commands.command(name="previous", description="Vuelve a la canción anterior")
    async def previous(self, interaction: discord.Interaction) -> None:
        self._check_channel(interaction)
        perms.check(interaction, "previous")
        service = self.get_or_create_service(interaction)
        if not service.history:
            return await interaction.response.send_message("No hay historial de canciones.")
        prev_track = service.history.pop()
        service.queue.appendleft(prev_track)
        vc = interaction.guild.voice_client
        if vc and (vc.is_playing() or vc.is_paused()):
            vc.stop()
        await interaction.response.send_message(f"⏮️ Volviendo a: **{prev_track.title}**")

    @app_commands.command(name="autoplay", description="Activa o desactiva el autoplay al terminar la cola")
    @app_commands.choices(mode=[
        app_commands.Choice(name="On", value="on"),
        app_commands.Choice(name="Off", value="off"),
    ])
    async def autoplay(self, interaction: discord.Interaction, mode: str) -> None:
        self._check_channel(interaction)
        service = self.get_or_create_service(interaction)
        service.autoplay = mode == "on"
        icon = "▶️" if service.autoplay else "⏹️"
        await interaction.response.send_message(f"{icon} Autoplay: **{'activado' if service.autoplay else 'desactivado'}**")

    @app_commands.command(name="voteskip", description="Vota para saltear la canción actual")
    async def voteskip(self, interaction: discord.Interaction) -> None:
        self._check_channel(interaction)
        service = self.get_or_create_service(interaction)
        if not service.current:
            return await interaction.response.send_message("No hay nada reproduciéndose.")

        vc = interaction.guild.voice_client
        if not vc:
            return await interaction.response.send_message("No estoy en un canal de voz.")

        listeners = [m for m in vc.channel.members if not m.bot]
        required = max(1, math.ceil(len(listeners) / 2))

        if interaction.user.id in service._skip_votes:
            return await interaction.response.send_message("Ya votaste para saltear.", ephemeral=True)

        service._skip_votes.add(interaction.user.id)
        votes = len(service._skip_votes)

        if votes >= required:
            vc.stop()
            await interaction.response.send_message(
                f"⏭️ Saltando por votación ({votes}/{required} votos)."
            )
        else:
            await interaction.response.send_message(
                f"🗳️ Voto registrado ({votes}/{required} necesarios para saltear)."
            )

    @app_commands.command(name="loop", description="Configura el modo de repetición")
    @app_commands.choices(mode=[
        app_commands.Choice(name="Off", value="off"),
        app_commands.Choice(name="Song — repite la canción actual", value="song"),
        app_commands.Choice(name="Queue — repite toda la cola", value="queue"),
    ])
    async def loop(self, interaction: discord.Interaction, mode: str) -> None:
        self._check_channel(interaction)
        perms.check(interaction, "loop")
        service = self.get_or_create_service(interaction)
        service.loop_mode = LoopMode(mode)
        labels = {
            "off": "🔕 Loop desactivado",
            "song": "🔂 Repitiendo canción actual",
            "queue": "🔁 Repitiendo toda la cola",
        }
        await interaction.response.send_message(labels[mode])

    @app_commands.command(name="shuffle", description="Mezcla aleatoriamente la cola")
    async def shuffle(self, interaction: discord.Interaction) -> None:
        self._check_channel(interaction)
        service = self.get_or_create_service(interaction)
        if len(service.queue) < 2:
            return await interaction.response.send_message("La cola tiene menos de 2 canciones.")
        service.shuffle()
        await interaction.response.send_message(f"🔀 Cola mezclada ({len(service.queue)} canciones).")

    @app_commands.command(name="remove", description="Elimina una canción de la cola por posición")
    async def remove(self, interaction: discord.Interaction, position: int) -> None:
        self._check_channel(interaction)
        service = self.get_or_create_service(interaction)
        try:
            removed = service.remove(position)
        except ValueError as e:
            return await interaction.response.send_message(f"⚠️ {e}", ephemeral=True)
        await interaction.response.send_message(f"🗑️ Eliminada: **{removed.title}**")

    @app_commands.command(name="move", description="Mueve una canción a otra posición en la cola")
    async def move(self, interaction: discord.Interaction, desde: int, hacia: int) -> None:
        self._check_channel(interaction)
        service = self.get_or_create_service(interaction)
        try:
            service.move(desde, hacia)
        except ValueError as e:
            return await interaction.response.send_message(f"⚠️ {e}", ephemeral=True)
        await interaction.response.send_message(f"↕️ Canción movida de `#{desde}` a `#{hacia}`.")

    @app_commands.command(name="clear", description="Limpia la cola de reproducción")
    async def clear(self, interaction: discord.Interaction) -> None:
        self._check_channel(interaction)
        perms.check(interaction, "clear")
        service = self.get_or_create_service(interaction)
        service.queue.clear()
        await interaction.response.send_message("🧹 Cola limpiada.")

    @app_commands.command(name="leave", description="Desconecta el bot del canal de voz")
    async def leave(self, interaction: discord.Interaction) -> None:
        self._check_channel(interaction)
        perms.check(interaction, "leave")
        service = self.get_or_create_service(interaction)
        await service.disconnect()
        self._states.pop(interaction.guild_id, None)
        await interaction.response.send_message("🛑 Devil Trigger se apagó.")

    async def cog_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        msg = str(error)
        if interaction.response.is_done():
            await interaction.followup.send(f"⚠️ {msg}", ephemeral=True)
        else:
            await interaction.response.send_message(f"⚠️ {msg}", ephemeral=True)


def _parse_time(value: str) -> int | None:
    value = value.strip()
    if ":" in value:
        parts = value.split(":")
        try:
            if len(parts) == 2:
                return int(parts[0]) * 60 + int(parts[1])
            if len(parts) == 3:
                return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        except ValueError:
            return None
    try:
        return int(value)
    except ValueError:
        return None


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(MusicCog(bot))
