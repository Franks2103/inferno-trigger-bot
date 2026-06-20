import json
from pathlib import Path
from typing import Optional

_FILE = Path(__file__).parent.parent / "data" / "favorites.json"
MAX_PER_USER = 25


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


def get_all(user_id: int) -> list[dict]:
    return _load().get(str(user_id), [])


def add(user_id: int, title: str, webpage_url: str, thumbnail: Optional[str]) -> str:
    data = _load()
    key = str(user_id)
    data.setdefault(key, [])

    if any(f["webpage_url"] == webpage_url for f in data[key]):
        return "duplicate"
    if len(data[key]) >= MAX_PER_USER:
        return "full"

    data[key].append({"title": title, "webpage_url": webpage_url, "thumbnail": thumbnail})
    _save(data)
    return "ok"


def remove(user_id: int, position: int) -> Optional[dict]:
    data = _load()
    key = str(user_id)
    favs = data.get(key, [])
    if not 1 <= position <= len(favs):
        return None
    removed = favs.pop(position - 1)
    data[key] = favs
    _save(data)
    return removed
