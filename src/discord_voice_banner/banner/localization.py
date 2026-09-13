from __future__ import annotations

import json
import logging
from pathlib import Path


logger = logging.getLogger(__name__)


class Localizer:
    def __init__(self, language: str, locales_dir: Path) -> None:
        self.language = language if language in {"ru", "en"} else "en"
        if self.language != language:
            logger.warning("Unsupported language %s; falling back to en.", language)
        self._strings = self._load(locales_dir / f"{self.language}.json")

    def t(self, key: str) -> str:
        return str(self._strings.get(key, key))

    def period(self, period: str) -> str:
        return self.t(f"period_{period}")

    def duration(self, seconds: int) -> str:
        seconds = max(0, int(seconds))
        days, remainder = divmod(seconds, 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, _ = divmod(remainder, 60)
        if days:
            return f"{days}{self.t('day_short')} {hours}{self.t('hour_short')}"
        if hours:
            return f"{hours}{self.t('hour_short')} {minutes}{self.t('minute_short')}"
        return f"{minutes}{self.t('minute_short')}"

    @staticmethod
    def _load(path: Path) -> dict[str, str]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            logger.info("Loaded localization file: %s", path)
            return {str(key): str(value) for key, value in data.items()}
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Localization file could not be loaded (%s): %s", path, exc)
            return {}
