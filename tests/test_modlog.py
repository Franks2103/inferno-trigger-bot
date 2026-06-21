import pytest
from datetime import timedelta
from services import modlog


GUILD = 111222333


@pytest.fixture(autouse=True)
def clean_modlog(tmp_path, monkeypatch):
    monkeypatch.setattr(modlog, "_DATA_DIR", tmp_path / "modlog")


def _make_entry(**kwargs):
    defaults = dict(
        type="warn",
        target_id=1,
        target_name="user#0001",
        moderator_id=2,
        moderator_name="mod#0002",
        reason="test reason",
    )
    defaults.update(kwargs)
    return modlog.add_entry(GUILD, **defaults)


def test_add_entry_returns_entry_with_id():
    entry = _make_entry()
    assert "id" in entry
    assert entry["type"] == "warn"
    assert entry["target_id"] == 1
    assert "timestamp" in entry


def test_get_entries_filters_by_target():
    _make_entry(target_id=1)
    _make_entry(target_id=2)
    entries = modlog.get_entries(GUILD, 1)
    assert len(entries) == 1
    assert entries[0]["target_id"] == 1


def test_remove_entry_returns_true_on_success():
    entry = _make_entry()
    result = modlog.remove_entry(GUILD, entry["id"])
    assert result is True
    assert modlog.get_entries(GUILD, 1) == []


def test_remove_entry_returns_false_for_unknown_id():
    result = modlog.remove_entry(GUILD, "nonexistent-id")
    assert result is False


def test_recent_entries_respects_limit():
    for i in range(7):
        _make_entry(reason=f"reason {i}")
    recent = modlog.recent_entries(GUILD, 5)
    assert len(recent) == 5


def test_recent_entries_empty_guild():
    assert modlog.recent_entries(GUILD, 5) == []


def test_parse_duration_seconds():
    assert modlog.parse_duration("30s") == timedelta(seconds=30)


def test_parse_duration_minutes():
    assert modlog.parse_duration("10m") == timedelta(minutes=10)


def test_parse_duration_hours():
    assert modlog.parse_duration("2h") == timedelta(hours=2)


def test_parse_duration_days():
    assert modlog.parse_duration("7d") == timedelta(days=7)


def test_parse_duration_invalid_suffix():
    assert modlog.parse_duration("10x") is None


def test_parse_duration_invalid_number():
    assert modlog.parse_duration("abc") is None


def test_parse_duration_empty():
    assert modlog.parse_duration("") is None


def test_parse_duration_zero_is_invalid():
    assert modlog.parse_duration("0m") is None


def test_parse_duration_negative_is_invalid():
    assert modlog.parse_duration("-5m") is None
