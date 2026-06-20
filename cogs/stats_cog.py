# cogs/stats_cog.py
import discord
from discord import app_commands
from discord.ext import commands

from services import stats as stats_store


class StatsCog(commands.Cog, name="Stats"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="stats", description="Muestra estadísticas de reproducción")
    @app_commands.choices(scope=[
        app_commands.Choice(name="Servidor", value="server"),
        app_commands.Choice(name="Mi perfil", value="me"),
    ])
    async def stats(self, interaction: discord.Interaction, scope: str = "server") -> None:
        if scope == "me":
            plays = stats_store.user_plays(interaction.guild_id, interaction.user.id)
            embed = discord.Embed(
                title=f"📊 Estadísticas de {interaction.user.display_name}",
                color=discord.Color.green(),
            )
            embed.add_field(name="Canciones pedidas", value=f"`{plays}`", inline=True)
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            g = stats_store.guild_stats(interaction.guild_id)
            embed = discord.Embed(
                title=f"📊 Estadísticas de {interaction.guild.name}",
                color=discord.Color.blue(),
            )
            embed.add_field(name="Total reproducidas", value=f"`{g.get('total', 0)}`", inline=True)
            embed.add_field(name="Canciones únicas", value=f"`{len(g.get('songs', {}))}`", inline=True)
            embed.add_field(name="Usuarios únicos", value=f"`{len(g.get('users', {}))}`", inline=True)
            await interaction.response.send_message(embed=embed)

    @app_commands.command(name="top", description="Muestra el top de canciones o usuarios")
    @app_commands.choices(category=[
        app_commands.Choice(name="Canciones más pedidas", value="songs"),
        app_commands.Choice(name="Usuarios más activos", value="users"),
    ])
    async def top(self, interaction: discord.Interaction, category: str = "songs") -> None:
        if category == "songs":
            songs = stats_store.top_songs(interaction.guild_id, 10)
            embed = discord.Embed(title="🎵 Top 10 canciones", color=discord.Color.purple())
            if not songs:
                embed.description = "Todavía no hay datos."
            else:
                lines = [f"`{i}.` **{s['title']}** — `{s['count']}` plays"
                         for i, s in enumerate(songs, 1)]
                embed.description = "\n".join(lines)
            await interaction.response.send_message(embed=embed)
        else:
            users = stats_store.top_users(interaction.guild_id, 10)
            embed = discord.Embed(title="👑 Top 10 usuarios", color=discord.Color.gold())
            if not users:
                embed.description = "Todavía no hay datos."
            else:
                lines = [f"`{i}.` <@{uid}> — `{count}` canciones"
                         for i, (uid, count) in enumerate(users, 1)]
                embed.description = "\n".join(lines)
            await interaction.response.send_message(embed=embed)

    async def cog_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        from ui.embeds import error_embed, safe_reply
        await safe_reply(interaction, embed=error_embed(str(error)), ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(StatsCog(bot))
