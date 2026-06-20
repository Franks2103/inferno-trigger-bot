# Repository Guidelines

## Project Structure & Module Organization

This is a Python Discord music bot. `main.py` creates the bot and loads extensions; `config.py` reads environment configuration and defines yt-dlp/FFmpeg options. Keep Discord slash-command handlers in `cogs/`, reusable business logic and persistence in `services/`, data classes in `models/`, and embeds/views in `ui/`. Place pytest files in `tests/` using the `test_*.py` pattern. Runtime JSON data belongs in the ignored `data/` directory; do not commit generated state.

## Build, Test, and Development Commands

Use Python 3.10 or later and ensure FFmpeg is available on `PATH`.

```bash
pip install -r requirements.txt  # install bot and test dependencies
cp .env.example .env             # create local configuration
python main.py                   # run the bot
pytest                           # run the complete test suite
pytest tests/test_stats.py       # run one test module
```

Set `DISCORD_TOKEN` in `.env`. Never add tokens, guild data, or other secrets to source control.

## Coding Style & Naming Conventions

Use four-space indentation, standard Python import grouping, and type annotations where they clarify public APIs or asynchronous boundaries. Use `snake_case` for modules, functions, variables, and slash-command callbacks; use `PascalCase` for classes (for example, `VoteManager`); use `UPPER_SNAKE_CASE` for configuration constants. Keep cog handlers thin: put shared state, file I/O, and domain behavior in `services/`. Match the existing direct pytest assertion style rather than adding unnecessary test classes.

## Testing Guidelines

Tests use pytest with `asyncio_mode = "auto"`; test discovery is limited to `tests/`. Add focused regression tests for changes to services, parsing, permissions, or persistent configuration. Name tests for observable behavior, such as `test_duplicate_vote_counts_once`. Discord-heavy imports may need lightweight mocks, following `tests/test_parse_time.py`, so tests remain runnable without live Discord credentials.

## Commit & Pull Request Guidelines

Use the existing conventional prefixes: `feat:`, `fix:`, `test:`, `docs:`, `refactor:`, and `chore:`. Write imperative, scoped summaries, e.g. `fix: reject favorites outside configured channel`. Keep commits cohesive. Pull requests should explain the user-visible change, list verification performed (`pytest` output), link the relevant issue when applicable, and include screenshots or Discord output for UI/embed changes.
