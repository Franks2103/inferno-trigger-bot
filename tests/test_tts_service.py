import pytest

from services.tts_service import TtsService, TtsValidationError


def config(**overrides):
    return {
        "maxChars": 20,
        "blockLinks": False,
        "blockMentions": True,
        **overrides,
    }


def test_validate_text_rejects_over_limit():
    with pytest.raises(TtsValidationError, match="max_chars"):
        TtsService().validate_text("x" * 21, config())


def test_sanitize_removes_custom_emojis_and_markdown():
    result = TtsService().sanitize_text("**Hola** <a:party:123456>", config())
    assert result == "Hola"


def test_sanitize_blocks_broadcast_mentions():
    with pytest.raises(TtsValidationError, match="broadcast_mention"):
        TtsService().sanitize_text("hola @everyone", config())


def test_validate_blocks_links_when_configured():
    with pytest.raises(TtsValidationError, match="links_blocked"):
        TtsService().validate_text("https://example.com", config(blockLinks=True))


def test_validate_blocks_obvious_api_key():
    with pytest.raises(TtsValidationError, match="possible_secret"):
        TtsService().validate_text("api_key=x", config())


def test_provider_info_reports_missing_espeak(monkeypatch):
    monkeypatch.setattr("services.tts_service.shutil.which", lambda _: None)
    info = TtsService().get_provider_info()
    assert info["available"] is False
    assert "espeak-ng" in info["message"]
