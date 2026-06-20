import asyncio
import random
import time
from collections import deque
from enum import Enum
from typing import Awaitable, Callable, Optional

import discord
from discord.ext import commands

from config import FFMPEG_OPTIONS
from models.track import Track
from services.vote_manager import VoteManager

OnTrackStart = Optional[Callable[["MusicService", Track], Awaitable[None]]]


class LoopMode(Enum):
    OFF = "off"
    SONG = "song"
    QUEUE = "queue"


class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, track: Track, *, volume: float, seek_to: int = 0):
        options = dict(FFMPEG_OPTIONS)
        if seek_to:
            options["before_options"] = f"{options.get('before_options', '')} -ss {seek_to}"
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

    @property
    def elapsed_seconds(self) -> int:
        if not self.current or not self._track_start_time:
            return 0
        return self._seek_position + int(time.monotonic() - self._track_start_time)

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
            self._next_event.clear()
            self.skip_votes.reset()

            if track.stream_url is None:
                try:
                    from services.extractor import resolve_track
                    await resolve_track(track)
                except Exception as e:
                    print(f"No se pudo resolver '{track.title}': {e}")
                    self.current = None
                    continue

            if not track.stream_url:
                self.current = None
                continue

            seek_to = self._seek_position
            self._seek_position = 0
            source = YTDLSource(track, volume=self.volume, seek_to=seek_to)
            self._track_start_time = time.monotonic()

            def after_play(error: Optional[Exception]) -> None:
                if error:
                    print(f"Error al reproducir: {error}")
                self.bot.loop.call_soon_threadsafe(self._next_event.set)

            voice_client.play(source, after=after_play)

            if self.on_track_start:
                await self.on_track_start(self, track)
            elif self.text_channel:
                await self.text_channel.send(f"🎵 Reproduciendo: **{track.title}**")

            await self._next_event.wait()
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
            print(f"Autoplay error: {e}")

    async def disconnect(self, *, cancel_player: bool = True) -> None:
        voice_client = self.guild.voice_client
        if voice_client:
            if voice_client.is_playing() or voice_client.is_paused():
                voice_client.stop()
            await voice_client.disconnect(force=True)

        self.queue.clear()
        self.current = None

        if cancel_player and self._player_task and not self._player_task.done():
            self._player_task.cancel()
