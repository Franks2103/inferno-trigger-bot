import json
import os
from pathlib import Path
from typing import Optional


_FILE = Path(__file__).parent.parent / "data" / "guild_config.json"

TTS_BRIDGE_DEFAULTS = {
    "enabled": False,
    "textChannelId": None,
    "language": "es",
    "voice": "default",
    "maxChars": int(os.getenv("TTS_MAX_CHARS", "250")),
    "cooldownSeconds": int(os.getenv("TTS_COOLDOWN_SECONDS", "5")),
    "readUsername": True,
    "usernameTemplate": "{username} dice",
    "ignoreBots": True,
    "ignoreCommands": True,
    "blockMentions": True,
    "blockLinks": False,
    "requireUserInVoice": True,
    "autoJoinUserVoiceChannel": True,
    "autoMoveBetweenVoiceChannels": False,
    "pauseMusicWhileSpeaking": True,
    "maxPendingPerUser": 3,
    "maxPendingPerGuild": 20,
}


def _load() -> dict:
    if not _FILE.exists():
        return {}
    try:
        with _FILE.open() as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save(data: dict) -> None:
    _FILE.parent.mkdir(exist_ok=True)
    with _FILE.open("w") as f:
        json.dump(data, f, indent=2)


def get(guild_id: int) -> dict:
    return _load().get(str(guild_id), {})


def set_value(guild_id: int, **kwargs) -> None:
    data = _load()
    key = str(guild_id)
    data.setdefault(key, {}).update(kwargs)
    _save(data)


def dj_role_id(guild_id: int) -> Optional[int]:
    return get(guild_id).get("dj_role")


def music_channel_id(guild_id: int) -> Optional[int]:
    return get(guild_id).get("music_channel")


def default_volume(guild_id: int) -> float:
    return get(guild_id).get("default_volume", 0.5)


def max_queue(guild_id: int) -> int:
    return get(guild_id).get("max_queue", 100)


def panel_ids(guild_id: int) -> tuple[int | None, int | None]:
    """Returns (channel_id, message_id) or (None, None)."""
    cfg = get(guild_id)
    return cfg.get("panel_channel_id"), cfg.get("panel_message_id")


def set_panel(guild_id: int, channel_id: int | None, message_id: int | None) -> None:
    set_value(guild_id, panel_channel_id=channel_id, panel_message_id=message_id)


def tts_bridge(guild_id: int) -> dict:
    """Return a complete TTS Bridge config, including safe defaults."""
    configured = get(guild_id).get("ttsBridgeConfig", {})
    return {**TTS_BRIDGE_DEFAULTS, **configured}


def set_tts_bridge(guild_id: int, **kwargs) -> None:
    config = tts_bridge(guild_id)
    config.update(kwargs)
    set_value(guild_id, ttsBridgeConfig=config)
