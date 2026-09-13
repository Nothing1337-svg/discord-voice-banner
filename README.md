# discord-voice-banner

Stable Discord bot that tracks voice-channel activity and generates a dynamic statistics banner.

The bot stores voice activity in SQLite, ignores bot accounts, survives restarts, and can either save the generated banner locally or apply it as the Discord server banner when permissions and server features allow it.

## Features

- tracks all voice and stage channels in one guild;
- counts real users currently connected to voice;
- stores completed and active voice sessions in SQLite;
- restores active sessions after restart by reconciling with the current guild state;
- calculates the most active user for `day`, `week`, `month`, or `all`;
- renders a PNG banner with current user count, active channel count, top user, avatar fallback, and top channels;
- handles missing avatars, invalid avatar bytes, long names, and Unicode text;
- rate-limit friendly banner updates with cooldown and periodic refresh;
- structured logs and graceful shutdown.

## Project Structure

```text
discord-voice-banner/
  bot/
    main.py
    config.py
    database.py
    voice_tracker.py
    banner.py
    tasks.py
    utils.py
  assets/
  data/
  tests/
    smoke_test.py
  .env.example
  .gitignore
  requirements.txt
  README.md
  run.py
```

## Requirements

- Python 3.11+
- Discord bot token
- Bot invited to the target server
- Server Members Intent enabled in the Discord Developer Portal
- Voice state events enabled by using `Intents.voice_states`
- `Manage Server` permission only if `APPLY_GUILD_BANNER=true`
- A server tier/feature set that supports guild banners if you want automatic server banner updates

## Installation

```bash
cd discord-voice-banner
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Fill `.env`:

```env
DISCORD_TOKEN=your-discord-bot-token
GUILD_ID=123456789012345678
APPLY_GUILD_BANNER=false
BANNER_PERIOD=all
```

Do not commit `.env`. It is ignored by Git.

## Discord Application Setup

1. Create an application in the Discord Developer Portal.
2. Add a bot to the application.
3. Copy the bot token into `.env` as `DISCORD_TOKEN`.
4. Enable required intents:
   - Server Members Intent
   - Voice States intent/events
5. Invite the bot to your server.
6. If you want the bot to update the server banner, grant `Manage Server` and set `APPLY_GUILD_BANNER=true`.

If `APPLY_GUILD_BANNER=false`, the bot still renders the banner to `data/current-banner.png`.

## Run

```bash
source .venv/bin/activate
python run.py
```

Configuration check without connecting to Discord:

```bash
python run.py --check
```

Render a sample banner without connecting to Discord:

```bash
python run.py --render-sample
```

Smoke test:

```bash
python tests/smoke_test.py
```

## Environment Variables

| Variable | Required | Default | Description |
| --- | --- | --- | --- |
| `DISCORD_TOKEN` | yes | empty | Discord bot token. |
| `GUILD_ID` | yes | `0` | Target Discord server ID. |
| `APPLY_GUILD_BANNER` | no | `false` | If true, call Discord API to update the server banner. |
| `BANNER_PERIOD` | no | `all` | `day`, `week`, `month`, or `all`. |
| `UPDATE_INTERVAL_SECONDS` | no | `300` | Periodic banner refresh interval. Minimum `30`. |
| `BANNER_UPDATE_COOLDOWN_SECONDS` | no | `20` | Debounce after voice events. Minimum `2`. |
| `DATABASE_PATH` | no | `data/voice_banner.sqlite3` | SQLite database path. |
| `BANNER_OUTPUT_PATH` | no | `data/current-banner.png` | Generated banner path. |
| `LOG_LEVEL` | no | `INFO` | Python logging level. |
| `LOG_FILE` | no | `logs/bot.log` | Log file path. Empty disables file logging. |

## Diagnostics

Common startup problems:

- `Missing required environment variable(s): DISCORD_TOKEN, GUILD_ID` - create `.env` from `.env.example`.
- `Discord rejected the token` - the token is invalid or was regenerated.
- `PrivilegedIntentsRequired` - enable the required intents in the Discord Developer Portal.
- `Configured guild ... is not visible` - the bot is not in the server or `GUILD_ID` is wrong.
- `Discord Forbidden while updating guild banner` - disable `APPLY_GUILD_BANNER` or grant `Manage Server`.
- `database locked` - stop duplicate bot processes using the same SQLite file.

Logs are written to stdout and to `logs/bot.log` by default.

