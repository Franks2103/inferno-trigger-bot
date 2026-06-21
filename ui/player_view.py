from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import app_commands

from services import favorites as favs_svc
from services import permissions as perms
from services import stats as stats_svc
from services.music_service import LoopMode

if TYPE_CHECKING:
    from models.track import Track
    from services.music_service import MusicService

_LOOP_ICONS = {LoopMode.OFF: "🔕", LoopMode.SONG: "🔂", LoopMode.QUEUE: "🔁"}
_LOOP_CYCLE = [LoopMode.OFF, LoopMode.SONG, LoopMode.QUEUE]


def _progress_bar(elapsed: int, total: int, width: int = 16) -> str:
    if not total:
        return ""
    ratio = min(elapsed / total, 1.0)
    pos = int(ratio * width)
    bar = "━" * pos + "●" + "─" * max(0, width - pos)
    e = f"{elapsed // 60}:{elapsed % 60:02d}"
    t = f"{total // 60}:{total % 60:02d}"
    return f"🎵 {bar} `{e} / {t}`"


def build_now_playing_embed(
    track: Track, service: MusicService, *, paused: bool = False
) -> discord.Embed:
    color = discord.Color.yellow() if paused else discord.Color.green()
    embed = discord.Embed(
        title="⏸ En pausa" if paused else "▶️ Reproduciendo",
        description=f"**[{track.title}]({track.webpage_url})**",
        color=color,
    )
    embed.add_field(name="Pedido por", value=track.requester.mention, inline=True)

    if track.duration:
        minutes, seconds = divmod(track.duration, 60)
        embed.add_field(name="Duración", value=f"`{minutes}:{seconds:02d}`", inline=True)

    loop_icon = _LOOP_ICONS[service.loop_mode]
    autoplay_icon = "▶️" if service.autoplay else "⏹️"
    embed.add_field(
        name="Estado",
        value=f"Vol: `{int(service.volume * 100)}%` · Loop: {loop_icon} · Autoplay: {autoplay_icon}",
        inline=False,
    )

    if track.duration:
        bar = _progress_bar(service.elapsed_seconds, track.duration)
        if bar:
            embed.add_field(name="​", value=bar, inline=False)

    queue_list = list(service.queue)[:3]
    if queue_list:
        lines = [f"`{i + 1}.` {t.title}" for i, t in enumerate(queue_list)]
        remaining = len(service.queue) - 3
        if remaining > 0:
            lines.append(f"_...y {remaining} más_")
        embed.add_field(name="🎶 En cola", value="\n".join(lines), inline=False)

    if track.thumbnail:
        embed.set_image(url=track.thumbnail)

    vc = service.guild.voice_client
    members_in_vc = max(0, len(vc.channel.members) - 1) if vc and vc.channel else 0
    person_label = "persona" if members_in_vc == 1 else "personas"
    embed.set_footer(text=f"Inferno Trigger · {members_in_vc} {person_label} en el canal")

    return embed


# ── Search Modal ──────────────────────────────────────────────────────────────

class SearchModal(discord.ui.Modal, title="Buscar canción"):
    query_field = discord.ui.TextInput(
        label="Búsqueda",
        placeholder="Nombre del artista o canción...",
    )

    def __init__(self, service: MusicService) -> None:
        super().__init__()
        self.service = service

    async def on_submit(self, interaction: discord.Interaction) -> None:
        from services.extractor import search_tracks

        if not interaction.guild.voice_client:
            return await interaction.response.send_message(
                "El bot no está en ningún canal de voz.", ephemeral=True
            )
        await interaction.response.defer(ephemeral=True)
        tracks = await search_tracks(self.query_field.value, interaction.user, limit=1)
        if not tracks:
            await interaction.followup.send("No se encontraron resultados.", ephemeral=True)
            return
        track = tracks[0]
        if self.service.dj_mode and self.service.current:
            self.service.add_next(track)
            await interaction.followup.send(
                f"⚡ Siguiente (modo DJ): **{track.title}**", ephemeral=True
            )
        else:
            self.service.add(track)
            await interaction.followup.send(
                f"🔍 Agregado a la cola: **{track.title}**", ephemeral=True
            )


# ── Now Playing View ──────────────────────────────────────────────────────────

class NowPlayingView(discord.ui.View):
    def __init__(self, service: MusicService) -> None:
        super().__init__(timeout=3600)
        self.service = service

    # ── Fila 0: controles de reproducción ────────────────────────────────────

    @discord.ui.button(label="Anterior", emoji="⏮️", style=discord.ButtonStyle.secondary, row=0)
    async def previous(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        try:
            perms.check(interaction, "previous")
        except app_commands.AppCommandError as e:
            return await interaction.response.send_message(str(e), ephemeral=True)
        if not self.service.history:
            return await interaction.response.send_message("No hay historial de canciones.", ephemeral=True)
        prev_track = self.service.history.pop()
        self.service.queue.appendleft(prev_track)
        self.service.stop_current()
        await interaction.response.send_message(
            f"⏮️ Volviendo a: **{prev_track.title}**", ephemeral=True
        )

    @discord.ui.button(label="Pause", emoji="⏸️", style=discord.ButtonStyle.secondary, row=0)
    async def pause_resume(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        vc = interaction.guild.voice_client
        if not vc:
            return await interaction.response.send_message("No estoy conectado.", ephemeral=True)
        if vc.is_playing():
            vc.pause()
            button.label = "Resume"
            button.emoji = discord.PartialEmoji.from_str("▶️")
            await interaction.response.edit_message(view=self)
        elif vc.is_paused():
            vc.resume()
            button.label = "Pause"
            button.emoji = discord.PartialEmoji.from_str("⏸️")
            await interaction.response.edit_message(view=self)
        else:
            await interaction.response.send_message("No hay música sonando.", ephemeral=True)

    @discord.ui.button(label="Skip", emoji="⏭️", style=discord.ButtonStyle.primary, row=0)
    async def skip(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        try:
            perms.check(interaction, "skip")
        except app_commands.AppCommandError as e:
            return await interaction.response.send_message(str(e), ephemeral=True)
        vc = interaction.guild.voice_client
        if self.service.current and vc and (vc.is_playing() or vc.is_paused()):
            self.service.stop_current()
            await interaction.response.send_message("⏭️ Saltando canción.", ephemeral=True)
        else:
            await interaction.response.send_message("No hay nada reproduciéndose.", ephemeral=True)

    @discord.ui.button(label="Stop", emoji="⏹️", style=discord.ButtonStyle.danger, row=0)
    async def stop(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        try:
            perms.check(interaction, "leave")
        except app_commands.AppCommandError as e:
            return await interaction.response.send_message(str(e), ephemeral=True)
        await self.service.disconnect()
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(view=self)

    # ── Fila 1: audio y cola ─────────────────────────────────────────────────

    @discord.ui.button(label="Loop", emoji="🔕", style=discord.ButtonStyle.secondary, row=1)
    async def loop_toggle(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        current_idx = _LOOP_CYCLE.index(self.service.loop_mode)
        next_mode = _LOOP_CYCLE[(current_idx + 1) % len(_LOOP_CYCLE)]
        self.service.loop_mode = next_mode
        button.emoji = discord.PartialEmoji.from_str(_LOOP_ICONS[next_mode])
        await interaction.response.edit_message(view=self)

    @discord.ui.button(label="Shuffle", emoji="🔀", style=discord.ButtonStyle.secondary, row=1)
    async def shuffle(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if len(self.service.queue) < 2:
            return await interaction.response.send_message(
                "La cola tiene menos de 2 canciones.", ephemeral=True
            )
        self.service.shuffle()
        await interaction.response.send_message(
            f"🔀 Cola mezclada ({len(self.service.queue)} canciones).", ephemeral=True
        )

    @discord.ui.button(label="Vol -", emoji="🔉", style=discord.ButtonStyle.secondary, row=1)
    async def vol_down(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.service.volume = max(0.0, self.service.volume - 0.1)
        self.service.set_volume(self.service.volume)
        await interaction.response.send_message(
            f"🔉 Volumen: **{int(self.service.volume * 100)}%**", ephemeral=True
        )

    @discord.ui.button(label="Vol +", emoji="🔊", style=discord.ButtonStyle.secondary, row=1)
    async def vol_up(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.service.volume = min(1.0, self.service.volume + 0.1)
        self.service.set_volume(self.service.volume)
        await interaction.response.send_message(
            f"🔊 Volumen: **{int(self.service.volume * 100)}%**", ephemeral=True
        )

    # ── Fila 2: favoritos, cola, búsqueda, stats ─────────────────────────────

    @discord.ui.button(label="Favorito", emoji="❤️", style=discord.ButtonStyle.secondary, row=2)
    async def add_favorite(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        track = self.service.current
        if not track:
            return await interaction.response.send_message("No hay canción reproduciéndose.", ephemeral=True)
        result = favs_svc.add(interaction.user.id, track.title, track.webpage_url, track.thumbnail)
        if result == "ok":
            await interaction.response.send_message(
                f"❤️ Guardado en favoritos: **{track.title}**", ephemeral=True
            )
        elif result == "duplicate":
            await interaction.response.send_message("Ya está en tus favoritos.", ephemeral=True)
        else:
            await interaction.response.send_message(
                "Tus favoritos están llenos (máx. 25).", ephemeral=True
            )

    @discord.ui.button(label="Ver Cola", emoji="📋", style=discord.ButtonStyle.secondary, row=2)
    async def view_queue(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        queue_list = list(self.service.queue)
        if not queue_list:
            return await interaction.response.send_message("La cola está vacía.", ephemeral=True)
        lines = [f"`{i + 1}.` {t.title}" for i, t in enumerate(queue_list[:10])]
        if len(queue_list) > 10:
            lines.append(f"_...y {len(queue_list) - 10} más_")
        embed = discord.Embed(
            title=f"📋 Cola ({len(queue_list)} canciones)",
            description="\n".join(lines),
            color=discord.Color.blurple(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Buscar", emoji="🔍", style=discord.ButtonStyle.secondary, row=2)
    async def search(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_modal(SearchModal(self.service))

    @discord.ui.button(label="Mis Stats", emoji="📊", style=discord.ButtonStyle.secondary, row=2)
    async def my_stats(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        plays = stats_svc.user_plays(interaction.guild_id, interaction.user.id)
        total = stats_svc.guild_stats(interaction.guild_id).get("total", 0)
        embed = discord.Embed(title="📊 Tus stats en este servidor", color=discord.Color.blurple())
        embed.add_field(name="Canciones pedidas", value=f"`{plays}`", inline=True)
        embed.add_field(name="Total del servidor", value=f"`{total}`", inline=True)
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        await interaction.response.send_message(embed=embed, ephemeral=True)
