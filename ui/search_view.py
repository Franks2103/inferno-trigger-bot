from __future__ import annotations

from typing import TYPE_CHECKING

import discord

if TYPE_CHECKING:
    from models.track import Track
    from services.music_service import MusicService

_NUMBER_EMOJIS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]


def build_search_embed(tracks: list[Track], query: str) -> discord.Embed:
    embed = discord.Embed(
        title=f"🔍 Resultados para: {query}",
        color=discord.Color.blurple(),
    )
    for i, track in enumerate(tracks, start=1):
        duration = ""
        if track.duration:
            m, s = divmod(track.duration, 60)
            duration = f" `{m}:{s:02d}`"
        embed.add_field(
            name=f"{i}. {track.title}{duration}",
            value=f"[Ver en YouTube]({track.webpage_url})",
            inline=False,
        )
    embed.set_footer(text="Tenés 30 segundos para elegir.")
    return embed


class SearchView(discord.ui.View):
    def __init__(
        self,
        tracks: list[Track],
        requester: discord.Member,
        service: MusicService,
    ) -> None:
        super().__init__(timeout=30)
        self.tracks = tracks
        self.requester = requester
        self.service = service

        for i, track in enumerate(tracks):
            btn = discord.ui.Button(
                label=str(i + 1),
                emoji=_NUMBER_EMOJIS[i],
                style=discord.ButtonStyle.primary,
                row=0,
            )
            btn.callback = self._make_pick_callback(track)
            self.add_item(btn)

        cancel = discord.ui.Button(
            label="Cancelar",
            emoji="❌",
            style=discord.ButtonStyle.secondary,
            row=1,
        )
        cancel.callback = self._cancel_callback
        self.add_item(cancel)

    def _make_pick_callback(self, track: Track):
        async def callback(interaction: discord.Interaction) -> None:
            if interaction.user.id != self.requester.id:
                return await interaction.response.send_message(
                    "Solo quien buscó puede elegir.", ephemeral=True
                )
            if self.service.dj_mode and self.service.current:
                self.service.add_next(track)
                msg = f"⚡ Siguiente (modo DJ): **{track.title}**"
            else:
                self.service.add(track)
                msg = f"🎶 Añadida: **{track.title}**"
            self._disable_all()
            await interaction.response.edit_message(
                content=msg,
                embed=None,
                view=self,
            )
            self.stop()

        return callback

    async def _cancel_callback(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.requester.id:
            return await interaction.response.send_message(
                "Solo quien buscó puede cancelar.", ephemeral=True
            )
        self._disable_all()
        await interaction.response.edit_message(
            content="❌ Búsqueda cancelada.",
            embed=None,
            view=self,
        )
        self.stop()

    async def on_timeout(self) -> None:
        self._disable_all()

    def _disable_all(self) -> None:
        for item in self.children:
            item.disabled = True
