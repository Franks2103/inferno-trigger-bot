"""Local, provider-neutral speech generation for Bandelion TTS Bridge."""

import asyncio
import re
import shutil
import subprocess
import uuid
from pathlib import Path

from config import TTS_PROVIDER, TTS_TEMP_DIR

_CUSTOM_EMOJI = re.compile(r"<a?:[A-Za-z0-9_]+:\d+>")
_MARKDOWN = re.compile(r"[`*_~>|]+")
_LINK = re.compile(r"https?://\S+", re.IGNORECASE)
_SECRET = re.compile(
    r"(?:discord(?:[_ -]?token)?|api[_ -]?key|secret|authorization)\s*[:=]\s*\S+|"
    r"[MN][A-Za-z\d_-]{23,}\.[A-Za-z\d_-]{6,}\.[A-Za-z\d_-]{20,}",
    re.IGNORECASE,
)


class TtsValidationError(ValueError):
    """A user message cannot safely be spoken."""


class TtsProviderError(RuntimeError):
    """The local speech provider could not generate audio."""


class TtsService:
    def __init__(self, *, provider: str = TTS_PROVIDER, temp_dir: Path = TTS_TEMP_DIR):
        self.provider = provider
        self.temp_dir = Path(temp_dir)

    def get_provider_info(self) -> dict[str, str | bool]:
        available = self.provider == "espeak" and shutil.which("espeak-ng") is not None
        return {
            "provider": self.provider,
            "available": available,
            "message": "OK" if available else "espeak-ng no está instalado. Instálalo con el gestor de paquetes del sistema.",
        }

    def is_provider_available(self) -> bool:
        return bool(self.get_provider_info()["available"])

    def validate_text(self, text: str, config: dict) -> str:
        cleaned = text.strip()
        if not cleaned:
            raise TtsValidationError("empty")
        if len(cleaned) > int(config["maxChars"]):
            raise TtsValidationError("max_chars")
        if config.get("blockLinks") and _LINK.search(cleaned):
            raise TtsValidationError("links_blocked")
        if _SECRET.search(cleaned):
            raise TtsValidationError("possible_secret")
        return cleaned

    def sanitize_text(self, text: str, config: dict) -> str:
        if config.get("blockMentions") and ("@everyone" in text or "@here" in text):
            raise TtsValidationError("broadcast_mention")
        text = _CUSTOM_EMOJI.sub("", text)
        text = _MARKDOWN.sub("", text)
        text = re.sub(r"\s+", " ", text).strip()
        if not text:
            raise TtsValidationError("empty_after_sanitize")
        return text

    async def generate_speech(self, text: str, *, language: str, voice: str = "default") -> Path:
        info = self.get_provider_info()
        if not info["available"]:
            raise TtsProviderError(str(info["message"]))
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        output = self.temp_dir / f"tts-{uuid.uuid4().hex}.wav"
        voice_arg = voice if voice != "default" else language
        command = ["espeak-ng", "-v", voice_arg, "-w", str(output), text]

        def run() -> None:
            try:
                subprocess.run(command, check=True, capture_output=True, text=True, timeout=30)
            except (OSError, subprocess.SubprocessError) as exc:
                raise TtsProviderError("No se pudo generar audio con espeak-ng.") from exc

        await asyncio.to_thread(run)
        return output

    def cleanup(self, file_path: Path | None) -> None:
        if not file_path:
            return
        try:
            file_path.unlink(missing_ok=True)
        except OSError:
            pass
