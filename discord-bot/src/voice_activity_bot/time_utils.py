from __future__ import annotations

from datetime import datetime, timedelta, timezone


def period_start(period: str, now: int) -> int | None:
    current = datetime.fromtimestamp(now, tz=timezone.utc)
    if period == "all":
        return None
    if period == "day":
        start = current.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "week":
        midnight = current.replace(hour=0, minute=0, second=0, microsecond=0)
        start = midnight - timedelta(days=midnight.weekday())
    elif period == "month":
        start = current.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    else:
        raise ValueError(f"Unknown period: {period}")
    return int(start.timestamp())


def format_duration(seconds: int) -> str:
    seconds = max(0, int(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, _ = divmod(remainder, 60)

    if hours >= 24:
        days, day_hours = divmod(hours, 24)
        return f"{days}d {day_hours}h"
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"

