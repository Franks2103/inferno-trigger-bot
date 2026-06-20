import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import services.stats as stats_svc


def test_record_and_retrieve_total(tmp_path, monkeypatch):
    monkeypatch.setattr(stats_svc, "_DATA_FILE", tmp_path / "stats.json")
    stats_svc.record_play(1, 10, "Song A", "http://a.com")
    stats_svc.record_play(1, 10, "Song A", "http://a.com")
    stats_svc.record_play(1, 20, "Song B", "http://b.com")

    g = stats_svc.guild_stats(1)
    assert g["total"] == 3


def test_top_songs_sorted_by_count(tmp_path, monkeypatch):
    monkeypatch.setattr(stats_svc, "_DATA_FILE", tmp_path / "stats.json")
    stats_svc.record_play(1, 10, "Song A", "http://a.com")
    stats_svc.record_play(1, 10, "Song A", "http://a.com")
    stats_svc.record_play(1, 20, "Song B", "http://b.com")

    top = stats_svc.top_songs(1)
    assert top[0]["title"] == "Song A"
    assert top[0]["count"] == 2


def test_user_plays_count(tmp_path, monkeypatch):
    monkeypatch.setattr(stats_svc, "_DATA_FILE", tmp_path / "stats.json")
    stats_svc.record_play(1, 42, "X", "http://x.com")
    assert stats_svc.user_plays(1, 42) == 1
    assert stats_svc.user_plays(1, 99) == 0
