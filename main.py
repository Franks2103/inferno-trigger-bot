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
    ai_audit_level = getattr(logging, os.getenv("AI_AUDIT_LOG_LEVEL", "INFO").upper(), logging.INFO)
    logging.getLogger("bandelion.ai.audit").setLevel(ai_audit_level)
    logging.getLogger(__name__).info("Logger iniciado level=%s file=%s", logging.getLevelName(level), log_dir / "bot.log")
    logging.getLogger("bandelion.ai.audit").info("ia.audit logger_started level=%s", logging.getLevelName(ai_audit_level))

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
intents.members = True  # needed for role.members count and member lookups

bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_command_error(ctx: commands.Context, error: commands.CommandError) -> None:
    """Slash commands are primary; ignore legacy !command attempts cleanly."""
    if isinstance(error, commands.CommandNotFound):
        return
    raise error


_DEV_GUILD_ID = os.getenv("DEV_GUILD_ID")
_DEV_GUILD = discord.Object(id=int(_DEV_GUILD_ID)) if _DEV_GUILD_ID else None

@bot.event
async def on_ready() -> None:
    if _DEV_GUILD:
        bot.tree.copy_global_to(guild=_DEV_GUILD)
        await bot.tree.sync(guild=_DEV_GUILD)
    else:
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
        await bot.load_extension("cogs.admin_cog")
        await bot.load_extension("cogs.dj_cog")
        await bot.load_extension("cogs.ai_cog")
        await bot.load_extension("cogs.chatbot_cog")
        logger.info("Extensiones cargadas; iniciando conexión Discord")
        await bot.start(TOKEN)


asyncio.run(main())
