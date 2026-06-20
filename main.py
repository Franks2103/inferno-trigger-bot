import asyncio

import discord
from discord.ext import commands

from config import TOKEN

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready() -> None:
    await bot.tree.sync()
    print(f"🔥 Devil Trigger online como {bot.user}")


async def main() -> None:
    async with bot:
        await bot.load_extension("cogs.music")
        await bot.load_extension("cogs.config_cog")
        await bot.load_extension("cogs.favorites_cog")
        await bot.start(TOKEN)


asyncio.run(main())
