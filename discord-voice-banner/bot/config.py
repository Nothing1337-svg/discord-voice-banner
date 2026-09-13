from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os

from .utils import load_dotenv, parse_bool, parse_float, parse_int, resolve_path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
VALID_PERIODS = {"day", "week", "month", "all"}


class ConfigError(RuntimeError):
    """Raised when required runtime configuration is missing or invalid."""


@dataclass(frozen=True)
class Settings:
    project_root: Path
    discord_token: str
    guild_id: int
    apply_guild_banner: bool
    banner_period: str
    update_interval_seconds: float
    banner_update_cooldown_seconds: float
    database_path: Path
    banner_output_path: Path
    log_level: str
    log_file: Path | None


def load_settings(*, validate_secrets: bool = True, env_file: Path | None = None) -> Settings:
    env_path = env_file or PROJECT_ROOT / ".env"
    load_dotenv(env_path)

    token = os.getenv("DISCORD_TOKEN", "").strip()
    try:
        guild_id = parse_int(os.getenv("GUILD_ID"), default=0, minimum=0)
    except ValueError as exc:
        raise ConfigError(f"GUILD_ID must be a positive integer: {exc}") from exc

    period = os.getenv("BANNER_PERIOD", "all").strip().lower()
    if period not in VALID_PERIODS:
        raise ConfigError(f"BANNER_PERIOD must be one of: {', '.join(sorted(VALID_PERIODS))}.")

    if validate_secrets:
        missing = []
        if not token:
            missing.append("DISCORD_TOKEN")
        if guild_id <= 0:
            missing.append("GUILD_ID")
        if missing:
            raise ConfigError(
                "Missing required environment variable(s): "
                + ", ".join(missing)
                + ". Copy .env.example to .env and fill real values."
            )

    database_path = resolve_path(PROJECT_ROOT, os.getenv("DATABASE_PATH", "data/voice_banner.sqlite3"))
    banner_output_path = resolve_path(PROJECT_ROOT, os.getenv("BANNER_OUTPUT_PATH", "data/current-banner.png"))
    log_file_raw = os.getenv("LOG_FILE", "logs/bot.log").strip()
    log_file = resolve_path(PROJECT_ROOT, log_file_raw) if log_file_raw else None

    try:
        return Settings(
            project_root=PROJECT_ROOT,
            discord_token=token,
            guild_id=guild_id,
            apply_guild_banner=parse_bool(os.getenv("APPLY_GUILD_BANNER"), default=False),
            banner_period=period,
            update_interval_seconds=parse_float(os.getenv("UPDATE_INTERVAL_SECONDS"), default=300.0, minimum=30.0),
            banner_update_cooldown_seconds=parse_float(
                os.getenv("BANNER_UPDATE_COOLDOWN_SECONDS"),
                default=20.0,
                minimum=2.0,
            ),
            database_path=database_path,
            banner_output_path=banner_output_path,
            log_level=os.getenv("LOG_LEVEL", "INFO").strip().upper(),
            log_file=log_file,
        )
    except ValueError as exc:
        raise ConfigError(f"Invalid environment configuration: {exc}") from exc
