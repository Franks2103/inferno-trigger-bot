# services/stats.py
import json
from pathlib import Path
from typing import Any

_DATA_FILE = Path(__file__).parent.parent / "data" / "stats.json"


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


def record_play(guild_id: int, user_id: int, title: str, webpage_url: str) -> None:
    data = _load()
    g = str(guild_id)
    u = str(user_id)

    if g not in data:
        data[g] = {"total": 0, "songs": {}, "users": {}}

    data[g]["total"] = data[g].get("total", 0) + 1

    songs = data[g].setdefault("songs", {})
    if webpage_url not in songs:
        songs[webpage_url] = {"title": title, "count": 0}
    songs[webpage_url]["count"] += 1

    users = data[g].setdefault("users", {})
    if u not in users:
        users[u] = 0
    users[u] += 1

    _save(data)


def guild_stats(guild_id: int) -> dict[str, Any]:
    data = _load()
    return data.get(str(guild_id), {"total": 0, "songs": {}, "users": {}})


def top_songs(guild_id: int, limit: int = 10) -> list[dict]:
    g = guild_stats(guild_id)
    songs = g.get("songs", {})
    sorted_songs = sorted(songs.values(), key=lambda x: x["count"], reverse=True)
    return sorted_songs[:limit]


def top_users(guild_id: int, limit: int = 10) -> list[tuple[str, int]]:
    g = guild_stats(guild_id)
    users = g.get("users", {})
    return sorted(users.items(), key=lambda x: x[1], reverse=True)[:limit]


def user_plays(guild_id: int, user_id: int) -> int:
    g = guild_stats(guild_id)
    return g.get("users", {}).get(str(user_id), 0)
