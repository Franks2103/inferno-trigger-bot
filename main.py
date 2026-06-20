import asyncio
import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

import discord
from discord.ext import commands

from config import TOKEN


def configure_logging() -> None:
    """Log operational events to terminal and a bounded local file."""
    level = getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO)
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    file_handler = RotatingFileHandler(log_dir / "bot.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logging.basicConfig(level=level, handlers=[console, file_handler], force=True)
    logging.getLogger("discord").setLevel(logging.INFO)
    logging.getLogger(__name__).info("Logger iniciado level=%s file=%s", logging.getLevelName(level), log_dir / "bot.log")

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready() -> None:
    await bot.tree.sync()
    logging.getLogger(__name__).info("Bot listo user=%s guilds=%s", bot.user, len(bot.guilds))


async def main() -> None:
    configure_logging()
    logger = logging.getLogger(__name__)
    async with bot:
        logger.info("Cargando extensiones")
        await bot.load_extension("cogs.music")
        await bot.load_extension("cogs.config_cog")
        await bot.load_extension("cogs.favorites_cog")
        await bot.load_extension("cogs.stats_cog")
        await bot.load_extension("cogs.tts_bridge_cog")
        logger.info("Extensiones cargadas; iniciando conexión Discord")
        await bot.start(TOKEN)


asyncio.run(main())
