from __future__ import annotations

from typing import TYPE_CHECKING

import discord

from services.music_service import LoopMode

if TYPE_CHECKING:
    from models.track import Track
    from services.music_service import MusicService

_LOOP_ICONS = {LoopMode.OFF: "🔕", LoopMode.SONG: "🔂", LoopMode.QUEUE: "🔁"}
_LOOP_CYCLE = [LoopMode.OFF, LoopMode.SONG, LoopMode.QUEUE]


def _progress_bar(elapsed: int, total: int, width: int = 14) -> str:
    if not total:
        return ""
    ratio = min(elapsed / total, 1.0)
    filled = int(ratio * width)
    bar = "█" * filled + "░" * (width - filled)
    e = f"{elapsed // 60}:{elapsed % 60:02d}"
    t = f"{total // 60}:{total % 60:02d}"
    return f"`{e}` [{bar}] `{t}`"


def build_now_playing_embed(track: Track, service: MusicService) -> discord.Embed:
    embed = discord.Embed(
        title="Now Playing",
        description=f"**[{track.title}]({track.webpage_url})**",
        color=discord.Color.purple(),
    )
    embed.add_field(name="Pedido por", value=track.requester.mention, inline=True)

    if track.duration:
        minutes, seconds = divmod(track.duration, 60)
        embed.add_field(name="Duración", value=f"`{minutes}:{seconds:02d}`", inline=True)

    if track.duration:
        bar = _progress_bar(service.elapsed_seconds, track.duration)
        if bar:
            embed.add_field(name="​", value=bar, inline=False)

    loop_icon = _LOOP_ICONS[service.loop_mode]
    autoplay_icon = "▶️" if service.autoplay else "⏹️"
    embed.add_field(
        name="​",
        value=(
            f"Queue: `{len(service.queue)}` · "
            f"Vol: `{int(service.volume * 100)}%` · "
            f"Loop: {loop_icon} · "
            f"Autoplay: {autoplay_icon}"
        ),
        inline=False,
    )

    if track.thumbnail:
        embed.set_thumbnail(url=track.thumbnail)

    return embed


class NowPlayingView(discord.ui.View):
    def __init__(self, service: MusicService) -> None:
        super().__init__(timeout=3600)
        self.service = service

    # ── Row 0: playback controls ──────────────────────────────────────────────

    @discord.ui.button(label="Pause", emoji="⏸️", style=discord.ButtonStyle.secondary, row=0)
    async def pause_resume(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
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
        from services import permissions as perms
        from discord import app_commands
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
        from services import permissions as perms
        from discord import app_commands
        try:
            perms.check(interaction, "leave")
        except app_commands.AppCommandError as e:
            return await interaction.response.send_message(str(e), ephemeral=True)
        await self.service.disconnect()
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(view=self)

    # ── Row 1: queue & audio controls ─────────────────────────────────────────

    @discord.ui.button(label="Loop", emoji="🔕", style=discord.ButtonStyle.secondary, row=1)
    async def loop_toggle(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        current_idx = _LOOP_CYCLE.index(self.service.loop_mode)
        next_mode = _LOOP_CYCLE[(current_idx + 1) % len(_LOOP_CYCLE)]
        self.service.loop_mode = next_mode
        button.emoji = discord.PartialEmoji.from_str(_LOOP_ICONS[next_mode])
        await interaction.response.edit_message(view=self)

    @discord.ui.button(label="Shuffle", emoji="🔀", style=discord.ButtonStyle.secondary, row=1)
    async def shuffle(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        if len(self.service.queue) < 2:
            return await interaction.response.send_message(
                "La cola tiene menos de 2 canciones.", ephemeral=True
            )
        self.service.shuffle()
        await interaction.response.send_message(
            f"🔀 Cola mezclada ({len(self.service.queue)} canciones).", ephemeral=True
        )

    @discord.ui.button(label="Vol -", emoji="🔉", style=discord.ButtonStyle.secondary, row=1)
    async def vol_down(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        self.service.volume = max(0.0, self.service.volume - 0.1)
        vc = interaction.guild.voice_client
        if vc and isinstance(vc.source, discord.PCMVolumeTransformer):
            vc.source.volume = self.service.volume
        pct = int(self.service.volume * 100)
        await interaction.response.send_message(f"🔉 Volumen: **{pct}%**", ephemeral=True)

    @discord.ui.button(label="Vol +", emoji="🔊", style=discord.ButtonStyle.secondary, row=1)
    async def vol_up(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        self.service.volume = min(1.0, self.service.volume + 0.1)
        vc = interaction.guild.voice_client
        if vc and isinstance(vc.source, discord.PCMVolumeTransformer):
            vc.source.volume = self.service.volume
        pct = int(self.service.volume * 100)
        await interaction.response.send_message(f"🔊 Volumen: **{pct}%**", ephemeral=True)
