import discord


def error_embed(msg: str) -> discord.Embed:
    return discord.Embed(description=f"⚠️ {msg}", color=discord.Color.red())


def success_embed(msg: str) -> discord.Embed:
    return discord.Embed(description=f"✅ {msg}", color=discord.Color.green())


def info_embed(msg: str) -> discord.Embed:
    return discord.Embed(description=msg, color=discord.Color.blurple())


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
