import asyncio
import logging
import random
import time
from collections import deque
from enum import Enum
from typing import Awaitable, Callable, Optional

import discord
from discord.ext import commands

from config import FFMPEG_OPTIONS
from models.track import Track
from services import history_store
from services import stats as stats_store
from services.audio_mixer import GuildAudioCoordinator
from services.vote_manager import VoteManager

logger = logging.getLogger(__name__)

OnTrackStart = Optional[Callable[["MusicService", Track], Awaitable[None]]]


class LoopMode(Enum):
    OFF = "off"
    SONG = "song"
    QUEUE = "queue"


class AudioFilter(Enum):
    OFF = "off"
    BASS_BOOST = "bassboost"
    NIGHTCORE = "nightcore"
    VAPORWAVE = "vaporwave"
    SLOWED = "slowed"
    KARAOKE = "karaoke"


FILTER_ARGS: dict[AudioFilter, str] = {
    AudioFilter.OFF: "",
    AudioFilter.BASS_BOOST: "bass=g=10",
    AudioFilter.NIGHTCORE: "asetrate=44100*1.25,aresample=44100",
    AudioFilter.VAPORWAVE: "asetrate=44100*0.8,aresample=44100",
    AudioFilter.SLOWED: "atempo=0.85",
    AudioFilter.KARAOKE: "pan=stereo|c0=c0-c1|c1=c1-c0",
}


class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, track: Track, *, volume: float, seek_to: int = 0, audio_filter: "AudioFilter | None" = None):
        options = dict(FFMPEG_OPTIONS)
        if seek_to:
            options["before_options"] = f"{options.get('before_options', '')} -ss {seek_to}"
        filter_str = FILTER_ARGS.get(audio_filter, "") if audio_filter else ""
        if filter_str:
            existing = options.get("options", "").strip()
            options["options"] = f"{existing} -af \"{filter_str}\"".strip()
        source = discord.FFmpegPCMAudio(track.stream_url, **options)
        super().__init__(source, volume)
        self.track = track


class MusicService:
    def __init__(self, bot: commands.Bot, guild: discord.Guild):
        self.bot = bot
        self.guild = guild
        self.queue: deque[Track] = deque()
        self.history: list[Track] = []
        self.current: Optional[Track] = None
        self.volume = 0.5
        self.loop_mode: LoopMode = LoopMode.OFF
        self.audio_filter: AudioFilter = AudioFilter.OFF
        self.autoplay: bool = False
        self.text_channel: Optional[discord.abc.Messageable] = None
        self.on_track_start: OnTrackStart = None
        self.skip_votes: VoteManager = VoteManager(threshold=0.5, min_votes=1)
        self._pending_seek: Optional[int] = None
        self._seek_position: int = 0
        self._track_start_time: float = 0.0
        self._queue_event = asyncio.Event()
        self._next_event = asyncio.Event()
        self._player_task: Optional[asyncio.Task] = None
        self.audio = GuildAudioCoordinator(bot, guild)

    @property
    def elapsed_seconds(self) -> int:
        if not self.current or not self._track_start_time:
            return 0
        paused = self.audio.music_paused_seconds
        if self.audio._music_pause_started is not None:
            paused += time.monotonic() - self.audio._music_pause_started
        return self._seek_position + int(time.monotonic() - self._track_start_time - paused)

    def add(self, track: Track) -> None:
        self.queue.append(track)
        self._queue_event.set()
        self._start_player()

    def shuffle(self) -> None:
        tracks = list(self.queue)
        random.shuffle(tracks)
        self.queue = deque(tracks)
        self._queue_event.set()

    def remove(self, position: int) -> Track:
        if not 1 <= position <= len(self.queue):
            raise ValueError(f"Posición {position} fuera de rango (1-{len(self.queue)}).")
        tracks = list(self.queue)
        removed = tracks.pop(position - 1)
        self.queue = deque(tracks)
        return removed

    def move(self, from_pos: int, to_pos: int) -> None:
        n = len(self.queue)
        if not 1 <= from_pos <= n or not 1 <= to_pos <= n:
            raise ValueError(f"Posición fuera de rango (1-{n}).")
        tracks = list(self.queue)
        track = tracks.pop(from_pos - 1)
        tracks.insert(to_pos - 1, track)
        self.queue = deque(tracks)

    def seek(self, seconds: int) -> None:
        self._pending_seek = seconds

    def _start_player(self) -> None:
        if self._player_task is None or self._player_task.done():
            self._player_task = asyncio.create_task(self._player_loop())

    async def _wait_for_track(self) -> Optional[Track]:
        while not self.queue:
            self._queue_event.clear()
            try:
                await asyncio.wait_for(self._queue_event.wait(), timeout=300)
            except asyncio.TimeoutError:
                return None
        return self.queue.popleft()

    async def _player_loop(self) -> None:
        await self.bot.wait_until_ready()

        while not self.bot.is_closed():
            track = await self._wait_for_track()

            if track is None:
                await self.disconnect(cancel_player=False)
                return

            voice_client = self.guild.voice_client
            if voice_client is None or not voice_client.is_connected():
                self.current = None
                continue

            self.current = track
            self.skip_votes.reset()

            if track.stream_url is None:
                try:
                    from services.extractor import resolve_track
                    await resolve_track(track)
                except Exception as e:
                    logger.warning("No se pudo resolver track title=%r error=%s", track.title, e)
                    self.current = None
                    continue

            if not track.stream_url:
                self.current = None
                continue

            seek_to = self._seek_position
            self._seek_position = 0
            source = YTDLSource(track, volume=self.volume, seek_to=seek_to, audio_filter=self.audio_filter)
            self._track_start_time = time.monotonic()

            if self.on_track_start:
                await self.on_track_start(self, track)
            elif self.text_channel:
                await self.text_channel.send(f"🎵 Reproduciendo: **{track.title}**")

            try:
                await self.audio.play_music(source)
            except RuntimeError:
                self.current = None
                continue
            self._track_start_time = 0.0

            if self._pending_seek is not None:
                self._seek_position = self._pending_seek
                self._pending_seek = None
                self.queue.appendleft(track)
                self._queue_event.set()
            elif self.loop_mode == LoopMode.SONG:
                self.queue.appendleft(track)
                self._queue_event.set()
            else:
                self.history.append(track)
                history_store.push(
                    self.guild.id,
                    {
                        "title": track.title,
                        "webpage_url": track.webpage_url,
                        "thumbnail": track.thumbnail,
                        "requester_id": track.requester.id,
                        "requester_name": track.requester.display_name,
                    },
                )
                stats_store.record_play(
                    self.guild.id,
                    track.requester.id,
                    track.title,
                    track.webpage_url,
                )
                if len(self.history) > 20:
                    self.history.pop(0)

                if self.loop_mode == LoopMode.QUEUE:
                    self.queue.append(track)
                    self._queue_event.set()
                elif self.autoplay and not self.queue:
                    await self._queue_autoplay_track(track)

            self.current = None

    async def _queue_autoplay_track(self, last_track: Track) -> None:
        from services.extractor import get_related_track
        try:
            related = await get_related_track(last_track, last_track.requester)
            if related:
                self.add(related)
                if self.text_channel:
                    await self.text_channel.send(f"🤖 Autoplay: **{related.title}**")
        except Exception as e:
            logger.warning("Autoplay error guild=%s error=%s", self.guild.id, e)

    async def disconnect(self, *, cancel_player: bool = True) -> None:
        await self.audio.close()
        voice_client = self.guild.voice_client
        if voice_client:
            if voice_client.is_playing() or voice_client.is_paused():
                voice_client.stop()
            await voice_client.disconnect(force=True)

        self.queue.clear()
        self.current = None

        if cancel_player and self._player_task and not self._player_task.done():
            self._player_task.cancel()

    def stop_current(self) -> None:
        """Stop only the music layer; active TTS continues safely."""
        self.audio.stop_music()

    def set_volume(self, volume: float) -> None:
        self.volume = volume
        with self.audio._lock:
            source = self.audio._music_source
            if isinstance(source, discord.PCMVolumeTransformer):
                source.volume = volume

    async def update_panel(self) -> None:
        """Refresh the persistent music panel embed if one exists for this guild."""
        from services import guild_config
        from ui.player_view import NowPlayingView, build_now_playing_embed

        channel_id, message_id = guild_config.panel_ids(self.guild.id)
        if channel_id is None or message_id is None:
            return

        channel = self.guild.get_channel(channel_id)
        if not channel:
            return

        try:
            message = await channel.fetch_message(message_id)
        except discord.NotFound:
            guild_config.set_panel(self.guild.id, None, None)
            return
        except discord.HTTPException:
            return  # transient error, leave panel IDs intact

        try:
            if self.current:
                embed = build_now_playing_embed(self.current, self)
                view = NowPlayingView(self)
                await message.edit(embed=embed, view=view)
            else:
                embed = discord.Embed(
                    title="🎵 Panel de Música",
                    description="Sin reproducción activa.",
                    color=discord.Color.greyple(),
                )
                await message.edit(embed=embed, view=None)
        except discord.HTTPException:
            return
