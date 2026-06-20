import discord
from discord import app_commands
from discord.ext import commands

from services import guild_config


class ConfigCog(commands.Cog, name="Config"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _is_admin(self, interaction: discord.Interaction) -> bool:
        return interaction.user.guild_permissions.administrator

    @app_commands.command(name="config-dj-role", description="Establece el rol DJ del servidor")
    async def set_dj_role(self, interaction: discord.Interaction, role: discord.Role) -> None:
        if not self._is_admin(interaction):
            return await interaction.response.send_message("Solo administradores.", ephemeral=True)
        guild_config.set_value(interaction.guild_id, dj_role=role.id)
        await interaction.response.send_message(f"✅ Rol DJ establecido: {role.mention}")

    @app_commands.command(name="config-music-channel", description="Canal exclusivo para comandos de música")
    async def set_music_channel(
        self, interaction: discord.Interaction, channel: discord.TextChannel
    ) -> None:
        if not self._is_admin(interaction):
            return await interaction.response.send_message("Solo administradores.", ephemeral=True)
        guild_config.set_value(interaction.guild_id, music_channel=channel.id)
        await interaction.response.send_message(f"✅ Canal de música: {channel.mention}")

    @app_commands.command(name="config-volume", description="Volumen predeterminado (0-100)")
    async def set_default_volume(self, interaction: discord.Interaction, value: int) -> None:
        if not self._is_admin(interaction):
            return await interaction.response.send_message("Solo administradores.", ephemeral=True)
        if not 0 <= value <= 100:
            return await interaction.response.send_message("Valor entre 0 y 100.", ephemeral=True)
        guild_config.set_value(interaction.guild_id, default_volume=value / 100)
        await interaction.response.send_message(f"✅ Volumen predeterminado: **{value}%**")

    @app_commands.command(name="config-max-queue", description="Máximo de canciones en cola")
    async def set_max_queue(self, interaction: discord.Interaction, value: int) -> None:
        if not self._is_admin(interaction):
            return await interaction.response.send_message("Solo administradores.", ephemeral=True)
        if value < 1:
            return await interaction.response.send_message("Mínimo 1.", ephemeral=True)
        guild_config.set_value(interaction.guild_id, max_queue=value)
        await interaction.response.send_message(f"✅ Máximo de cola: **{value}** canciones")

    @app_commands.command(name="config-show", description="Muestra la configuración actual")
    async def show_config(self, interaction: discord.Interaction) -> None:
        cfg = guild_config.get(interaction.guild_id)
        guild = interaction.guild

        dj_role_id = cfg.get("dj_role")
        dj_role = guild.get_role(dj_role_id).mention if dj_role_id else "No configurado"

        ch_id = cfg.get("music_channel")
        channel = guild.get_channel(ch_id).mention if ch_id else "Cualquier canal"

        vol = int(cfg.get("default_volume", 0.5) * 100)
        max_q = cfg.get("max_queue", 100)

        embed = discord.Embed(title="⚙️ Configuración del servidor", color=discord.Color.blurple())
        embed.add_field(name="DJ Role", value=dj_role, inline=True)
        embed.add_field(name="Canal de música", value=channel, inline=True)
        embed.add_field(name="Volumen por defecto", value=f"`{vol}%`", inline=True)
        embed.add_field(name="Máximo en cola", value=f"`{max_q}`", inline=True)
        await interaction.response.send_message(embed=embed)

    async def cog_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        msg = str(error)
        if interaction.response.is_done():
            await interaction.followup.send(f"⚠️ {msg}", ephemeral=True)
        else:
            await interaction.response.send_message(f"⚠️ {msg}", ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ConfigCog(bot))
