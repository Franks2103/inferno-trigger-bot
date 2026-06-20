import asyncio
import re
from urllib.parse import parse_qs, urlparse

import discord
import yt_dlp
from discord import app_commands
from yt_dlp.utils import DownloadError, ExtractorError

from config import YTDL_OPTIONS, YTDL_PLAYLIST_OPTIONS
from models.track import Track


def looks_like_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def looks_like_playlist_url(value: str) -> bool:
    if not looks_like_url(value):
        return False
    params = parse_qs(urlparse(value).query)
    return "list" in params and "v" not in params


def looks_like_spotify_url(value: str) -> bool:
    return looks_like_url(value) and "spotify.com" in urlparse(value).netloc


def _get_spotify_title_sync(url: str) -> str:
    import urllib.request
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        html = resp.read().decode("utf-8", errors="ignore")
    match = re.search(r'<title[^>]*>([^<]+)</title>', html)
    if match:
        return match.group(1).replace(" | Spotify", "").strip()
    return ""


def _extract_info_sync(query: str) -> dict:
    search = query if looks_like_url(query) else f"ytsearch1:{query}"
    with yt_dlp.YoutubeDL(YTDL_OPTIONS) as ytdl:
        return ytdl.extract_info(search, download=False)


def _extract_playlist_sync(url: str) -> dict:
    with yt_dlp.YoutubeDL(YTDL_PLAYLIST_OPTIONS) as ytdl:
        return ytdl.extract_info(url, download=False)


def _search_sync(query: str, limit: int) -> dict:
    with yt_dlp.YoutubeDL(YTDL_OPTIONS) as ytdl:
        return ytdl.extract_info(f"ytsearch{limit}:{query}", download=False)


def _entry_to_track(entry: dict, requester: discord.Member) -> Track | None:
    stream_url = entry.get("url")
    webpage_url = entry.get("webpage_url") or stream_url
    if not stream_url or not webpage_url:
        return None
    return Track(
        title=entry.get("title", "Sin título"),
        webpage_url=webpage_url,
        requester=requester,
        stream_url=stream_url,
        duration=entry.get("duration"),
        thumbnail=entry.get("thumbnail"),
    )


def _flat_entry_to_track(entry: dict, requester: discord.Member) -> Track | None:
    video_id = entry.get("id") or ""
    webpage_url = entry.get("webpage_url") or (
        f"https://www.youtube.com/watch?v={video_id}" if video_id else ""
    )
    if not webpage_url:
        return None
    return Track(
        title=entry.get("title", "Sin título"),
        webpage_url=webpage_url,
        requester=requester,
        stream_url=None,
        duration=entry.get("duration"),
        thumbnail=entry.get("thumbnail"),
    )


async def resolve_track(track: Track) -> None:
    data = await asyncio.to_thread(_extract_info_sync, track.webpage_url)
    if "entries" in data:
        entries = [e for e in data["entries"] if e]
        data = entries[0] if entries else {}
    track.stream_url = data.get("url") or ""


async def create_track(query: str, requester: discord.Member) -> Track:
    try:
        data = await asyncio.to_thread(_extract_info_sync, query)
    except (DownloadError, ExtractorError) as exc:
        raise app_commands.AppCommandError(
            "No pude extraer ese audio. Prueba con otro link o búsqueda."
        ) from exc

    if "entries" in data:
        entries = [e for e in data["entries"] if e]
        if not entries:
            raise app_commands.AppCommandError("No encontré resultados para esa búsqueda.")
        data = entries[0]

    track = _entry_to_track(data, requester)
    if not track:
        raise app_commands.AppCommandError("No encontré una URL de audio válida.")
    return track


async def create_track_from_spotify(url: str, requester: discord.Member) -> Track:
    try:
        title = await asyncio.to_thread(_get_spotify_title_sync, url)
    except Exception as exc:
        raise app_commands.AppCommandError(
            "No pude leer el link de Spotify. Verificá que sea público."
        ) from exc
    if not title:
        raise app_commands.AppCommandError("No pude obtener el título de Spotify.")
    return await create_track(title, requester)


async def create_tracks_from_playlist(url: str, requester: discord.Member) -> list[Track]:
    try:
        data = await asyncio.to_thread(_extract_playlist_sync, url)
    except (DownloadError, ExtractorError) as exc:
        raise app_commands.AppCommandError(
            "No pude extraer la playlist. Verificá que el link sea válido y público."
        ) from exc

    entries = [e for e in data.get("entries", []) if e]
    if not entries:
        raise app_commands.AppCommandError("La playlist está vacía o no es accesible.")

    tracks = [t for e in entries if (t := _flat_entry_to_track(e, requester))]
    if not tracks:
        raise app_commands.AppCommandError("No pude extraer canciones de la playlist.")
    return tracks


async def search_tracks(query: str, requester: discord.Member, limit: int = 5) -> list[Track]:
    try:
        data = await asyncio.to_thread(_search_sync, query, limit)
    except (DownloadError, ExtractorError) as exc:
        raise app_commands.AppCommandError("No pude realizar la búsqueda.") from exc

    entries = [e for e in data.get("entries", []) if e]
    return [t for e in entries[:limit] if (t := _entry_to_track(e, requester))]


async def get_related_track(track: Track, requester: discord.Member) -> Track | None:
    base_title = re.sub(r'\s*[\(\[][^)\]]*[\)\]]', '', track.title).strip()
    try:
        tracks = await search_tracks(f"{base_title} mix", requester, limit=3)
        for candidate in tracks:
            if candidate.webpage_url != track.webpage_url:
                return candidate
    except Exception:
        pass
    return None
