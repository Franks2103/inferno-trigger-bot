# services/history_store.py
import json
from pathlib import Path
from typing import Any

_DATA_FILE = Path(__file__).parent.parent / "data" / "history.json"
MAX_PER_GUILD = 100


def _load() -> dict:
    if _DATA_FILE.exists():
        try:
            return json.loads(_DATA_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save(data: dict) -> None:
    _DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    _DATA_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def push(guild_id: int, track_data: dict[str, Any]) -> None:
    data = _load()
    key = str(guild_id)
    guild_history = data.get(key, [])
    guild_history.append(track_data)
    if len(guild_history) > MAX_PER_GUILD:
        guild_history = guild_history[-MAX_PER_GUILD:]
    data[key] = guild_history
    _save(data)


def get_all(guild_id: int) -> list[dict[str, Any]]:
    data = _load()
    return data.get(str(guild_id), [])


def clear(guild_id: int) -> None:
    data = _load()
    data.pop(str(guild_id), None)
    _save(data)
