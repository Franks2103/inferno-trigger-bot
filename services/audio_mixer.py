"""A single PCM output per guild that can duck music under local TTS audio."""

import asyncio
import logging
import threading
import time
from array import array
from typing import Optional

import discord

logger = logging.getLogger(__name__)


def _scale_pcm(data: bytes, factor: float) -> bytes:
    samples = array("h")
    samples.frombytes(data)
    for index, sample in enumerate(samples):
        samples[index] = max(-32768, min(32767, int(sample * factor)))
    return samples.tobytes()


def _mix_pcm(left: bytes, right: bytes) -> bytes:
    left_samples = array("h")
    right_samples = array("h")
    left_samples.frombytes(left)
    right_samples.frombytes(right)
    length = min(len(left_samples), len(right_samples))
    for index in range(length):
        left_samples[index] = max(-32768, min(32767, left_samples[index] + right_samples[index]))
    return left_samples.tobytes()


class MixedPCMSource(discord.AudioSource):
    """Mixes two PCM sources on Discord's audio thread without changing voice clients."""

    def __init__(self, coordinator: "GuildAudioCoordinator"):
        self.coordinator = coordinator
        self._idle_since: float | None = None

    def is_opus(self) -> bool:
        return False

    def read(self) -> bytes:
        with self.coordinator._lock:
            music = self.coordinator._music_source
            speech = self.coordinator._speech_source
            pause_music = self.coordinator.pause_music and speech is not None

        # Do not consume music frames while speech is active: this is a real
        # pause at the source layer, while the shared VoiceClient keeps playing.
        music_data = music.read() if music and not pause_music else b""
        speech_data = speech.read() if speech else b""

        if music and not music_data:
            self.coordinator._music_finished_threadsafe()
        if speech and not speech_data:
            self.coordinator._speech_finished_threadsafe()

        if music_data and speech_data:
            return _mix_pcm(music_data, speech_data)
        if music_data:
            return music_data
        if speech_data:
            return speech_data

        # Keep the player alive briefly while the event loop installs the next
        # queue item. Returning b"" immediately creates a race at track changes.
        now = time.monotonic()
        if self._idle_since is None:
            self._idle_since = now
        if now - self._idle_since < 0.35:
            return b"\x00" * 3840
        return b""

    def cleanup(self) -> None:
        return None


class GuildAudioCoordinator:
    """Coordinates music and speech sources for exactly one Discord guild."""

    def __init__(self, bot, guild: discord.Guild):
        self.bot = bot
        self.guild = guild
        self._lock = threading.Lock()
        self._mixer = MixedPCMSource(self)
        self._music_source: Optional[discord.AudioSource] = None
        self._speech_source: Optional[discord.AudioSource] = None
        self._music_done: Optional[asyncio.Event] = None
        self._speech_done: Optional[asyncio.Event] = None
        self.pause_music = True
        self.music_paused_seconds = 0.0
        self._music_pause_started: float | None = None

    async def _ensure_playing(self) -> None:
        voice_client = self.guild.voice_client
        if voice_client is None or not voice_client.is_connected():
            raise RuntimeError("No hay conexión de voz disponible.")
        if not voice_client.is_playing() and not voice_client.is_paused():
            voice_client.play(self._mixer, after=self._after_play)

    def _after_play(self, error: Optional[Exception]) -> None:
        if error:
            logger.error("audio mixer error guild=%s error=%s", self.guild.id, error)

    async def play_music(self, source: discord.AudioSource) -> None:
        done = asyncio.Event()
        with self._lock:
            self._music_source = source
            self._music_done = done
            self.music_paused_seconds = 0.0
            self._music_pause_started = None
            self._mixer._idle_since = None
        await self._ensure_playing()
        await done.wait()

    async def play_speech(self, source: discord.AudioSource, *, pause_music: bool) -> None:
        done = asyncio.Event()
        with self._lock:
            self._speech_source = source
            self._speech_done = done
            self.pause_music = pause_music
            if pause_music and self._music_source is not None:
                self._music_pause_started = time.monotonic()
            self._mixer._idle_since = None
        await self._ensure_playing()
        await done.wait()

    def stop_music(self) -> None:
        with self._lock:
            source = self._music_source
            self._music_source = None
            done = self._music_done
        if source:
            source.cleanup()
        if done:
            self.bot.loop.call_soon_threadsafe(done.set)

    def stop_speech(self) -> None:
        with self._lock:
            source = self._speech_source
            self._speech_source = None
            done = self._speech_done
            if self._music_pause_started is not None:
                self.music_paused_seconds += time.monotonic() - self._music_pause_started
                self._music_pause_started = None
        if source:
            source.cleanup()
        if done:
            self.bot.loop.call_soon_threadsafe(done.set)

    def _music_finished_threadsafe(self) -> None:
        with self._lock:
            if self._music_source is None:
                return
            self._music_source = None
            done = self._music_done
        if done:
            self.bot.loop.call_soon_threadsafe(done.set)

    def _speech_finished_threadsafe(self) -> None:
        with self._lock:
            if self._speech_source is None:
                return
            self._speech_source = None
            done = self._speech_done
            if self._music_pause_started is not None:
                self.music_paused_seconds += time.monotonic() - self._music_pause_started
                self._music_pause_started = None
        if done:
            self.bot.loop.call_soon_threadsafe(done.set)

    async def close(self) -> None:
        self.stop_music()
        self.stop_speech()
