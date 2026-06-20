import discord


def error_embed(msg: str) -> discord.Embed:
    return discord.Embed(description=f"⚠️ {msg}", color=discord.Color.red())


def success_embed(msg: str) -> discord.Embed:
    return discord.Embed(description=f"✅ {msg}", color=discord.Color.green())


def info_embed(msg: str) -> discord.Embed:
    return discord.Embed(description=msg, color=discord.Color.blurple())


def create_bandelion_embed(title: str, description: str | None = None) -> discord.Embed:
    embed = discord.Embed(title=title, description=description, color=discord.Color.blurple())
    embed.set_footer(text="Powered by Bandelion")
    return embed


def create_tts_bridge_error_embed(message: str) -> discord.Embed:
    embed = create_bandelion_embed("⚠️ Bandelion TTS Bridge", message)
    embed.color = discord.Color.red()
    return embed


def create_tts_bridge_settings_embed(config: dict, *, text_channel: str, voice_channel: str, provider: dict) -> discord.Embed:
    embed = create_bandelion_embed("🔊 Bandelion TTS Bridge — Configuración")
    embed.add_field(name="Estado", value="✅ Activado" if config["enabled"] else "⛔ Desactivado", inline=True)
    embed.add_field(name="Canal de texto", value=text_channel, inline=True)
    embed.add_field(name="Canal de voz", value=voice_channel, inline=True)
    embed.add_field(name="Idioma / voz", value=f"`{config['language']}` / `{config['voice']}`", inline=True)
    embed.add_field(name="Máximo / cooldown", value=f"`{config['maxChars']}` chars / `{config['cooldownSeconds']}s`", inline=True)
    embed.add_field(name="Leer usuario", value="Sí" if config["readUsername"] else "No", inline=True)
    embed.add_field(name="Pausar música", value="Sí" if config["pauseMusicWhileSpeaking"] else "No", inline=True)
    status = "✅ OK" if provider["available"] else "❌ Missing"
    embed.add_field(name=f"Provider: {provider['provider']}", value=f"{status}\n{provider['message']}", inline=False)
    return embed


def create_tts_bridge_queue_embed(current, pending: list) -> discord.Embed:
    embed = create_bandelion_embed("📢 Bandelion TTS Bridge — Cola")
    if current:
        embed.add_field(name="Ahora", value=f"{current.display_name} · `{len(current.text)}` caracteres", inline=False)
    if pending:
        lines = [f"`{index}.` {item.display_name} · `{len(item.text)}` caracteres" for index, item in enumerate(pending[:10], 1)]
        embed.add_field(name="Próximos", value="\n".join(lines), inline=False)
    if not current and not pending:
        embed.description = "La cola está vacía."
    elif len(pending) > 10:
        embed.set_footer(text=f"Powered by Bandelion · y {len(pending) - 10} más")
    return embed


async def safe_reply(
    interaction: discord.Interaction,
    content: str | None = None,
    *,
    embed: discord.Embed | None = None,
    ephemeral: bool = False,
    view: discord.ui.View | None = None,
) -> None:
    """Send reply regardless of whether the interaction was deferred or not."""
    kwargs: dict = {}
    if content:
        kwargs["content"] = content
    if embed:
        kwargs["embed"] = embed
    if view:
        kwargs["view"] = view
    kwargs["ephemeral"] = ephemeral

    if interaction.response.is_done():
        await interaction.followup.send(**kwargs)
    else:
        await interaction.response.send_message(**kwargs)
