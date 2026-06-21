import json
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

_DATA_DIR = Path(__file__).parent.parent / "data" / "modlog"

_DURATION_UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400}


def _file(guild_id: int) -> Path:
    return _DATA_DIR / f"{guild_id}.json"


def _load(guild_id: int) -> list[dict]:
    f = _file(guild_id)
    if not f.exists():
        return []
    try:
        with f.open() as fh:
            return json.load(fh)
    except (json.JSONDecodeError, OSError):
        return []


def _save(guild_id: int, entries: list[dict]) -> None:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    with _file(guild_id).open("w") as fh:
        json.dump(entries, fh, indent=2, ensure_ascii=False)


def add_entry(
    guild_id: int,
    *,
    type: str,
    target_id: int,
    target_name: str,
    moderator_id: int,
    moderator_name: str,
    reason: str,
) -> dict:
    entry = {
        "id": str(uuid.uuid4()),
        "type": type,
        "target_id": target_id,
        "target_name": target_name,
        "moderator_id": moderator_id,
        "moderator_name": moderator_name,
        "reason": reason,
        "timestamp": datetime.utcnow().isoformat(),
    }
    entries = _load(guild_id)
    entries.append(entry)
    _save(guild_id, entries)
    return entry


def get_entries(guild_id: int, target_id: int, entry_type: str | None = None) -> list[dict]:
    entries = [e for e in _load(guild_id) if e["target_id"] == target_id]
    if entry_type is not None:
        entries = [e for e in entries if e["type"] == entry_type]
    return entries


def remove_entry(guild_id: int, entry_id: str) -> bool:
    entries = _load(guild_id)
    new_entries = [e for e in entries if e["id"] != entry_id]
    if len(new_entries) == len(entries):
        return False
    _save(guild_id, new_entries)
    return True


def recent_entries(guild_id: int, limit: int = 5) -> list[dict]:
    return _load(guild_id)[-limit:]


def parse_duration(s: str) -> Optional[timedelta]:
    s = s.strip().lower()
    if len(s) < 2:
        return None
    suffix = s[-1]
    if suffix not in _DURATION_UNITS:
        return None
    try:
        amount = int(s[:-1])
    except ValueError:
        return None
    if amount <= 0:
        return None
    return timedelta(seconds=amount * _DURATION_UNITS[suffix])
