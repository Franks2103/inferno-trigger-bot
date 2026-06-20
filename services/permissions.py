# services/permissions.py
from enum import Enum, auto
from typing import Optional

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
