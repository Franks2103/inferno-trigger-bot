from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands

from services import ai_memory, mistral_api, mistral_dj, modlog, permissions
from services.extractor import search_tracks
from services.music_service import AudioFilter, LoopMode
from models.track import Track
from ui.embeds import error_embed

logger = logging.getLogger(__name__)
audit_logger = logging.getLogger("bandelion.ai.audit")
_FOOTER = "Powered by Bandelion"
_chatbot = app_commands.Group(name="chatbot", description="Activa respuestas automáticas para tus mensajes")

_TOOLS = [
    {"type": "function", "function": {"name": "play_music", "description": "Busca y agrega una canción o hasta cinco resultados a la cola. Úsala para poner, cambiar o añadir música.", "parameters": {"type": "object", "properties": {"query": {"type": "string"}, "count": {"type": "integer", "minimum": 1, "maximum": 5}}, "required": ["query"]}}},
    {"type": "function", "function": {"name": "music_control", "description": "Controla la reproducción: skip, pause, resume, stop (detiene música sin apagar el chatbot ni desconectar), shuffle, clear, queue o now.", "parameters": {"type": "object", "properties": {"action": {"type": "string", "enum": ["skip", "pause", "resume", "stop", "shuffle", "clear", "queue", "now"]}}, "required": ["action"]}}},
    {"type": "function", "function": {"name": "audio_settings", "description": "Ajusta loop, autoplay, volumen o filtro de audio. Usa solamente los campos necesarios.", "parameters": {"type": "object", "properties": {"loop": {"type": "string", "enum": ["off", "song", "queue"]}, "autoplay": {"type": "boolean"}, "volume": {"type": "integer", "minimum": 0, "maximum": 100}, "filter": {"type": "string", "enum": ["off", "bassboost", "nightcore", "vaporwave", "slowed", "karaoke"]}}}}},
    {"type": "function", "function": {"name": "set_dj", "description": "Activa o desactiva el DJ automático. Para activar puede recibir un mood musical.", "parameters": {"type": "object", "properties": {"enabled": {"type": "boolean"}, "mood": {"type": "string"}}, "required": ["enabled"]}}},
    {"type": "function", "function": {"name": "recommend_music", "description": "Propone hasta cinco canciones basadas en la canción actual o en un mood. No las agrega aún; el usuario debe aprobarlas o pedir cambios.", "parameters": {"type": "object", "properties": {"mood": {"type": "string"}}}}},
    {"type": "function", "function": {"name": "manage_recommendations", "description": "Gestiona las últimas recomendaciones del usuario: add para agregar todas o solo indexes (base 1), replace para otras, dismiss para descartarlas.", "parameters": {"type": "object", "properties": {"action": {"type": "string", "enum": ["add", "replace", "dismiss"]}, "indexes": {"type": "array", "items": {"type": "integer", "minimum": 1, "maximum": 5}}}, "required": ["action"]}}},
    {"type": "function", "function": {"name": "get_server_rules", "description": "Lee las reglas públicas del canal de reglas del servidor.", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "request_moderation", "description": "Solicita ban, kick o timeout. Solo úsala si el usuario mencionó explícitamente al objetivo; target_id debe ser su ID numérico. Nunca ejecuta directamente: exige confirmación posterior.", "parameters": {"type": "object", "properties": {"action": {"type": "string", "enum": ["ban", "kick", "timeout"]}, "target_id": {"type": "string"}, "reason": {"type": "string"}, "duration": {"type": "string"}}, "required": ["action", "target_id", "reason"]}}},
]


@dataclass
class PendingModeration:
    action: str
    target_id: int
    reason: str
    duration: str | None
    expires_at: datetime


@dataclass
class PendingRecommendations:
    tracks: list[Track]
    mood: str | None
    expires_at: datetime


@_chatbot.command(name="activar", description="Hace que Bandelion responda a todos tus mensajes")
async def chatbot_activar(interaction: discord.Interaction) -> None:
    if interaction.guild_id is None:
        return await interaction.response.send_message(
            embed=error_embed("Este comando solo funciona dentro de un servidor."), ephemeral=True
        )
    ai_memory.set_chatbot_enabled(interaction.guild_id, interaction.user.id, True)
    embed = discord.Embed(
        title="🤖 Chatbot activado",
        description="Responderé a tus mensajes en este servidor hasta que uses `/chatbot desactivar`.",
        color=discord.Color.green(),
    )
    embed.set_footer(text=_FOOTER)
    await interaction.response.send_message(embed=embed, ephemeral=True)


@_chatbot.command(name="desactivar", description="Detiene las respuestas automáticas para tus mensajes")
async def chatbot_desactivar(interaction: discord.Interaction) -> None:
    if interaction.guild_id is None:
        return await interaction.response.send_message(
            embed=error_embed("Este comando solo funciona dentro de un servidor."), ephemeral=True
        )
    ai_memory.set_chatbot_enabled(interaction.guild_id, interaction.user.id, False)
    embed = discord.Embed(
        title="⏹️ Chatbot desactivado",
        description="Ya no responderé automáticamente a tus mensajes en este servidor.",
        color=discord.Color.orange(),
    )
    embed.set_footer(text=_FOOTER)
    await interaction.response.send_message(embed=embed, ephemeral=True)


@_chatbot.command(name="estado", description="Muestra si el chatbot automático está activo")
async def chatbot_estado(interaction: discord.Interaction) -> None:
    if interaction.guild_id is None:
        return await interaction.response.send_message(
            embed=error_embed("Este comando solo funciona dentro de un servidor."), ephemeral=True
        )
    enabled = ai_memory.is_chatbot_enabled(interaction.guild_id, interaction.user.id)
    message = "✅ Activo: responderé a todos tus mensajes." if enabled else "⏹️ Desactivado. Usá `/chatbot activar`."
    await interaction.response.send_message(message, ephemeral=True)


class ChatbotCog(commands.Cog, name="Chatbot"):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._pending_moderation: dict[tuple[int, int], PendingModeration] = {}
        self._recommendations: dict[tuple[int, int], PendingRecommendations] = {}

    async def cog_load(self) -> None:
        # Conversation is mention-driven; no slash command is required.
        return None

    async def cog_unload(self) -> None:
        return None

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or message.guild is None or not message.content.strip() or self.bot.user is None:
            return
        if message.content.startswith("!"):
            return
        if self.bot.user.id not in message.raw_mentions:
            return

        user_message = (
            message.content.replace(f"<@{self.bot.user.id}>", "").replace(f"<@!{self.bot.user.id}>", "").strip()
        )
        if not user_message:
            return await message.reply("Decime qué necesitás.", mention_author=False)

        audit_logger.info(
            "chatbot.message accepted guild=%s channel=%s user=%s chars=%s",
            message.guild.id, message.channel.id, message.author.id, len(user_message),
        )

        if await self._handle_pending_moderation(message):
            return

        memory = ai_memory.get_user_memory(message.guild.id, message.author.id)
        audit_logger.info(
            "chatbot.memory loaded guild=%s user=%s preset=%s preference_count=%s custom_tone=%s",
            message.guild.id, message.author.id, memory.get("style_preset", "neutral"),
            len(memory.get("preferences", [])), bool(memory.get("custom_tone")),
        )
        system, user = ai_memory.build_ia_prompt(
            guild_context={"id": message.guild.id, "name": message.guild.name},
            user_memory=memory,
            recent_context=None,
            user_message=user_message,
        )
        system += (
            "\n\nHERRAMIENTAS: usá tools cuando el usuario quiera una acción. "
            "Nunca afirmes haber ejecutado una acción sin recibir su resultado. "
            "Las herramientas aplican permisos reales del servidor. "
            "Para moderación, solicitá confirmación; nunca la ejecutes directamente."
        )
        audit_logger.info(
            "chatbot.prompt built guild=%s user=%s system_chars=%s tool_count=%s",
            message.guild.id, message.author.id, len(system), len(_TOOLS),
        )
        async with message.channel.typing():
            result = await mistral_api.ask_with_tools(system, user, _TOOLS, lambda name, args: self._execute_tool(message, name, args))
        if not result:
            audit_logger.warning("chatbot.response skipped guild=%s user=%s reason=empty_model_result", message.guild.id, message.author.id)
            return
        try:
            await message.reply(
                result[:2000],
                mention_author=False,
                allowed_mentions=discord.AllowedMentions.none(),
            )
            audit_logger.info("chatbot.response sent guild=%s channel=%s user=%s chars=%s", message.guild.id, message.channel.id, message.author.id, len(result))
        except (discord.Forbidden, discord.HTTPException) as exc:
            logger.warning("Could not send chatbot reply guild=%s channel=%s: %s", message.guild.id, message.channel.id, exc)

    async def _execute_tool(self, message: discord.Message, name: str, args: dict) -> dict:
        audit_logger.info("chatbot.tool dispatch guild=%s user=%s name=%s argument_keys=%s", message.guild.id, message.author.id, name, ",".join(sorted(args.keys())))
        try:
            if name == "play_music":
                return await self._play_music(message, args)
            if name == "music_control":
                return await self._music_control(message, args)
            if name == "audio_settings":
                return await self._audio_settings(message, args)
            if name == "set_dj":
                return await self._set_dj(message, args)
            if name == "recommend_music":
                return await self._recommend_music(message, args)
            if name == "manage_recommendations":
                return await self._manage_recommendations(message, args)
            if name == "get_server_rules":
                return await self._get_server_rules(message)
            if name == "request_moderation":
                return self._request_moderation(message, args)
            return {"ok": False, "error": "Herramienta no permitida."}
        except Exception as exc:
            logger.warning("Chatbot tool failed name=%s guild=%s: %s", name, message.guild.id, exc)
            audit_logger.warning("chatbot.tool failed guild=%s user=%s name=%s error_type=%s", message.guild.id, message.author.id, name, type(exc).__name__)
            return {"ok": False, "error": str(exc)}

    def _music_cog(self):
        return self.bot.get_cog("Music")

    async def _ensure_voice(self, message: discord.Message) -> None:
        if not isinstance(message.author, discord.Member) or not message.author.voice or not message.author.voice.channel:
            raise ValueError("Tenés que estar en un canal de voz para usar música.")
        voice = message.guild.voice_client
        if voice is None:
            await message.author.voice.channel.connect()
        elif voice.channel != message.author.voice.channel:
            await voice.move_to(message.author.voice.channel)

    async def _play_music(self, message: discord.Message, args: dict) -> dict:
        permissions.check_member(message.guild.id, message.author, "play")
        music = self._music_cog()
        if music is None:
            raise ValueError("El módulo de música no está disponible.")
        query = str(args.get("query", "")).strip()
        if not query:
            raise ValueError("Falta la canción o artista.")
        count = min(max(int(args.get("count", 1)), 1), 5)
        await self._ensure_voice(message)
        service = music.get_or_create_service_for_guild(message.guild)
        service.text_channel = message.channel
        tracks = await search_tracks(query, message.author, limit=count)
        if not tracks:
            return {"ok": False, "error": "No encontré resultados."}
        for track in tracks:
            service.add(track)
        await music.refresh_player_ui(message.guild.id)
        return {"ok": True, "queued": [track.title for track in tracks], "ui": "El panel de reproducción aparecerá al iniciar la canción."}

    async def _music_control(self, message: discord.Message, args: dict) -> dict:
        action = args.get("action")
        music = self._music_cog()
        service = music.get_service_for_guild(message.guild.id) if music else None
        if action in {"skip", "clear", "stop"}:
            permissions.check_member(message.guild.id, message.author, action)
        if not service:
            return {"ok": False, "error": "No hay una sesión de música activa."}
        voice = message.guild.voice_client
        if action == "skip":
            if not service.current:
                return {"ok": False, "error": "No hay canción sonando."}
            service.stop_current()
        elif action == "pause":
            if not voice or not voice.is_playing(): return {"ok": False, "error": "No hay música sonando."}
            voice.pause()
        elif action == "resume":
            if not voice or not voice.is_paused(): return {"ok": False, "error": "No hay música pausada."}
            voice.resume()
        elif action == "shuffle":
            service.shuffle()
        elif action == "clear":
            service.queue.clear()
        elif action == "stop":
            service.queue.clear()
            service.autoplay = False
            if service.current:
                service.stop_current()
        elif action == "queue":
            return {"ok": True, "current": service.current.title if service.current else None, "queue": [t.title for t in list(service.queue)[:10]]}
        elif action == "now":
            return {"ok": True, "current": service.current.title if service.current else "Nada sonando"}
        else:
            return {"ok": False, "error": "Control no válido."}
        await music.refresh_player_ui(message.guild.id)
        return {"ok": True, "action": action}

    async def _recommend_music(self, message: discord.Message, args: dict) -> dict:
        music = self._music_cog()
        service = music.get_service_for_guild(message.guild.id) if music else None
        mood = str(args.get("mood", "")).strip() or None
        if service and service.current and not mood:
            mood = f"similar a {service.current.title}"
        suggestions, _ = await mistral_dj.get_recommendations(message.guild.id, mood=mood, count=5)
        tracks: list[Track] = []
        for suggestion in suggestions:
            found = await search_tracks(suggestion, message.author, limit=1)
            if found:
                tracks.append(found[0])
        if not tracks:
            return {"ok": False, "error": "No pude encontrar recomendaciones ahora."}
        self._recommendations[(message.guild.id, message.author.id)] = PendingRecommendations(
            tracks=tracks, mood=mood, expires_at=datetime.now(timezone.utc) + timedelta(minutes=10)
        )
        return {"ok": True, "recommendations": [track.title for track in tracks], "instruction": "Preguntá si agrega todas, cuáles números agrega, o si quiere otras."}

    async def _manage_recommendations(self, message: discord.Message, args: dict) -> dict:
        key = (message.guild.id, message.author.id)
        pending = self._recommendations.get(key)
        if pending is None or pending.expires_at < datetime.now(timezone.utc):
            self._recommendations.pop(key, None)
            return {"ok": False, "error": "No hay recomendaciones pendientes. Pedí nuevas recomendaciones."}
        action = args.get("action")
        if action == "dismiss":
            self._recommendations.pop(key, None)
            return {"ok": True, "dismissed": True}
        if action == "replace":
            self._recommendations.pop(key, None)
            return await self._recommend_music(message, {"mood": pending.mood or ""})
        if action != "add":
            return {"ok": False, "error": "Acción de recomendaciones inválida."}
        music = self._music_cog()
        if music is None:
            return {"ok": False, "error": "El módulo de música no está disponible."}
        await self._ensure_voice(message)
        selected = args.get("indexes") or list(range(1, len(pending.tracks) + 1))
        tracks = [pending.tracks[i - 1] for i in selected if isinstance(i, int) and 1 <= i <= len(pending.tracks)]
        if not tracks:
            return {"ok": False, "error": "No seleccionaste recomendaciones válidas."}
        service = music.get_or_create_service_for_guild(message.guild)
        service.text_channel = message.channel
        for track in tracks:
            service.add(track)
        self._recommendations.pop(key, None)
        await music.refresh_player_ui(message.guild.id)
        return {"ok": True, "queued": [track.title for track in tracks]}

    async def _audio_settings(self, message: discord.Message, args: dict) -> dict:
        music = self._music_cog()
        service = music.get_service_for_guild(message.guild.id) if music else None
        if service is None:
            return {"ok": False, "error": "No hay una sesión de música activa."}
        changed: dict[str, object] = {}
        if "loop" in args:
            permissions.check_member(message.guild.id, message.author, "loop")
            service.loop_mode = LoopMode(args["loop"])
            changed["loop"] = args["loop"]
        if "autoplay" in args:
            permissions.check_member(message.guild.id, message.author, "autoplay")
            service.autoplay = bool(args["autoplay"])
            changed["autoplay"] = service.autoplay
        if "volume" in args:
            permissions.check_member(message.guild.id, message.author, "volume")
            volume = max(0, min(int(args["volume"]), 100))
            service.set_volume(volume / 100)
            changed["volume"] = volume
        if "filter" in args:
            permissions.check_member(message.guild.id, message.author, "filter")
            service.audio_filter = AudioFilter(args["filter"])
            changed["filter"] = args["filter"]
            if service.current:
                service.seek(service.elapsed_seconds)
                service.stop_current()
        if not changed:
            return {"ok": False, "error": "No indicaron ningún ajuste de audio."}
        await music.refresh_player_ui(message.guild.id)
        return {"ok": True, "changed": changed}

    async def _set_dj(self, message: discord.Message, args: dict) -> dict:
        enabled = bool(args.get("enabled"))
        permissions.check_member(message.guild.id, message.author, "dj-start" if enabled else "dj-stop")
        music = self._music_cog()
        if music is None: raise ValueError("El módulo de música no está disponible.")
        service = music.get_or_create_service_for_guild(message.guild)
        if not enabled:
            service.dj_mode, service.dj_mood = False, None
            return {"ok": True, "dj": "desactivado"}
        await self._ensure_voice(message)
        mood = str(args.get("mood", "")).strip() or None
        service.dj_mode, service.dj_mood, service.text_channel = True, mood, message.channel
        suggestions, _ = await mistral_dj.get_recommendations(message.guild.id, mood=mood, count=5)
        queued = []
        for suggestion in suggestions:
            tracks = await search_tracks(suggestion, message.author, limit=1)
            if tracks:
                service.add(tracks[0]); queued.append(tracks[0].title)
        if not queued:
            service.dj_mode = False
            return {"ok": False, "error": "No pude generar canciones para el DJ."}
        return {"ok": True, "dj": "activado", "queued": queued}

    async def _get_server_rules(self, message: discord.Message) -> dict:
        channel = message.guild.rules_channel
        if channel is None:
            return {"ok": False, "error": "Este servidor no tiene un canal de reglas configurado."}
        rules = [m.content[:500] async for m in channel.history(limit=15, oldest_first=True) if m.content and not m.author.bot]
        return {"ok": True, "channel": channel.mention, "rules": rules}

    def _request_moderation(self, message: discord.Message, args: dict) -> dict:
        action = str(args.get("action", ""))
        try: target_id = int(args.get("target_id"))
        except (TypeError, ValueError): return {"ok": False, "error": "Necesito una mención válida del usuario."}
        permissions.check_member(message.guild.id, message.author, action)
        target = message.guild.get_member(target_id)
        if target is None or target.bot:
            return {"ok": False, "error": "No encontré un miembro válido para moderar."}
        if target_id not in message.raw_mentions:
            return {"ok": False, "error": "Por seguridad, mencioná explícitamente al usuario objetivo."}
        self._pending_moderation[(message.guild.id, message.author.id)] = PendingModeration(action, target_id, str(args.get("reason", "Sin razón"))[:300], args.get("duration"), datetime.now(timezone.utc) + timedelta(minutes=2))
        audit_logger.warning("chatbot.moderation pending guild=%s moderator=%s action=%s target=%s", message.guild.id, message.author.id, action, target_id)
        return {"ok": True, "pending_confirmation": True, "action": action, "target": target.display_name, "instruction": "Pedí al usuario que escriba CONFIRMO en los próximos 2 minutos."}

    async def _handle_pending_moderation(self, message: discord.Message) -> bool:
        key = (message.guild.id, message.author.id)
        pending = self._pending_moderation.get(key)
        if not pending: return False
        if pending.expires_at < datetime.now(timezone.utc):
            self._pending_moderation.pop(key, None)
            audit_logger.info("chatbot.moderation expired guild=%s moderator=%s", message.guild.id, message.author.id)
            return False
        text = message.content.strip().lower()
        if text in {"cancelar", "cancela", "no"}:
            self._pending_moderation.pop(key, None)
            audit_logger.info("chatbot.moderation cancelled guild=%s moderator=%s", message.guild.id, message.author.id)
            await message.reply("Acción de moderación cancelada.", mention_author=False); return True
        if text not in {"confirmo", "confirmar", "sí confirmo", "si confirmo"}: return False
        self._pending_moderation.pop(key, None)
        audit_logger.warning("chatbot.moderation confirmed guild=%s moderator=%s action=%s target=%s", message.guild.id, message.author.id, pending.action, pending.target_id)
        target = message.guild.get_member(pending.target_id)
        if target is None: await message.reply("El usuario ya no está disponible.", mention_author=False); return True
        try:
            if pending.action == "ban": await message.guild.ban(target, reason=pending.reason)
            elif pending.action == "kick": await target.kick(reason=pending.reason)
            else:
                delta = modlog.parse_duration(pending.duration or "")
                if delta is None: raise ValueError("La duración debe ser como `10m`, `1h` o `7d`.")
                await target.timeout(datetime.now(timezone.utc) + delta, reason=pending.reason)
            modlog.add_entry(message.guild.id, type=pending.action, target_id=target.id, target_name=str(target), moderator_id=message.author.id, moderator_name=str(message.author), reason=pending.reason)
            await message.reply(f"✅ {pending.action.capitalize()} ejecutado para {target.mention}. Razón: {pending.reason}", mention_author=False)
            audit_logger.warning("chatbot.moderation executed guild=%s moderator=%s action=%s target=%s", message.guild.id, message.author.id, pending.action, target.id)
        except (discord.Forbidden, discord.HTTPException, ValueError) as exc:
            audit_logger.warning("chatbot.moderation failed guild=%s moderator=%s action=%s error_type=%s", message.guild.id, message.author.id, pending.action, type(exc).__name__)
            await message.reply(f"No pude ejecutar la moderación: {exc}", mention_author=False)
        return True


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ChatbotCog(bot))
