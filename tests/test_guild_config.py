import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import services.guild_config as gc


def test_get_returns_empty_dict_for_unknown_guild(tmp_path, monkeypatch):
    monkeypatch.setattr(gc, "_FILE", tmp_path / "guild_config.json")
    cfg = gc.get(123)
    assert cfg == {}


def test_set_and_get_value(tmp_path, monkeypatch):
    monkeypatch.setattr(gc, "_FILE", tmp_path / "guild_config.json")
    gc.set_value(123, dj_role=456)
    cfg = gc.get(123)
    assert cfg["dj_role"] == 456


def test_dj_role_id_none_when_not_set(tmp_path, monkeypatch):
    monkeypatch.setattr(gc, "_FILE", tmp_path / "guild_config.json")
    assert gc.dj_role_id(999) is None


def test_dj_role_id_returns_value_when_set(tmp_path, monkeypatch):
    monkeypatch.setattr(gc, "_FILE", tmp_path / "guild_config.json")
    gc.set_value(999, dj_role=111)
    assert gc.dj_role_id(999) == 111
