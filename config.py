import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")

if not TOKEN:
    raise RuntimeError("Falta DISCORD_TOKEN en tu archivo .env")

YTDL_OPTIONS = {
    "format": "bestaudio[ext=m4a]/bestaudio/best",
    "quiet": True,
    "noplaylist": True,
    "nocheckcertificate": True,
    "no_warnings": True,
    "default_search": "ytsearch",
    "source_address": "0.0.0.0",
}

YTDL_PLAYLIST_OPTIONS = {
    "format": "bestaudio[ext=m4a]/bestaudio/best",
    "quiet": True,
    "noplaylist": False,
    "playlistend": 50,
    "nocheckcertificate": True,
    "no_warnings": True,
    "extract_flat": True,
    "source_address": "0.0.0.0",
}

FFMPEG_OPTIONS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn",
}

# Bandelion TTS Bridge. These environment values are global safety defaults;
# each guild may override the character and cooldown limits in its config.
TTS_BRIDGE_ENABLED = os.getenv("TTS_BRIDGE_ENABLED", "true").lower() == "true"
TTS_PROVIDER = os.getenv("TTS_PROVIDER", "espeak")
TTS_MAX_CHARS = int(os.getenv("TTS_MAX_CHARS", "250"))
TTS_COOLDOWN_SECONDS = int(os.getenv("TTS_COOLDOWN_SECONDS", "5"))
TTS_TEMP_DIR = Path(os.getenv("TTS_TEMP_DIR", "temp/tts"))
