import time
import logging

import discord
from discord import app_commands
from discord.ext import commands

from config import TTS_BRIDGE_ENABLED
from services import guild_config
from services import permissions as perms
from services.tts_bridge_queue import TtsBridgeQueue, TtsItem
from services.tts_service import TtsService, TtsValidationError
from ui.embeds import (
    create_tts_bridge_error_embed,
    create_tts_bridge_queue_embed,
    create_tts_bridge_settings_embed,
    safe_reply,
)

logger = logging.getLogger(__name__)


class TtsBridgeCog(commands.Cog, name="TtsBridge"):
    tts_group = app_commands.Group(name="ttsbridge", description="Gestiona Bandelion TTS Bridge")

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.tts_service = TtsService()
        self.queues: dict[int, TtsBridgeQueue] = {}
        self._cooldowns: dict[tuple[int, int], float] = {}

    def _music_cog(self):
        music_cog = self.bot.get_cog("Music")
        if music_cog is None:
            raise RuntimeError("MusicCog no está cargado.")
        return music_cog

    def _queue_for(self, guild: discord.Guild) -> TtsBridgeQueue:
        if guild.id not in self.queues:
            music = self._music_cog().get_or_create_service_for_guild(guild)
            self.queues[guild.id] = TtsBridgeQueue(self.bot, guild, music.audio, self.tts_service)
        return self.queues[guild.id]

    async def clear_guild(self, guild_id: int, *, stop_current: bool) -> None:
        queue = self.queues.get(guild_id)
        if queue:
            queue.clear(stop_current=stop_current)

    @staticmethod
    def _channel_label(guild: discord.Guild, channel_id: int | None, fallback: str) -> str:
        channel = guild.get_channel(channel_id) if channel_id else None
        return channel.mention if channel else fallback

    async def _ensure_voice_target(self, guild: discord.Guild, author_channel, config: dict) -> str | None:
        target = author_channel
        if not isinstance(target, (discord.VoiceChannel, discord.StageChannel)):
            return "author_not_in_voice"

        me = guild.me
        permissions = target.permissions_for(me)
        if not (permissions.view_channel and permissions.connect and permissions.speak):
            return "missing_voice_permissions"

        voice_client = guild.voice_client
        if voice_client is None:
            if not config["autoJoinUserVoiceChannel"]:
                return "auto_join_disabled"
            await target.connect()
            return None
        if voice_client.channel != target:
            music = self._music_cog().get_service_for_guild(guild.id)
            queue = self.queues.get(guild.id)
            if not config["autoMoveBetweenVoiceChannels"]:
                return "bot_in_other_channel"
            if music and music.current or queue and queue.current:
                return "music_in_other_channel"
            await voice_client.move_to(target)
        return None

    def _replace_mentions(self, message: discord.Message) -> str:
        # clean_content resolves Discord mention syntax to readable names and
        # avoids speaking raw snowflake IDs.
        return message.clean_content

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if not TTS_BRIDGE_ENABLED or message.guild is None:
            return
        if self.bot.user and message.author.id == self.bot.user.id:
            return
        config = guild_config.tts_bridge(message.guild.id)
        if not config["enabled"] or message.channel.id != config["textChannelId"]:
            return
        if message.is_system():
            return
        if config["ignoreBots"] and message.author.bot:
            return
        raw = message.content.strip()
        if not raw:
            return
        if config["ignoreCommands"] and raw.startswith(("/", "!", ".")):
            return

        try:
            self.tts_service.validate_text(raw, config)
            text = self.tts_service.sanitize_text(self._replace_mentions(message), config)
        except TtsValidationError as exc:
            logger.info("tts ignored guild=%s user=%s message=%s length=%s reason=%s", message.guild.id, message.author.id, message.id, len(raw), exc)
            return

        key = (message.guild.id, message.author.id)
        now = time.monotonic()
        if len(self._cooldowns) > 1000:
            self._cooldowns = {
                cooldown_key: timestamp
                for cooldown_key, timestamp in self._cooldowns.items()
                if now - timestamp < 3600
            }
        if now - self._cooldowns.get(key, 0) < config["cooldownSeconds"]:
            logger.info("tts ignored guild=%s user=%s message=%s length=%s reason=cooldown", message.guild.id, message.author.id, message.id, len(text))
            return

        author_channel = getattr(getattr(message.author, "voice", None), "channel", None)
        if config["requireUserInVoice"] and author_channel is None:
            logger.info("tts ignored guild=%s user=%s message=%s length=%s reason=author_not_in_voice", message.guild.id, message.author.id, message.id, len(text))
            return
        voice_error = await self._ensure_voice_target(message.guild, author_channel, config)
        if voice_error:
            logger.info("tts ignored guild=%s user=%s message=%s length=%s reason=%s", message.guild.id, message.author.id, message.id, len(text), voice_error)
            return

        display_name = message.author.display_name
        final_text = text
        if config["readUsername"]:
            final_text = f"{config['usernameTemplate'].format(username=display_name)}: {text}"
        reason = self._queue_for(message.guild).enqueue(
            TtsItem(message.author.id, display_name, final_text, message.id)
        )
        if reason:
            logger.info("tts ignored guild=%s user=%s message=%s length=%s reason=%s", message.guild.id, message.author.id, message.id, len(text), reason)
            return
        self._cooldowns[key] = now
        logger.info("tts queued guild=%s user=%s message=%s length=%s target_voice=%s", message.guild.id, message.author.id, message.id, len(text), author_channel.id)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after) -> None:
        if self.bot.user and member.id == self.bot.user.id and before.channel and after.channel is None:
            await self.clear_guild(member.guild.id, stop_current=True)

    def _check_manager(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            raise app_commands.AppCommandError("Este comando solo funciona en un servidor.")
        perms.check_tts_manager(interaction)

    @tts_group.command(name="setup", description="Configura el canal de texto y voz de TTS Bridge")
    async def setup(
        self,
        interaction: discord.Interaction,
        text_channel: discord.TextChannel | discord.VoiceChannel,
    ) -> None:
        self._check_manager(interaction)
        guild_config.set_tts_bridge(interaction.guild_id, textChannelId=text_channel.id)
        await interaction.response.send_message(f"✅ Bandelion TTS Bridge configurado en {text_channel.mention}. Leerá en el canal de voz de cada autor.", ephemeral=True)

    @tts_group.command(name="enable", description="Activa Bandelion TTS Bridge")
    async def enable(self, interaction: discord.Interaction) -> None:
        self._check_manager(interaction)
        config = guild_config.tts_bridge(interaction.guild_id)
        if not config["textChannelId"]:
            raise app_commands.AppCommandError("Primero usá /ttsbridge setup con un canal de texto.")
        guild_config.set_tts_bridge(interaction.guild_id, enabled=True)
        await interaction.response.send_message("✅ Bandelion TTS Bridge activado.", ephemeral=True)

    @tts_group.command(name="disable", description="Desactiva Bandelion TTS Bridge")
    async def disable(self, interaction: discord.Interaction) -> None:
        self._check_manager(interaction)
        guild_config.set_tts_bridge(interaction.guild_id, enabled=False)
        await self.clear_guild(interaction.guild_id, stop_current=True)
        await interaction.response.send_message("⛔ Bandelion TTS Bridge desactivado y cola limpiada.", ephemeral=True)

    @tts_group.command(name="settings", description="Muestra la configuración de TTS Bridge")
    async def settings(self, interaction: discord.Interaction) -> None:
        config = guild_config.tts_bridge(interaction.guild_id)
        embed = create_tts_bridge_settings_embed(
            config,
            text_channel=self._channel_label(interaction.guild, config["textChannelId"], "No configurado"),
            voice_channel="Dinámico: canal de voz del autor",
            provider=self.tts_service.get_provider_info(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @tts_group.command(name="channel", description="Cambia el canal de texto que se lee")
    async def channel(
        self,
        interaction: discord.Interaction,
        text_channel: discord.TextChannel | discord.VoiceChannel,
    ) -> None:
        self._check_manager(interaction)
        guild_config.set_tts_bridge(interaction.guild_id, textChannelId=text_channel.id)
        await interaction.response.send_message(f"✅ Canal TTS: {text_channel.mention}", ephemeral=True)

    @tts_group.command(name="language", description="Cambia el idioma/voz de espeak-ng")
    async def language(self, interaction: discord.Interaction, language: str) -> None:
        self._check_manager(interaction)
        guild_config.set_tts_bridge(interaction.guild_id, language=language.strip())
        await interaction.response.send_message(f"✅ Idioma TTS: `{language.strip()}`", ephemeral=True)

    @tts_group.command(name="max-chars", description="Configura el máximo de caracteres por mensaje")
    async def max_chars(self, interaction: discord.Interaction, number: app_commands.Range[int, 1, 1000]) -> None:
        self._check_manager(interaction)
        guild_config.set_tts_bridge(interaction.guild_id, maxChars=int(number))
        await interaction.response.send_message(f"✅ Máximo TTS: `{number}` caracteres", ephemeral=True)

    @tts_group.command(name="cooldown", description="Configura el cooldown TTS por usuario")
    async def cooldown(self, interaction: discord.Interaction, seconds: app_commands.Range[int, 0, 60]) -> None:
        self._check_manager(interaction)
        guild_config.set_tts_bridge(interaction.guild_id, cooldownSeconds=int(seconds))
        await interaction.response.send_message(f"✅ Cooldown TTS: `{seconds}s`", ephemeral=True)

    @tts_group.command(name="read-username", description="Activa o desactiva el nombre antes del mensaje")
    async def read_username(self, interaction: discord.Interaction, enabled: bool) -> None:
        self._check_manager(interaction)
        guild_config.set_tts_bridge(interaction.guild_id, readUsername=enabled)
        await interaction.response.send_message(f"✅ Leer usuario: {'sí' if enabled else 'no'}", ephemeral=True)

    @tts_group.command(name="pause-music", description="Pausa música mientras habla TTS")
    async def pause_music(self, interaction: discord.Interaction, enabled: bool) -> None:
        self._check_manager(interaction)
        guild_config.set_tts_bridge(interaction.guild_id, pauseMusicWhileSpeaking=enabled)
        await interaction.response.send_message(f"✅ Pausar música: {'sí' if enabled else 'no'}", ephemeral=True)

    @tts_group.command(name="join", description="Une el bot a tu canal de voz")
    async def join(self, interaction: discord.Interaction) -> None:
        config = guild_config.tts_bridge(interaction.guild_id)
        if not config["enabled"]:
            raise app_commands.AppCommandError("TTS Bridge está desactivado.")
        target = getattr(getattr(interaction.user, "voice", None), "channel", None)
        error = await self._ensure_voice_target(interaction.guild, target, config)
        if error:
            raise app_commands.AppCommandError("No puedo unirme a ese canal de voz ahora.")
        await interaction.response.send_message("✅ Conectado a tu canal de voz.", ephemeral=True)

    @tts_group.command(name="leave", description="Limpia TTS y sale si no hay música activa")
    async def leave(self, interaction: discord.Interaction) -> None:
        self._queue_for(interaction.guild).clear(stop_current=True)
        music = self._music_cog().get_service_for_guild(interaction.guild_id)
        if music and music.current:
            return await interaction.response.send_message("🧹 Cola TTS limpiada. La música sigue activa, por eso no desconecté el bot.", ephemeral=True)
        if music:
            await music.disconnect()
        await interaction.response.send_message("🛑 TTS Bridge desconectado y cola limpiada.", ephemeral=True)

    @tts_group.command(name="skip", description="Salta el TTS actual")
    async def skip(self, interaction: discord.Interaction) -> None:
        if self._queue_for(interaction.guild).skip():
            await interaction.response.send_message("⏭️ TTS saltado.", ephemeral=True)
        else:
            await interaction.response.send_message("No hay TTS reproduciéndose.", ephemeral=True)

    @tts_group.command(name="clear", description="Limpia la cola TTS pendiente")
    async def clear(self, interaction: discord.Interaction) -> None:
        count = self._queue_for(interaction.guild).clear()
        await interaction.response.send_message(f"🧹 Se eliminaron `{count}` mensajes TTS pendientes.", ephemeral=True)

    @tts_group.command(name="queue", description="Muestra la cola TTS")
    async def queue(self, interaction: discord.Interaction) -> None:
        queue = self._queue_for(interaction.guild)
        await interaction.response.send_message(embed=create_tts_bridge_queue_embed(queue.current, list(queue.items)), ephemeral=True)

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
        await safe_reply(interaction, embed=create_tts_bridge_error_embed(str(error)), ephemeral=True)

    def cog_unload(self) -> None:
        for queue in self.queues.values():
            self.bot.loop.create_task(queue.close())


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(TtsBridgeCog(bot))
