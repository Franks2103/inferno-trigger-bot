import sys
from types import SimpleNamespace

import pytest

# test_parse_time installs a lightweight `ui` module mock during collection.
# This cog needs the real package, so restore it locally before importing.
for module_name in ("ui", "ui.embeds"):
    sys.modules.pop(module_name, None)

fake_commands = sys.modules.get("discord.ext.commands")
if fake_commands and not hasattr(fake_commands.Cog, "listener"):
    fake_commands.Cog.listener = staticmethod(lambda: lambda func: func)

from cogs.tts_bridge_cog import TtsBridgeCog
from services import guild_config


def message(*, guild_id=1, channel_id=10, bot=False):
    return SimpleNamespace(
        guild=SimpleNamespace(id=guild_id),
        channel=SimpleNamespace(id=channel_id),
        author=SimpleNamespace(id=2, bot=bot),
        content="hola",
        id=3,
        is_system=lambda: False,
        clean_content="hola",
    )


@pytest.mark.asyncio
async def test_listener_ignores_bots(tmp_path, monkeypatch):
    monkeypatch.setattr(guild_config, "_FILE", tmp_path / "guild_config.json")
    guild_config.set_tts_bridge(1, enabled=True, textChannelId=10)
    cog = TtsBridgeCog(SimpleNamespace(user=SimpleNamespace(id=999)))

    await cog.on_message(message(bot=True))

    assert cog.queues == {}


@pytest.mark.asyncio
async def test_listener_ignores_unconfigured_channel(tmp_path, monkeypatch):
    monkeypatch.setattr(guild_config, "_FILE", tmp_path / "guild_config.json")
    guild_config.set_tts_bridge(1, enabled=True, textChannelId=99)
    cog = TtsBridgeCog(SimpleNamespace(user=SimpleNamespace(id=999)))

    await cog.on_message(message(channel_id=10))

    assert cog.queues == {}


@pytest.mark.asyncio
async def test_listener_ignores_user_outside_voice(tmp_path, monkeypatch):
    monkeypatch.setattr(guild_config, "_FILE", tmp_path / "guild_config.json")
    guild_config.set_tts_bridge(1, enabled=True, textChannelId=10)
    cog = TtsBridgeCog(SimpleNamespace(user=SimpleNamespace(id=999)))

    await cog.on_message(message())

    assert cog.queues == {}
