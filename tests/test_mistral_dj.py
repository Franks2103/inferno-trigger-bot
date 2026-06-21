import json
import pytest
import requests as req
from unittest.mock import MagicMock, patch

from services import mistral_dj


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_response(recs: list[dict], commentary: str = "Vamos con algo energético.") -> str:
    return json.dumps({"djCommentary": commentary, "recommendations": recs})


def _rec(query: str, rtype: str = "core_taste") -> dict:
    return {"query": query, "type": rtype, "genre": "rock", "energy": "high"}


# ── _parse_suggestions ────────────────────────────────────────────────────────

def test_parse_suggestions_valid_json():
    text = _make_response([_rec("Queen - Bohemian Rhapsody"), _rec("Led Zeppelin - Stairway to Heaven")])
    songs, commentary = mistral_dj._parse_suggestions(text, [], 5)
    assert songs == ["Queen - Bohemian Rhapsody", "Led Zeppelin - Stairway to Heaven"]
    assert commentary == "Vamos con algo energético."


def test_parse_suggestions_json_embedded_in_prose():
    inner = _make_response([_rec("Dua Lipa - Levitating"), _rec("The Weeknd - Blinding Lights")])
    text = f"Aquí mis recomendaciones:\n{inner}\n¡Disfrutá!"
    songs, _ = mistral_dj._parse_suggestions(text, [], 5)
    assert "Dua Lipa - Levitating" in songs
    assert "The Weeknd - Blinding Lights" in songs


def test_parse_suggestions_invalid_returns_empty():
    songs, commentary = mistral_dj._parse_suggestions("sin JSON aquí", [], 5)
    assert songs == []
    assert commentary == ""


def test_parse_suggestions_empty_string_returns_empty():
    songs, commentary = mistral_dj._parse_suggestions("", [], 5)
    assert songs == []
    assert commentary == ""


def test_parse_suggestions_filters_recent_by_substring():
    text = _make_response([_rec("Queen - Bohemian Rhapsody"), _rec("Coldplay - Yellow")])
    songs, _ = mistral_dj._parse_suggestions(text, ["Bohemian Rhapsody"], 5)
    assert "Queen - Bohemian Rhapsody" not in songs
    assert "Coldplay - Yellow" in songs


def test_parse_suggestions_filter_is_case_insensitive():
    text = _make_response([_rec("queen - bohemian rhapsody"), _rec("Coldplay - Yellow")])
    songs, _ = mistral_dj._parse_suggestions(text, ["BOHEMIAN RHAPSODY"], 5)
    assert "queen - bohemian rhapsody" not in songs


def test_parse_suggestions_respects_count():
    recs = [_rec(f"Artist {i} - Song {i}") for i in range(10)]
    songs, _ = mistral_dj._parse_suggestions(_make_response(recs), [], 3)
    assert len(songs) == 3


def test_parse_suggestions_skips_recs_without_query():
    text = _make_response([{"type": "core_taste"}, _rec("Valid - Song")])
    songs, _ = mistral_dj._parse_suggestions(text, [], 5)
    assert songs == ["Valid - Song"]


# ── _call_mistral ─────────────────────────────────────────────────────────────

def test_call_mistral_no_api_key_returns_empty(monkeypatch):
    monkeypatch.setenv("MISTRAL_API_KEY", "")
    result = mistral_dj._call_mistral("system", "user")
    assert result == ""


def test_call_mistral_returns_message_content(monkeypatch):
    monkeypatch.setenv("MISTRAL_API_KEY", "test-key")
    monkeypatch.setenv("MISTRAL_MODEL", "mistral-small-latest")
    payload = _make_response([_rec("Song A"), _rec("Song B")])
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.json.return_value = {"choices": [{"message": {"content": payload}}]}
    with patch("services.mistral_dj.requests.post", return_value=mock_resp) as mock_post:
        result = mistral_dj._call_mistral("system prompt", "user prompt")
    assert result == payload
    body = mock_post.call_args.kwargs.get("json") or mock_post.call_args[1]["json"]
    assert body["model"] == "mistral-small-latest"
    assert body["max_tokens"] == 1000
    assert body["response_format"] == {"type": "json_object"}


def test_call_mistral_http_error_raises(monkeypatch):
    monkeypatch.setenv("MISTRAL_API_KEY", "test-key")
    mock_resp = MagicMock()
    mock_resp.ok = False
    mock_resp.raise_for_status.side_effect = req.HTTPError("500 Server Error")
    with patch("services.mistral_dj.requests.post", return_value=mock_resp):
        with pytest.raises(req.HTTPError):
            mistral_dj._call_mistral("system", "user")
