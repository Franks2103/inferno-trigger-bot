"""Bounded FIFO TTS queue, isolated per guild."""

import asyncio
import logging
from collections import Counter, deque
from dataclasses import dataclass
from pathlib import Path

import discord

from services.audio_mixer import GuildAudioCoordinator
from services import guild_config
from services.tts_service import TtsProviderError, TtsService

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class TtsItem:
    user_id: int
    display_name: str
    text: str
    message_id: int


class TtsBridgeQueue:
    MAX_PER_USER = 3
    MAX_PER_GUILD = 20

    def __init__(self, bot, guild: discord.Guild, coordinator: GuildAudioCoordinator, service: TtsService):
        self.bot = bot
        self.guild = guild
        self.coordinator = coordinator
        self.service = service
        self.items: deque[TtsItem] = deque()
        self.current: TtsItem | None = None
        self._event = asyncio.Event()
        self._task: asyncio.Task | None = None

    def enqueue(self, item: TtsItem) -> str | None:
        all_items = list(self.items) + ([self.current] if self.current else [])
        config = guild_config.tts_bridge(self.guild.id)
        if len(all_items) >= int(config["maxPendingPerGuild"]):
            return "guild_queue_full"
        if sum(entry.user_id == item.user_id for entry in all_items) >= int(config["maxPendingPerUser"]):
            return "user_queue_full"
        self.items.append(item)
        self._event.set()
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._worker())
        return None

    async def _worker(self) -> None:
        while True:
            while not self.items:
                self._event.clear()
                try:
                    await asyncio.wait_for(self._event.wait(), timeout=300)
                except asyncio.TimeoutError:
                    return
            self.current = self.items.popleft()
            path: Path | None = None
            try:
                config = guild_config.tts_bridge(self.guild.id)
                path = await self.service.generate_speech(
                    self.current.text,
                    language=config["language"],
                    voice=config["voice"],
                )
                source = discord.FFmpegPCMAudio(str(path))
                await self.coordinator.play_speech(source, pause_music=config["pauseMusicWhileSpeaking"])
                logger.info("tts played guild=%s user=%s message=%s length=%s result=success", self.guild.id, self.current.user_id, self.current.message_id, len(self.current.text))
            except (TtsProviderError, RuntimeError) as exc:
                logger.warning("tts failed guild=%s user=%s message=%s length=%s error=%s", self.guild.id, self.current.user_id, self.current.message_id, len(self.current.text), type(exc).__name__)
            finally:
                self.service.cleanup(path)
                self.current = None

    def skip(self) -> bool:
        if not self.current:
            return False
        self.coordinator.stop_speech()
        return True

    def clear(self, *, stop_current: bool = False) -> int:
        count = len(self.items)
        self.items.clear()
        if stop_current:
            self.coordinator.stop_speech()
        return count

    async def close(self) -> None:
        self.clear(stop_current=True)
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
