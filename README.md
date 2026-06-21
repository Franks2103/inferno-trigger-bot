# Inferno Trigger Bot

A Discord music bot built with discord.py. Plays audio from YouTube, supports playlists, queues, favorites, server stats, and per-server configuration — all through slash commands.

## Features

- **Music** — play, pause, skip, stop, queue management, loop, shuffle, seek, volume control
- **Playlists** — load YouTube playlists (up to 50 tracks)
- **Favorites** — save and load personal song favorites per server
- **Stats** — track per-server listening statistics
- **Config** — per-guild bot configuration with role-based permissions
- **Bandelion AI** — consultas con preferencias privadas por usuario y servidor

## Requirements

- Python 3.10+
- FFmpeg installed and in PATH
- A Discord bot token

## Setup

1. Clone the repo and install dependencies:

```bash
pip install -r requirements.txt
```

2. Create a `.env` file based on `.env.example`:

```env
DISCORD_TOKEN=your_token_here
REDIS_HOST=127.0.0.1
REDIS_PORT=6379
```

`/ia` stores its user memory in Redis. For the local Docker container already
exposed on port `6379`, the sample settings work as-is. Install the updated
requirements before running the bot.

3. Run the bot:

```bash
python main.py
```

## Project Structure

```
main.py              # Entry point, loads cogs
config.py            # Token and yt-dlp/ffmpeg config
cogs/
  music.py           # Music playback commands
  config_cog.py      # Guild configuration commands
  favorites_cog.py   # Favorites management
  stats_cog.py       # Listening stats
services/            # Business logic layer
models/              # Data models
data/                # Persistent data storage
tests/               # Pytest test suite
```

## Permissions

The bot requires the following Discord permissions:
- `Send Messages`, `Embed Links`, `Read Message History`
- `Connect`, `Speak` (voice)
- `Use Application Commands`

## Bandelion AI commands

- `/ia pregunta:<texto>` — asks the assistant using your memory in that server.
- `/ia memory set <texto>` — adds a presentation preference (tone, language or explanation format).
- `/ia memory view` — privately shows your current memory.
- `/ia memory clear` — privately clears only your memory in the current server.
- `/ia memory remove <índice>` — removes one preference shown by `view`.
- `/ia style set <preset>` — `neutral`, `paisa`, `formal`, `técnico`, `corto`, `profesor` or `gamer`.
- `/ia style custom <tono>` — sets a personal tone that takes priority over a preset.
- `/ia style reset` — returns to `neutral`.

## Chatbot por mención

- Escribí `@Bandelion <tu mensaje>` para hablar con el bot. Solo responde a mensajes que lo mencionen.

Al mencionarlo, podés pedir acciones en lenguaje natural, por ejemplo
`pon 5 canciones de salsa`, `salta esta canción`, `activa el DJ con mood lo-fi`
o `qué recomendás según esta canción`. Podés contestar `agregá todas`,
`agregá la 1 y la 3`, `dame otras` o `no me gustaron`. Las acciones de moderación (`ban`, `kick`, `timeout`) se
validan contra los permisos actuales y exigen escribir `CONFIRMO` antes de que
el bot las ejecute.

Los eventos operativos de IA se guardan en `logs/bot.log`. Configurá
`AI_AUDIT_LOG_LEVEL=DEBUG` para más detalle técnico; por privacidad, nunca se
guardan el contenido de mensajes, prompts, memoria ni secretos.

Memory is keyed by both Discord guild ID and user ID. It is only used to adapt
presentation; instructions attempting to alter safety rules or storing sensitive
information are rejected.

## License

MIT
