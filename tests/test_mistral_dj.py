import json
import pytest
import requests as req
from unittest.mock import MagicMock, patch

from services import mistral_dj


# ── _parse_suggestions ────────────────────────────────────────────────────────

def test_parse_suggestions_valid_json():
    text = '["Queen - Bohemian Rhapsody", "Led Zeppelin - Stairway to Heaven"]'
    result = mistral_dj._parse_suggestions(text, [], 5)
    assert result == ["Queen - Bohemian Rhapsody", "Led Zeppelin - Stairway to Heaven"]


def test_parse_suggestions_json_embedded_in_prose():
    text = 'Aquí mis recomendaciones:\n["Dua Lipa - Levitating", "The Weeknd - Blinding Lights"]\n¡Disfrutá!'
    result = mistral_dj._parse_suggestions(text, [], 5)
    assert "Dua Lipa - Levitating" in result
    assert "The Weeknd - Blinding Lights" in result


def test_parse_suggestions_invalid_returns_empty():
    assert mistral_dj._parse_suggestions("sin JSON aquí", [], 5) == []


def test_parse_suggestions_empty_string_returns_empty():
    assert mistral_dj._parse_suggestions("", [], 5) == []


def test_parse_suggestions_filters_recent_by_substring():
    text = '["Queen - Bohemian Rhapsody", "Coldplay - Yellow"]'
    result = mistral_dj._parse_suggestions(text, ["Bohemian Rhapsody"], 5)
    assert "Queen - Bohemian Rhapsody" not in result
    assert "Coldplay - Yellow" in result


def test_parse_suggestions_filter_is_case_insensitive():
    text = '["queen - bohemian rhapsody", "Coldplay - Yellow"]'
    result = mistral_dj._parse_suggestions(text, ["BOHEMIAN RHAPSODY"], 5)
    assert "queen - bohemian rhapsody" not in result


def test_parse_suggestions_respects_count():
    songs = [f"Artist {i} - Song {i}" for i in range(10)]
    result = mistral_dj._parse_suggestions(json.dumps(songs), [], 3)
    assert len(result) == 3


def test_parse_suggestions_non_string_items_skipped():
    text = '["Valid Song", 42, null, "Another Song"]'
    result = mistral_dj._parse_suggestions(text, [], 5)
    assert result == ["Valid Song", "Another Song"]


# ── _call_mistral ─────────────────────────────────────────────────────────────

def test_call_mistral_no_api_key_returns_empty(monkeypatch):
    monkeypatch.setenv("MISTRAL_API_KEY", "")
    result = mistral_dj._call_mistral("system", "user")
    assert result == ""


def test_call_mistral_returns_message_content(monkeypatch):
    monkeypatch.setenv("MISTRAL_API_KEY", "test-key")
    monkeypatch.setenv("MISTRAL_MODEL", "ministral-3b")
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": '["Song A", "Song B"]'}}]
    }
    with patch("services.mistral_dj.requests.post", return_value=mock_resp) as mock_post:
        result = mistral_dj._call_mistral("system prompt", "user prompt")
    assert result == '["Song A", "Song B"]'
    call_kwargs = mock_post.call_args
    body = call_kwargs.kwargs["json"] if call_kwargs.kwargs else call_kwargs[1]["json"]
    assert body["model"] == "ministral-3b"
    assert body["max_tokens"] == 300


def test_call_mistral_http_error_raises(monkeypatch):
    monkeypatch.setenv("MISTRAL_API_KEY", "test-key")
    mock_resp = MagicMock()
    mock_resp.raise_for_status.side_effect = req.HTTPError("500 Server Error")
    with patch("services.mistral_dj.requests.post", return_value=mock_resp):
        with pytest.raises(req.HTTPError):
            mistral_dj._call_mistral("system", "user")
