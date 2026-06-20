# Discord Bot Upgrade — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Llevar el bot de una base funcional a un bot de música profesional, estable y mantenible con permisos avanzados, panel persistente, filtros de audio, estadísticas y cobertura de tests.

**Architecture:** Cog + Service ya está bien separado. El plan agrega capas verticales: persistencia robusta (JSON thread-safe), capa de permisos unificada, capa de UI más rica (panel persistente, history view, stats embeds), y tests unitarios sobre los servicios puros.

**Tech Stack:** discord.py 2.x, yt-dlp, FFmpeg, asyncio, pytest, aiofiles (opcional para I/O async), filelock

---

## Phase 0 — Bug Fixes críticos

### Task 0.1 — Fix `config_cog.py` AttributeError en role/channel eliminados

**Files:**
- Modify: `cogs/config_cog.py:54-58`

- [ ] **Step 1: Aplicar fix defensivo en `show_config`**

Reemplazar las líneas que acceden a `.mention` sin comprobar None:

```python
# ANTES (falla si el role/channel fue eliminado del servidor)
dj_role = guild.get_role(dj_role_id).mention if dj_role_id else "No configurado"
channel = guild.get_channel(ch_id).mention if ch_id else "Cualquier canal"

# DESPUÉS
dj_role_obj = guild.get_role(dj_role_id) if dj_role_id else None
dj_role = dj_role_obj.mention if dj_role_obj else "No configurado (rol eliminado)"

ch_obj = guild.get_channel(ch_id) if ch_id else None
channel = ch_obj.mention if ch_obj else "Cualquier canal"
```

- [ ] **Step 2: Verificar que el archivo compila**

```bash
python -c "import ast; ast.parse(open('cogs/config_cog.py').read()); print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add cogs/config_cog.py
git commit -m "fix: handle deleted role/channel in config show"
```

---

### Task 0.2 — Fix encapsulación en `favorites_cog.py`

**Files:**
- Modify: `cogs/music.py` (agregar método público)
- Modify: `cogs/favorites_cog.py:17`

- [ ] **Step 1: Agregar método público `get_service` en `MusicCog`**

En `cogs/music.py`, después de `_get_service`, agregar:

```python
def get_service_for_guild(self, guild_id: int):
    """Public API for other cogs to read the current MusicService."""
    return self._states.get(guild_id)
```

- [ ] **Step 2: Actualizar `favorites_cog.py` para usar la API pública**

```python
# ANTES (línea 17)
service = music_cog._states.get(interaction.guild_id) if music_cog else None

# DESPUÉS
service = music_cog.get_service_for_guild(interaction.guild_id) if music_cog else None
```

- [ ] **Step 3: Verificar compilación**

```bash
python -c "import ast; ast.parse(open('cogs/favorites_cog.py').read()); print('OK')"
python -c "import ast; ast.parse(open('cogs/music.py').read()); print('OK')"
```

- [ ] **Step 4: Commit**

```bash
git add cogs/music.py cogs/favorites_cog.py
git commit -m "fix: use public API instead of _states in favorites_cog"
```

---

## Phase 1 — Permisos avanzados por acción

### Task 1.1 — Crear `services/permissions.py`

**Files:**
- Create: `services/permissions.py`

- [ ] **Step 1: Crear el módulo de permisos**

```python
# services/permissions.py
from enum import Enum, auto
from typing import Optional

import discord
from discord import app_commands

from services import guild_config


class PermLevel(Enum):
    EVERYONE = auto()
    DJ = auto()
    ADMIN = auto()


# Maps action name → minimum required permission level
ACTION_PERMS: dict[str, PermLevel] = {
    "play": PermLevel.EVERYONE,
    "queue": PermLevel.EVERYONE,
    "now": PermLevel.EVERYONE,
    "voteskip": PermLevel.EVERYONE,
    "fav-add": PermLevel.EVERYONE,
    "fav-list": PermLevel.EVERYONE,
    "fav-play": PermLevel.EVERYONE,
    "fav-remove": PermLevel.EVERYONE,
    "shuffle": PermLevel.EVERYONE,
    "remove": PermLevel.EVERYONE,
    "move": PermLevel.EVERYONE,
    "history": PermLevel.EVERYONE,
    "seek": PermLevel.DJ,
    "replay": PermLevel.DJ,
    "skip": PermLevel.DJ,
    "previous": PermLevel.DJ,
    "loop": PermLevel.DJ,
    "autoplay": PermLevel.DJ,
    "volume": PermLevel.DJ,
    "clear": PermLevel.DJ,
    "join": PermLevel.DJ,
    "leave": PermLevel.DJ,
    "filter": PermLevel.DJ,
    "musicpanel": PermLevel.ADMIN,
    "config-dj-role": PermLevel.ADMIN,
    "config-music-channel": PermLevel.ADMIN,
    "config-volume": PermLevel.ADMIN,
    "config-max-queue": PermLevel.ADMIN,
    "config-show": PermLevel.EVERYONE,
    "stats": PermLevel.EVERYONE,
    "top": PermLevel.EVERYONE,
}


def check(interaction: discord.Interaction, action: str) -> None:
    """Raise AppCommandError if the user lacks permission for `action`."""
    required = ACTION_PERMS.get(action, PermLevel.DJ)

    if required == PermLevel.EVERYONE:
        return

    member = interaction.user
    if member.guild_permissions.administrator:
        return

    if required == PermLevel.ADMIN:
        raise app_commands.AppCommandError("Solo los administradores pueden usar este comando.")

    # DJ level
    dj_id = guild_config.dj_role_id(interaction.guild_id)
    if dj_id is None:
        return  # No DJ role configured → everyone can use DJ commands
    role_ids = {r.id for r in member.roles}
    if dj_id not in role_ids:
        raise app_commands.AppCommandError("Necesitás el rol DJ para usar este comando.")
```

- [ ] **Step 2: Verificar compilación**

```bash
cd /home/fran/Documentos/Coding/chatbot_disc && python -c "from services.permissions import check, PermLevel; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Reemplazar `_check_dj` en `cogs/music.py`**

Agregar el import al tope:

```python
from services import permissions as perms
```

Reemplazar cada llamada a `self._check_dj(interaction)` por `perms.check(interaction, "<nombre_del_comando>")`.

Ejemplos de reemplazos:
- En `skip`: `perms.check(interaction, "skip")`
- En `volume`: `perms.check(interaction, "volume")`
- En `loop`: `perms.check(interaction, "loop")`
- En `clear`: `perms.check(interaction, "clear")`
- En `leave`: `perms.check(interaction, "leave")`
- En `previous`: `perms.check(interaction, "previous")`

Eliminar el método `_check_dj` de `MusicCog`.

- [ ] **Step 4: Verificar compilación**

```bash
python -c "import ast; ast.parse(open('cogs/music.py').read()); print('OK')"
```

- [ ] **Step 5: Commit**

```bash
git add services/permissions.py cogs/music.py
git commit -m "feat: unified permissions system per action"
```

---

## Phase 2 — VoteManager generalizado

### Task 2.1 — Crear `services/vote_manager.py`

**Files:**
- Create: `services/vote_manager.py`
- Modify: `services/music_service.py`
- Modify: `cogs/music.py`

- [ ] **Step 1: Crear `VoteManager`**

```python
# services/vote_manager.py
import math


class VoteManager:
    """Generic vote tracker for any action (skip, etc.)."""

    def __init__(self, threshold: float = 0.5, min_votes: int = 1):
        self._threshold = threshold
        self._min_votes = min_votes
        self._votes: set[int] = set()

    def reset(self) -> None:
        self._votes.clear()

    def has_voted(self, user_id: int) -> bool:
        return user_id in self._votes

    def add(self, user_id: int, total_listeners: int) -> tuple[int, int, bool]:
        """
        Returns (current_votes, required_votes, passed).
        `total_listeners` = number of non-bot members in VC.
        """
        self._votes.add(user_id)
        required = max(self._min_votes, math.ceil(total_listeners * self._threshold))
        return len(self._votes), required, len(self._votes) >= required
```

- [ ] **Step 2: Reemplazar `_skip_votes` en `MusicService`**

En `services/music_service.py`, agregar el import:

```python
from services.vote_manager import VoteManager
```

Reemplazar `self._skip_votes: set[int] = set()` por:

```python
self.skip_votes: VoteManager = VoteManager(threshold=0.5, min_votes=1)
```

En `_player_loop`, reemplazar `self._skip_votes.clear()` por `self.skip_votes.reset()`.

- [ ] **Step 3: Actualizar `/voteskip` en `cogs/music.py`**

```python
@app_commands.command(name="voteskip", description="Vota para saltear la canción actual")
async def voteskip(self, interaction: discord.Interaction) -> None:
    self._check_channel(interaction)
    service = self._get_service(interaction)
    if not service.current:
        return await interaction.response.send_message("No hay nada reproduciéndose.")

    vc = interaction.guild.voice_client
    if not vc:
        return await interaction.response.send_message("No estoy en un canal de voz.")

    if service.skip_votes.has_voted(interaction.user.id):
        return await interaction.response.send_message("Ya votaste para saltear.", ephemeral=True)

    listeners = [m for m in vc.channel.members if not m.bot]
    votes, required, passed = service.skip_votes.add(interaction.user.id, len(listeners))

    if passed:
        vc.stop()
        await interaction.response.send_message(
            f"⏭️ Saltando por votación ({votes}/{required} votos)."
        )
    else:
        await interaction.response.send_message(
            f"🗳️ Voto registrado ({votes}/{required} necesarios para saltear)."
        )
```

- [ ] **Step 4: Verificar compilación**

```bash
python -c "from services.vote_manager import VoteManager; print('OK')"
python -c "import ast; ast.parse(open('services/music_service.py').read()); print('OK')"
python -c "import ast; ast.parse(open('cogs/music.py').read()); print('OK')"
```

- [ ] **Step 5: Commit**

```bash
git add services/vote_manager.py services/music_service.py cogs/music.py
git commit -m "feat: generalized VoteManager replaces _skip_votes set"
```

---

## Phase 3 — Filtros de audio FFmpeg

### Task 3.1 — Agregar `AudioFilter` a `music_service.py` y comando `/filter`

**Files:**
- Modify: `services/music_service.py`
- Modify: `cogs/music.py`
- Modify: `config.py`

- [ ] **Step 1: Definir `AudioFilter` enum en `music_service.py`**

Agregar antes de la clase `LoopMode`:

```python
class AudioFilter(Enum):
    OFF = "off"
    BASS_BOOST = "bassboost"
    NIGHTCORE = "nightcore"
    VAPORWAVE = "vaporwave"
    SLOWED = "slowed"
    KARAOKE = "karaoke"


FILTER_ARGS: dict[AudioFilter, str] = {
    AudioFilter.OFF: "",
    AudioFilter.BASS_BOOST: "bass=g=10",
    AudioFilter.NIGHTCORE: "asetrate=44100*1.25,aresample=44100",
    AudioFilter.VAPORWAVE: "asetrate=44100*0.8,aresample=44100",
    AudioFilter.SLOWED: "atempo=0.85",
    AudioFilter.KARAOKE: "pan=stereo|c0=c0-c1|c1=c1-c0",
}
```

- [ ] **Step 2: Agregar `audio_filter` a `MusicService.__init__`**

```python
self.audio_filter: AudioFilter = AudioFilter.OFF
```

- [ ] **Step 3: Pasar filtro a `YTDLSource`**

Modificar `YTDLSource.__init__` para aceptar el filtro:

```python
class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, track: Track, *, volume: float, seek_to: int = 0, audio_filter: "AudioFilter | None" = None):
        options = dict(FFMPEG_OPTIONS)
        if seek_to:
            options["before_options"] = f"{options.get('before_options', '')} -ss {seek_to}"
        filter_str = FILTER_ARGS.get(audio_filter, "") if audio_filter else ""
        if filter_str:
            options["options"] = f"{options.get('options', '')} -af \"{filter_str}\""
        source = discord.FFmpegPCMAudio(track.stream_url, **options)
        super().__init__(source, volume)
        self.track = track
```

En `_player_loop`, actualizar la línea que crea el source:

```python
source = YTDLSource(track, volume=self.volume, seek_to=seek_to, audio_filter=self.audio_filter)
```

- [ ] **Step 4: Agregar comando `/filter` en `cogs/music.py`**

```python
@app_commands.command(name="filter", description="Aplica un filtro de audio a la reproducción")
@app_commands.choices(name=[
    app_commands.Choice(name="Off (sin filtro)", value="off"),
    app_commands.Choice(name="Bass Boost", value="bassboost"),
    app_commands.Choice(name="Nightcore (+25% velocidad)", value="nightcore"),
    app_commands.Choice(name="Vaporwave (-20% velocidad)", value="vaporwave"),
    app_commands.Choice(name="Slowed (-15% velocidad)", value="slowed"),
    app_commands.Choice(name="Karaoke (elimina voz central)", value="karaoke"),
])
async def filter(self, interaction: discord.Interaction, name: str) -> None:
    self._check_channel(interaction)
    perms.check(interaction, "filter")
    service = self._get_service(interaction)

    from services.music_service import AudioFilter
    new_filter = AudioFilter(name)
    service.audio_filter = new_filter

    # Restart current track with new filter at current position
    if service.current:
        elapsed = service.elapsed_seconds
        service.seek(elapsed)
        vc = interaction.guild.voice_client
        if vc and (vc.is_playing() or vc.is_paused()):
            vc.stop()

    labels = {
        "off": "🔇 Sin filtro",
        "bassboost": "🔈 Bass Boost activado",
        "nightcore": "⚡ Nightcore activado",
        "vaporwave": "🌊 Vaporwave activado",
        "slowed": "🐌 Slowed activado",
        "karaoke": "🎤 Karaoke activado",
    }
    await interaction.response.send_message(labels[name])
```

- [ ] **Step 5: Importar `AudioFilter` en `cogs/music.py`**

```python
from services.music_service import AudioFilter, LoopMode, MusicService
```

- [ ] **Step 6: Verificar compilación**

```bash
python -c "import ast; ast.parse(open('services/music_service.py').read()); print('OK')"
python -c "import ast; ast.parse(open('cogs/music.py').read()); print('OK')"
```

- [ ] **Step 7: Commit**

```bash
git add services/music_service.py cogs/music.py
git commit -m "feat: audio filters via FFmpeg (bassboost, nightcore, vaporwave, slowed, karaoke)"
```

---

## Phase 4 — Historial robusto + `/history`

### Task 4.1 — Persistir historial por guild y agregar `/history`

**Files:**
- Create: `services/history_store.py`
- Modify: `services/music_service.py`
- Modify: `cogs/music.py`
- Create: `ui/history_view.py`

- [ ] **Step 1: Crear `services/history_store.py`**

```python
# services/history_store.py
import json
from pathlib import Path
from typing import Any

_DATA_FILE = Path(__file__).parent.parent / "data" / "history.json"
MAX_PER_GUILD = 50


def _load() -> dict:
    if _DATA_FILE.exists():
        try:
            return json.loads(_DATA_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save(data: dict) -> None:
    _DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    _DATA_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def push(guild_id: int, track_data: dict[str, Any]) -> None:
    data = _load()
    key = str(guild_id)
    guild_history = data.get(key, [])
    guild_history.append(track_data)
    if len(guild_history) > MAX_PER_GUILD:
        guild_history = guild_history[-MAX_PER_GUILD:]
    data[key] = guild_history
    _save(data)


def get_all(guild_id: int) -> list[dict[str, Any]]:
    data = _load()
    return data.get(str(guild_id), [])


def clear(guild_id: int) -> None:
    data = _load()
    data.pop(str(guild_id), None)
    _save(data)
```

- [ ] **Step 2: Persistir en `_player_loop` cuando termina una canción**

En `services/music_service.py`, agregar el import:

```python
from services import history_store
```

En `_player_loop`, después de `self.history.append(track)` (línea que actualmente agrega al historial en memoria), agregar:

```python
history_store.push(
    self.guild.id,
    {
        "title": track.title,
        "webpage_url": track.webpage_url,
        "thumbnail": track.thumbnail,
        "requester_id": track.requester.id,
        "requester_name": track.requester.display_name,
    },
)
```

- [ ] **Step 3: Crear `ui/history_view.py`**

```python
# ui/history_view.py
from __future__ import annotations

from typing import TYPE_CHECKING

import discord

if TYPE_CHECKING:
    from services.music_service import MusicService


def build_history_embed(entries: list[dict], guild: discord.Guild) -> discord.Embed:
    embed = discord.Embed(
        title=f"📜 Historial de {guild.name}",
        color=discord.Color.blurple(),
    )
    if not entries:
        embed.description = "No hay historial disponible."
        return embed
    lines = []
    for i, e in enumerate(reversed(entries[-20:]), 1):
        lines.append(f"`{i}.` [{e['title']}]({e['webpage_url']}) — {e['requester_name']}")
    embed.description = "\n".join(lines)
    return embed
```

- [ ] **Step 4: Agregar comando `/history` en `cogs/music.py`**

```python
@app_commands.command(name="history", description="Muestra el historial de canciones reproducidas")
async def history(self, interaction: discord.Interaction) -> None:
    self._check_channel(interaction)
    from services import history_store
    from ui.history_view import build_history_embed
    entries = history_store.get_all(interaction.guild_id)
    embed = build_history_embed(entries, interaction.guild)
    await interaction.response.send_message(embed=embed, ephemeral=True)
```

- [ ] **Step 5: Verificar compilación**

```bash
python -c "from services.history_store import push, get_all; print('OK')"
python -c "import ast; ast.parse(open('cogs/music.py').read()); print('OK')"
```

- [ ] **Step 6: Commit**

```bash
git add services/history_store.py ui/history_view.py services/music_service.py cogs/music.py
git commit -m "feat: persistent history store + /history command"
```

---

## Phase 5 — Estadísticas básicas

### Task 5.1 — Crear `services/stats.py` y comandos `/stats` `/top`

**Files:**
- Create: `services/stats.py`
- Create: `cogs/stats_cog.py`
- Modify: `services/music_service.py`
- Modify: `main.py`

- [ ] **Step 1: Crear `services/stats.py`**

```python
# services/stats.py
import json
from pathlib import Path
from typing import Any

_DATA_FILE = Path(__file__).parent.parent / "data" / "stats.json"


def _load() -> dict:
    if _DATA_FILE.exists():
        try:
            return json.loads(_DATA_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save(data: dict) -> None:
    _DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    _DATA_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def record_play(guild_id: int, user_id: int, title: str, webpage_url: str) -> None:
    data = _load()
    g = str(guild_id)
    u = str(user_id)

    if g not in data:
        data[g] = {"total": 0, "songs": {}, "users": {}}

    data[g]["total"] = data[g].get("total", 0) + 1

    songs = data[g].setdefault("songs", {})
    if webpage_url not in songs:
        songs[webpage_url] = {"title": title, "count": 0}
    songs[webpage_url]["count"] += 1

    users = data[g].setdefault("users", {})
    if u not in users:
        users[u] = 0
    users[u] += 1

    _save(data)


def guild_stats(guild_id: int) -> dict[str, Any]:
    data = _load()
    return data.get(str(guild_id), {"total": 0, "songs": {}, "users": {}})


def top_songs(guild_id: int, limit: int = 10) -> list[dict]:
    g = guild_stats(guild_id)
    songs = g.get("songs", {})
    sorted_songs = sorted(songs.values(), key=lambda x: x["count"], reverse=True)
    return sorted_songs[:limit]


def top_users(guild_id: int, limit: int = 10) -> list[tuple[str, int]]:
    g = guild_stats(guild_id)
    users = g.get("users", {})
    return sorted(users.items(), key=lambda x: x[1], reverse=True)[:limit]


def user_plays(guild_id: int, user_id: int) -> int:
    g = guild_stats(guild_id)
    return g.get("users", {}).get(str(user_id), 0)
```

- [ ] **Step 2: Registrar plays en `_player_loop`**

En `services/music_service.py`, agregar en el import:

```python
from services import stats as stats_store
```

En `_player_loop`, inmediatamente después de que empiece a reproducirse (después de `voice_client.play(source, after=after_play)`):

```python
stats_store.record_play(
    self.guild.id,
    track.requester.id,
    track.title,
    track.webpage_url,
)
```

- [ ] **Step 3: Crear `cogs/stats_cog.py`**

```python
# cogs/stats_cog.py
import discord
from discord import app_commands
from discord.ext import commands

from services import stats as stats_store


class StatsCog(commands.Cog, name="Stats"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="stats", description="Muestra estadísticas de reproducción")
    @app_commands.choices(scope=[
        app_commands.Choice(name="Servidor", value="server"),
        app_commands.Choice(name="Mi perfil", value="me"),
    ])
    async def stats(self, interaction: discord.Interaction, scope: str = "server") -> None:
        if scope == "me":
            plays = stats_store.user_plays(interaction.guild_id, interaction.user.id)
            embed = discord.Embed(
                title=f"📊 Estadísticas de {interaction.user.display_name}",
                color=discord.Color.green(),
            )
            embed.add_field(name="Canciones pedidas", value=f"`{plays}`", inline=True)
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            g = stats_store.guild_stats(interaction.guild_id)
            embed = discord.Embed(
                title=f"📊 Estadísticas de {interaction.guild.name}",
                color=discord.Color.blue(),
            )
            embed.add_field(name="Total reproducidas", value=f"`{g.get('total', 0)}`", inline=True)
            embed.add_field(name="Canciones únicas", value=f"`{len(g.get('songs', {}))}`", inline=True)
            embed.add_field(name="Usuarios únicos", value=f"`{len(g.get('users', {}))}`", inline=True)
            await interaction.response.send_message(embed=embed)

    @app_commands.command(name="top", description="Muestra el top de canciones o usuarios")
    @app_commands.choices(category=[
        app_commands.Choice(name="Canciones más pedidas", value="songs"),
        app_commands.Choice(name="Usuarios más activos", value="users"),
    ])
    async def top(self, interaction: discord.Interaction, category: str = "songs") -> None:
        if category == "songs":
            songs = stats_store.top_songs(interaction.guild_id, 10)
            embed = discord.Embed(title="🎵 Top 10 canciones", color=discord.Color.purple())
            if not songs:
                embed.description = "Todavía no hay datos."
            else:
                lines = [f"`{i}.` **{s['title']}** — `{s['count']}` plays"
                         for i, s in enumerate(songs, 1)]
                embed.description = "\n".join(lines)
            await interaction.response.send_message(embed=embed)
        else:
            users = stats_store.top_users(interaction.guild_id, 10)
            embed = discord.Embed(title="👑 Top 10 usuarios", color=discord.Color.gold())
            if not users:
                embed.description = "Todavía no hay datos."
            else:
                lines = [f"`{i}.` <@{uid}> — `{count}` canciones"
                         for i, (uid, count) in enumerate(users, 1)]
                embed.description = "\n".join(lines)
            await interaction.response.send_message(embed=embed)

    async def cog_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        msg = str(error)
        if interaction.response.is_done():
            await interaction.followup.send(f"⚠️ {msg}", ephemeral=True)
        else:
            await interaction.response.send_message(f"⚠️ {msg}", ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(StatsCog(bot))
```

- [ ] **Step 4: Registrar el cog en `main.py`**

```python
await bot.load_extension("cogs.stats_cog")
```

- [ ] **Step 5: Verificar compilación**

```bash
python -c "from services.stats import record_play, guild_stats, top_songs, top_users; print('OK')"
python -c "import ast; ast.parse(open('cogs/stats_cog.py').read()); print('OK')"
```

- [ ] **Step 6: Commit**

```bash
git add services/stats.py cogs/stats_cog.py services/music_service.py main.py
git commit -m "feat: stats system with /stats and /top commands"
```

---

## Phase 6 — Panel persistente de música

### Task 6.1 — Guardar panel_message_id y panel_channel_id en guild_config

**Files:**
- Modify: `services/guild_config.py`
- Modify: `cogs/music.py`

- [ ] **Step 1: Agregar helpers para panel en `guild_config.py`**

```python
def panel_ids(guild_id: int) -> tuple[int | None, int | None]:
    """Returns (channel_id, message_id) or (None, None)."""
    cfg = get(guild_id)
    return cfg.get("panel_channel_id"), cfg.get("panel_message_id")


def set_panel(guild_id: int, channel_id: int | None, message_id: int | None) -> None:
    set_value(guild_id, panel_channel_id=channel_id, panel_message_id=message_id)
```

- [ ] **Step 2: Agregar `update_panel` a `MusicService`**

En `services/music_service.py`, agregar método:

```python
async def update_panel(self) -> None:
    """Refresh the persistent music panel if one exists."""
    from services import guild_config
    from ui.player_view import NowPlayingView, build_now_playing_embed

    channel_id, message_id = guild_config.panel_ids(self.guild.id)
    if not channel_id or not message_id:
        return

    channel = self.guild.get_channel(channel_id)
    if not channel:
        return

    try:
        message = await channel.fetch_message(message_id)
    except discord.NotFound:
        guild_config.set_panel(self.guild.id, None, None)
        return

    if self.current:
        embed = build_now_playing_embed(self.current, self)
        view = NowPlayingView(self)
        await message.edit(embed=embed, view=view)
    else:
        embed = discord.Embed(
            title="🎵 Panel de Música",
            description="Sin reproducción activa.",
            color=discord.Color.greyple(),
        )
        await message.edit(embed=embed, view=None)
```

- [ ] **Step 3: Llamar a `update_panel` en `on_track_start`**

Modificar `_send_now_playing` en `cogs/music.py` para también actualizar el panel:

```python
async def _send_now_playing(self, service: MusicService, track: Track) -> None:
    if service.text_channel:
        embed = build_now_playing_embed(track, service)
        view = NowPlayingView(service)
        await service.text_channel.send(embed=embed, view=view)
    await service.update_panel()
```

- [ ] **Step 4: Agregar comando `/musicpanel` como grupo**

En `cogs/music.py`, agregar el grupo de comandos dentro de `MusicCog`:

```python
_panel_group = app_commands.Group(name="musicpanel", description="Gestiona el panel persistente de música")

@_panel_group.command(name="create", description="Crea el panel persistente de música en este canal")
async def musicpanel_create(self, interaction: discord.Interaction) -> None:
    perms.check(interaction, "musicpanel")
    service = self._get_service(interaction)
    embed = build_now_playing_embed(service.current, service) if service.current else discord.Embed(
        title="🎵 Panel de Música",
        description="Sin reproducción activa.",
        color=discord.Color.greyple(),
    )
    view = NowPlayingView(service) if service.current else None
    await interaction.response.send_message("📌 Panel creado.", ephemeral=True)
    msg = await interaction.channel.send(embed=embed, view=view)
    guild_config.set_panel(interaction.guild_id, interaction.channel_id, msg.id)

@_panel_group.command(name="delete", description="Elimina el panel persistente de música")
async def musicpanel_delete(self, interaction: discord.Interaction) -> None:
    perms.check(interaction, "musicpanel")
    channel_id, message_id = guild_config.panel_ids(interaction.guild_id)
    if not channel_id or not message_id:
        return await interaction.response.send_message("No hay panel activo.", ephemeral=True)
    channel = interaction.guild.get_channel(channel_id)
    if channel:
        try:
            msg = await channel.fetch_message(message_id)
            await msg.delete()
        except discord.NotFound:
            pass
    guild_config.set_panel(interaction.guild_id, None, None)
    await interaction.response.send_message("🗑️ Panel eliminado.", ephemeral=True)

@_panel_group.command(name="refresh", description="Actualiza manualmente el panel")
async def musicpanel_refresh(self, interaction: discord.Interaction) -> None:
    perms.check(interaction, "musicpanel")
    service = self._get_service(interaction)
    await service.update_panel()
    await interaction.response.send_message("✅ Panel actualizado.", ephemeral=True)
```

Registrar el grupo en `MusicCog.__init__` o con `bot.tree.add_command`. En discord.py 2.x con Cog, usar:

```python
# Al final de la clase MusicCog, antes de setup()
# El grupo debe agregarse al árbol desde setup():
```

```python
async def setup(bot: commands.Bot) -> None:
    cog = MusicCog(bot)
    await bot.add_cog(cog)
    bot.tree.add_command(cog._panel_group)
```

- [ ] **Step 5: Importar guild_config en `services/music_service.py`**

Asegurarse de que el import lazy en `update_panel` evita circular imports. Verificar:

```bash
python -c "from services.music_service import MusicService; print('OK')"
```

- [ ] **Step 6: Verificar compilación completa**

```bash
python -c "import ast; ast.parse(open('cogs/music.py').read()); print('OK')"
python -c "import ast; ast.parse(open('services/music_service.py').read()); print('OK')"
python -c "import ast; ast.parse(open('services/guild_config.py').read()); print('OK')"
```

- [ ] **Step 7: Commit**

```bash
git add services/guild_config.py services/music_service.py cogs/music.py
git commit -m "feat: persistent music panel with /musicpanel create/delete/refresh"
```

---

## Phase 7 — UX improvements

### Task 7.1 — Helper `safe_reply` y errores consistentes

**Files:**
- Create: `ui/embeds.py`
- Modify: `cogs/music.py`
- Modify: `cogs/config_cog.py`
- Modify: `cogs/favorites_cog.py`
- Modify: `cogs/stats_cog.py`

- [ ] **Step 1: Crear `ui/embeds.py`**

```python
# ui/embeds.py
import discord


def error_embed(msg: str) -> discord.Embed:
    return discord.Embed(description=f"⚠️ {msg}", color=discord.Color.red())


def success_embed(msg: str) -> discord.Embed:
    return discord.Embed(description=f"✅ {msg}", color=discord.Color.green())


def info_embed(msg: str) -> discord.Embed:
    return discord.Embed(description=msg, color=discord.Color.blurple())


async def safe_reply(
    interaction: discord.Interaction,
    content: str | None = None,
    *,
    embed: discord.Embed | None = None,
    ephemeral: bool = False,
    view: discord.ui.View | None = None,
) -> None:
    """Send reply regardless of whether the interaction was deferred or not."""
    kwargs: dict = {}
    if content:
        kwargs["content"] = content
    if embed:
        kwargs["embed"] = embed
    if view:
        kwargs["view"] = view
    kwargs["ephemeral"] = ephemeral

    if interaction.response.is_done():
        await interaction.followup.send(**kwargs)
    else:
        await interaction.response.send_message(**kwargs)
```

- [ ] **Step 2: Reemplazar manejo de errores en todos los cogs**

En cada `cog_app_command_error` de todos los cogs, usar `error_embed`:

```python
async def cog_app_command_error(
    self, interaction: discord.Interaction, error: app_commands.AppCommandError
) -> None:
    from ui.embeds import error_embed, safe_reply
    await safe_reply(interaction, embed=error_embed(str(error)), ephemeral=True)
```

- [ ] **Step 3: Verificar compilación**

```bash
python -c "from ui.embeds import error_embed, success_embed, info_embed, safe_reply; print('OK')"
```

- [ ] **Step 4: Commit**

```bash
git add ui/embeds.py cogs/music.py cogs/config_cog.py cogs/favorites_cog.py cogs/stats_cog.py
git commit -m "feat: consistent embed helpers and safe_reply utility"
```

---

## Phase 8 — Tests

### Task 8.1 — Setup pytest y tests unitarios de servicios

**Files:**
- Create: `tests/__init__.py`
- Create: `tests/test_music_service.py`
- Create: `tests/test_vote_manager.py`
- Create: `tests/test_parse_time.py`
- Create: `tests/test_guild_config.py`
- Create: `tests/test_stats.py`
- Create: `pyproject.toml` (si no existe)

- [ ] **Step 1: Instalar pytest**

```bash
pip install pytest pytest-asyncio
```

- [ ] **Step 2: Crear `pyproject.toml`**

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

- [ ] **Step 3: Crear `tests/__init__.py`** (vacío)

- [ ] **Step 4: Crear `tests/test_parse_time.py`**

```python
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from cogs.music import _parse_time


def test_parse_seconds():
    assert _parse_time("90") == 90


def test_parse_mm_ss():
    assert _parse_time("1:30") == 90


def test_parse_hh_mm_ss():
    assert _parse_time("1:01:30") == 3690


def test_parse_invalid():
    assert _parse_time("abc") is None


def test_parse_empty():
    assert _parse_time("") is None
```

- [ ] **Step 5: Ejecutar y verificar**

```bash
cd /home/fran/Documentos/Coding/chatbot_disc && python -m pytest tests/test_parse_time.py -v
```

Expected: 5 tests passing

- [ ] **Step 6: Crear `tests/test_vote_manager.py`**

```python
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from services.vote_manager import VoteManager


def test_single_vote_passes_when_majority():
    vm = VoteManager(threshold=0.5, min_votes=1)
    votes, required, passed = vm.add(user_id=1, total_listeners=1)
    assert passed is True
    assert votes == 1
    assert required == 1


def test_needs_majority():
    vm = VoteManager(threshold=0.5, min_votes=1)
    votes, required, passed = vm.add(user_id=1, total_listeners=4)
    assert passed is False
    assert required == 2

    votes, required, passed = vm.add(user_id=2, total_listeners=4)
    assert passed is True


def test_reset():
    vm = VoteManager(threshold=0.5, min_votes=1)
    vm.add(user_id=1, total_listeners=2)
    vm.reset()
    assert not vm.has_voted(1)


def test_duplicate_vote_still_counts_once():
    vm = VoteManager(threshold=0.5, min_votes=1)
    vm.add(user_id=1, total_listeners=4)
    votes, _, _ = vm.add(user_id=1, total_listeners=4)
    assert votes == 1
```

- [ ] **Step 7: Ejecutar y verificar**

```bash
python -m pytest tests/test_vote_manager.py -v
```

Expected: 4 tests passing

- [ ] **Step 8: Crear `tests/test_guild_config.py`**

```python
import sys, os, json, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import services.guild_config as gc


def test_get_returns_defaults(tmp_path, monkeypatch):
    monkeypatch.setattr(gc, "_DATA_FILE", tmp_path / "guild_config.json")
    cfg = gc.get(123)
    assert cfg == {}


def test_set_and_get(tmp_path, monkeypatch):
    monkeypatch.setattr(gc, "_DATA_FILE", tmp_path / "guild_config.json")
    gc.set_value(123, dj_role=456)
    cfg = gc.get(123)
    assert cfg["dj_role"] == 456


def test_dj_role_id(tmp_path, monkeypatch):
    monkeypatch.setattr(gc, "_DATA_FILE", tmp_path / "guild_config.json")
    assert gc.dj_role_id(999) is None
    gc.set_value(999, dj_role=111)
    assert gc.dj_role_id(999) == 111
```

- [ ] **Step 9: Ejecutar y verificar**

```bash
python -m pytest tests/test_guild_config.py -v
```

Expected: 3 tests passing

- [ ] **Step 10: Crear `tests/test_stats.py`**

```python
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import services.stats as stats_svc


def test_record_and_retrieve(tmp_path, monkeypatch):
    monkeypatch.setattr(stats_svc, "_DATA_FILE", tmp_path / "stats.json")
    stats_svc.record_play(1, 10, "Song A", "http://a.com")
    stats_svc.record_play(1, 10, "Song A", "http://a.com")
    stats_svc.record_play(1, 20, "Song B", "http://b.com")

    g = stats_svc.guild_stats(1)
    assert g["total"] == 3


def test_top_songs(tmp_path, monkeypatch):
    monkeypatch.setattr(stats_svc, "_DATA_FILE", tmp_path / "stats.json")
    stats_svc.record_play(1, 10, "Song A", "http://a.com")
    stats_svc.record_play(1, 10, "Song A", "http://a.com")
    stats_svc.record_play(1, 20, "Song B", "http://b.com")

    top = stats_svc.top_songs(1)
    assert top[0]["title"] == "Song A"
    assert top[0]["count"] == 2


def test_user_plays(tmp_path, monkeypatch):
    monkeypatch.setattr(stats_svc, "_DATA_FILE", tmp_path / "stats.json")
    stats_svc.record_play(1, 42, "X", "http://x.com")
    assert stats_svc.user_plays(1, 42) == 1
    assert stats_svc.user_plays(1, 99) == 0
```

- [ ] **Step 11: Ejecutar todos los tests**

```bash
python -m pytest tests/ -v
```

Expected: todos pasando

- [ ] **Step 12: Commit**

```bash
git add tests/ pyproject.toml
git commit -m "test: pytest suite for parse_time, VoteManager, guild_config, stats"
```

---

## Verificación final

```bash
# 1. Syntax check de todos los archivos Python
find . -name "*.py" -not -path "./.git/*" | xargs python -m py_compile && echo "All OK"

# 2. Correr todos los tests
python -m pytest tests/ -v

# 3. Levantar el bot
python main.py
```

Smoke test manual:
1. `/play <canción>` → reproduce + panel Now Playing con botones
2. `/filter nightcore` → reinicia con nightcore
3. `/loop song` → la canción se repite
4. `/voteskip` → requiere mayoría de votos
5. `/history` → muestra últimas 20 canciones
6. `/stats server` → muestra total de plays
7. `/top songs` → top 10 canciones
8. `/musicpanel create` → panel fijo en el canal
9. Panel se actualiza solo al cambiar de canción
