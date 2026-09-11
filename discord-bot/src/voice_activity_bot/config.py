from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import tomllib


VALID_PERIODS = {"day", "week", "month", "all"}
VALID_BANNER_MODES = {"file", "guild"}


@dataclass(frozen=True)
class DiscordConfig:
    token: str
    guild_id: int


@dataclass(frozen=True)
class BotConfig:
    command_prefix: str
    log_level: str
    update_debounce_seconds: float


@dataclass(frozen=True)
class DatabaseConfig:
    path: Path


@dataclass(frozen=True)
class BannerConfig:
    mode: str
    output_path: Path
    background_path: Path | None
    font_path: Path | None
    period: str
    width: int
    height: int


@dataclass(frozen=True)
class AppConfig:
    discord: DiscordConfig
    bot: BotConfig
    database: DatabaseConfig
    banner: BannerConfig
    root_dir: Path


def load_config(path: str | Path = "config.toml") -> AppConfig:
    root_dir = Path.cwd()
    config_path = Path(path)
    if not config_path.is_absolute():
        config_path = root_dir / config_path

    load_dotenv(root_dir / ".env")

    if not config_path.exists():
        raise FileNotFoundError(
            f"Config file not found: {config_path}. Copy config.example.toml to config.toml."
        )

    with config_path.open("rb") as file:
        raw = tomllib.load(file)

    discord_raw = raw.get("discord", {})
    bot_raw = raw.get("bot", {})
    database_raw = raw.get("database", {})
    banner_raw = raw.get("banner", {})

    token = os.getenv("DISCORD_TOKEN") or str(discord_raw.get("token", "")).strip()
    if not token:
        raise ValueError("Discord token is empty. Set DISCORD_TOKEN in .env or discord.token in config.toml.")

    guild_id = int(discord_raw.get("guild_id", 0))
    if guild_id <= 0:
        raise ValueError("discord.guild_id must be set to your Discord server ID.")

    mode = str(banner_raw.get("mode", "file")).lower()
    if mode not in VALID_BANNER_MODES:
        raise ValueError(f"banner.mode must be one of: {', '.join(sorted(VALID_BANNER_MODES))}.")

    period = str(banner_raw.get("period", "week")).lower()
    if period not in VALID_PERIODS:
        raise ValueError(f"banner.period must be one of: {', '.join(sorted(VALID_PERIODS))}.")

    return AppConfig(
        discord=DiscordConfig(token=token, guild_id=guild_id),
        bot=BotConfig(
            command_prefix=str(bot_raw.get("command_prefix", "!")),
            log_level=str(bot_raw.get("log_level", "INFO")).upper(),
            update_debounce_seconds=float(bot_raw.get("update_debounce_seconds", 5)),
        ),
        database=DatabaseConfig(path=resolve_path(root_dir, database_raw.get("path", "data/voice_activity.sqlite3"))),
        banner=BannerConfig(
            mode=mode,
            output_path=resolve_path(root_dir, banner_raw.get("output_path", "data/current_banner.png")),
            background_path=optional_path(root_dir, banner_raw.get("background_path", "")),
            font_path=optional_path(root_dir, banner_raw.get("font_path", "")),
            period=period,
            width=int(banner_raw.get("width", 960)),
            height=int(banner_raw.get("height", 540)),
        ),
        root_dir=root_dir,
    )


def resolve_path(root_dir: Path, value: object) -> Path:
    path = Path(str(value))
    return path if path.is_absolute() else root_dir / path


def optional_path(root_dir: Path, value: object) -> Path | None:
    if not value:
        return None
    path = resolve_path(root_dir, value)
    return path if str(path).strip() else None


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)

