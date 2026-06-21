# services/permissions.py
from enum import Enum, auto

import discord
from discord import app_commands

from services import guild_config


class PermLevel(Enum):
    EVERYONE = auto()
    DJ = auto()
    ADMIN = auto()


# Maps action name → minimum required permission level
ACTION_PERMS: dict[str, PermLevel] = {
    "play": PermLevel.EVERYONE,
    "queue": PermLevel.EVERYONE,
    "now": PermLevel.EVERYONE,
    "voteskip": PermLevel.EVERYONE,
    "fav-add": PermLevel.EVERYONE,
    "fav-list": PermLevel.EVERYONE,
    "fav-play": PermLevel.EVERYONE,
    "fav-remove": PermLevel.EVERYONE,
    "shuffle": PermLevel.EVERYONE,
    "remove": PermLevel.EVERYONE,
    "move": PermLevel.EVERYONE,
    "history": PermLevel.EVERYONE,
    "pause": PermLevel.EVERYONE,
    "resume": PermLevel.EVERYONE,
    "seek": PermLevel.DJ,
    "replay": PermLevel.DJ,
    "skip": PermLevel.DJ,
    "previous": PermLevel.DJ,
    "loop": PermLevel.DJ,
    "autoplay": PermLevel.DJ,
    "volume": PermLevel.DJ,
    "clear": PermLevel.DJ,
    "join": PermLevel.DJ,
    "leave": PermLevel.DJ,
    "filter": PermLevel.DJ,
    "musicpanel": PermLevel.ADMIN,
    "config-dj-role": PermLevel.ADMIN,
    "config-music-channel": PermLevel.ADMIN,
    "config-volume": PermLevel.ADMIN,
    "config-max-queue": PermLevel.ADMIN,
    "config-show": PermLevel.EVERYONE,
    "stats": PermLevel.EVERYONE,
    "top": PermLevel.EVERYONE,
    # Admin moderation
    "ban": PermLevel.ADMIN,
    "unban": PermLevel.ADMIN,
    "kick": PermLevel.ADMIN,
    "timeout": PermLevel.ADMIN,
    "warn": PermLevel.ADMIN,
    "warns": PermLevel.EVERYONE,
    "unwarn": PermLevel.ADMIN,
    # Admin roles
    "role-give": PermLevel.ADMIN,
    "role-remove": PermLevel.ADMIN,
    "role-info": PermLevel.EVERYONE,
    # Admin channels
    "channel-lock": PermLevel.ADMIN,
    "channel-unlock": PermLevel.ADMIN,
    "channel-slowmode": PermLevel.ADMIN,
    # Admin panel
    "adminpanel": PermLevel.ADMIN,
    # DJ mode
    "dj-start": PermLevel.DJ,
    "dj-stop": PermLevel.DJ,
    "dj-status": PermLevel.EVERYONE,
    # AI
    "summary": PermLevel.EVERYONE,
    "ai": PermLevel.EVERYONE,
}


def check(interaction: discord.Interaction, action: str) -> None:
    """Raise AppCommandError if the user lacks permission for `action`."""
    required = ACTION_PERMS.get(action, PermLevel.DJ)

    if required == PermLevel.EVERYONE:
        return

    member = interaction.user
    if member.guild_permissions.administrator:
        return

    if required == PermLevel.ADMIN:
        raise app_commands.AppCommandError("Solo los administradores pueden usar este comando.")

    # DJ level
    dj_id = guild_config.dj_role_id(interaction.guild_id)
    if dj_id is None:
        return  # No DJ role configured → everyone can use DJ commands
    role_ids = {r.id for r in member.roles}
    if dj_id not in role_ids:
        raise app_commands.AppCommandError("Necesitás el rol DJ para usar este comando.")


def check_tts_manager(interaction: discord.Interaction) -> None:
    """Allow only admins, Manage Guild members, or the configured DJ role.

    Unlike generic DJ commands, a missing DJ role must not make configuration
    available to everyone.
    """
    member = interaction.user
    if member.guild_permissions.administrator or member.guild_permissions.manage_guild:
        return
    dj_id = guild_config.dj_role_id(interaction.guild_id)
    if dj_id and dj_id in {role.id for role in member.roles}:
        return
    raise app_commands.AppCommandError(
        "Necesitás Administrador, Gestionar servidor o el rol DJ para configurar TTS."
    )
