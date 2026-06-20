import json
from pathlib import Path
from typing import Optional

_FILE = Path(__file__).parent.parent / "data" / "guild_config.json"


def _load() -> dict:
    if not _FILE.exists():
        return {}
    with _FILE.open() as f:
        return json.load(f)


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
