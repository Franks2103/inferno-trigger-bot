import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import unittest.mock as mock
import types

# Mock discord and all discord-dependent modules before importing cogs.music
try:
    import discord
    _discord_available = True
except ImportError:
    _discord_available = False

if not _discord_available:
    # discord.ext.commands.Cog is used as a base class with keyword `name=`,
    # so it must be a real class whose __init_subclass__ accepts **kwargs.
    class _FakeCog:
        def __init_subclass__(cls, name=None, **kwargs):
            super().__init_subclass__(**kwargs)

    # discord.app_commands.Group is instantiated at class body level, so it
    # must be callable and return a plain object.
    class _FakeGroup:
        def __init__(self, *args, **kwargs):
            pass
        def __getattr__(self, item):
            return mock.MagicMock()

    class _FakeAppCommands(types.ModuleType):
        Group = _FakeGroup
        def __getattr__(self, item):
            return mock.MagicMock()

    class _FakeCommands(types.ModuleType):
        Cog = _FakeCog
        def __getattr__(self, item):
            return mock.MagicMock()

    class _FakeDiscordExt(types.ModuleType):
        commands = _FakeCommands('discord.ext.commands')
        def __getattr__(self, item):
            return mock.MagicMock()

    _fake_discord = mock.MagicMock()
    _fake_discord.ext = _FakeDiscordExt('discord.ext')
    _fake_discord.ext.commands = _FakeCommands('discord.ext.commands')
    _fake_discord.ext.commands.Cog = _FakeCog
    _fake_discord.app_commands = _FakeAppCommands('discord.app_commands')
    _fake_discord.app_commands.Group = _FakeGroup

    sys.modules['discord'] = _fake_discord
    sys.modules['discord.ext'] = _fake_discord.ext
    sys.modules['discord.ext.commands'] = _fake_discord.ext.commands
    sys.modules['discord.app_commands'] = _fake_discord.app_commands

# Mock local modules that also import discord at the top level
for mod_name in [
    'models',
    'models.track',
    'services.extractor',
    'services.music_service',
    'services.permissions',
    'ui',
    'ui.player_view',
    'ui.search_view',
]:
    if mod_name not in sys.modules:
        sys.modules[mod_name] = mock.MagicMock()

from cogs.music import _parse_time


def test_parse_seconds():
    assert _parse_time("90") == 90


def test_parse_mm_ss():
    assert _parse_time("1:30") == 90


def test_parse_hh_mm_ss():
    assert _parse_time("1:01:30") == 3690


def test_parse_invalid():
    assert _parse_time("abc") is None


def test_parse_empty():
    assert _parse_time("") is None
