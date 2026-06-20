# Inferno Trigger Bot

A Discord music bot built with discord.py. Plays audio from YouTube, supports playlists, queues, favorites, server stats, and per-server configuration — all through slash commands.

## Features

- **Music** — play, pause, skip, stop, queue management, loop, shuffle, seek, volume control
- **Playlists** — load YouTube playlists (up to 50 tracks)
- **Favorites** — save and load personal song favorites per server
- **Stats** — track per-server listening statistics
- **Config** — per-guild bot configuration with role-based permissions

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
```

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

## License

MIT
