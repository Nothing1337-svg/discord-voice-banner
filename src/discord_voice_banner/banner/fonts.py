from __future__ import annotations

from pathlib import Path
import logging

from PIL import ImageFont


logger = logging.getLogger(__name__)


class FontManager:
    def __init__(self, *, regular_path: Path | None = None, bold_path: Path | None = None) -> None:
        self.regular_path = self._select_font(regular_path, bold=False)
        self.bold_path = self._select_font(bold_path, bold=True)
        self._cache: dict[tuple[int, bool], ImageFont.ImageFont] = {}

    def font(self, size: int, *, bold: bool = False) -> ImageFont.ImageFont:
        key = (size, bold)
        if key in self._cache:
            return self._cache[key]

        path = self.bold_path if bold else self.regular_path
        try:
            font = ImageFont.truetype(str(path), size)
            self._cache[key] = font
            return font
        except OSError as exc:
            logger.error("Configured font could not be loaded: %s (%s)", path, exc)
            raise RuntimeError(f"Font could not be loaded: {path}") from exc

    def _select_font(self, configured: Path | None, *, bold: bool) -> Path:
        candidates: list[Path] = []
        if configured is not None:
            candidates.append(configured)

        candidates.extend(default_font_candidates(bold=bold))

        for path in candidates:
            if not path.exists():
                continue
            try:
                ImageFont.truetype(str(path), 24)
                logger.info("Using %s font: %s", "bold" if bold else "regular", path)
                return path
            except OSError:
                logger.warning("Font exists but could not be loaded: %s", path)

        raise RuntimeError(
            "No TrueType font with Unicode/Cyrillic support was found. "
            "Set FONT_PATH and FONT_BOLD_PATH in .env."
        )


def default_font_candidates(*, bold: bool) -> list[Path]:
    names = (
        ["DejaVuSans-Bold.ttf", "Arial Bold.ttf", "Arial Unicode Bold.ttf", "seguiemj.ttf", "arialbd.ttf"]
        if bold
        else ["DejaVuSans.ttf", "Arial.ttf", "Arial Unicode.ttf", "seguiemj.ttf", "arial.ttf"]
    )
    bases = [
        Path("assets/fonts"),
        Path("/usr/share/fonts/truetype/dejavu"),
        Path("/usr/local/share/fonts"),
        Path("/System/Library/Fonts/Supplemental"),
        Path("/Library/Fonts"),
        Path("C:/Windows/Fonts"),
    ]
    return [base / name for base in bases for name in names]

