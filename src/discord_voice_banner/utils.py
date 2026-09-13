from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import os
import time


def utc_now() -> int:
    return int(time.time())


def ensure_parent_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def parse_bool(value: str | None, *, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def parse_int(value: str | None, *, default: int, minimum: int | None = None) -> int:
    if value is None or value.strip() == "":
        result = default
    else:
        result = int(value.strip())
    if minimum is not None and result < minimum:
        raise ValueError(f"Expected integer >= {minimum}, got {result}.")
    return result


def parse_float(value: str | None, *, default: float, minimum: float | None = None) -> float:
    if value is None or value.strip() == "":
        result = default
    else:
        result = float(value.strip())
    if minimum is not None and result < minimum:
        raise ValueError(f"Expected float >= {minimum}, got {result}.")
    return result


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


def resolve_path(project_root: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else project_root / path


def period_start(period: str, now: int | None = None) -> int | None:
    if period == "all":
        return None

    current = datetime.fromtimestamp(now or utc_now(), tz=timezone.utc)
    if period == "day":
        start = current.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "week":
        midnight = current.replace(hour=0, minute=0, second=0, microsecond=0)
        start = midnight - timedelta(days=midnight.weekday())
    elif period == "month":
        start = current.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    else:
        raise ValueError(f"Unsupported period: {period}")
    return int(start.timestamp())


def format_duration(seconds: int) -> str:
    seconds = max(0, int(seconds))
    days, remainder = divmod(seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, _ = divmod(remainder, 60)

    if days:
        return f"{days}d {hours}h"
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"

