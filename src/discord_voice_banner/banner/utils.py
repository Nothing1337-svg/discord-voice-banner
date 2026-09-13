from __future__ import annotations

from pathlib import Path
import logging

from PIL import Image, ImageDraw, ImageFont, UnidentifiedImageError


logger = logging.getLogger(__name__)
SUPPORTED_BACKGROUND_SUFFIXES = {".png", ".jpg", ".jpeg"}


def cover_image(source: Image.Image, width: int, height: int) -> Image.Image:
    source_ratio = source.width / source.height
    target_ratio = width / height

    if source_ratio > target_ratio:
        new_height = height
        new_width = int(height * source_ratio)
    else:
        new_width = width
        new_height = int(width / source_ratio)

    resized = source.resize((new_width, new_height), Image.Resampling.LANCZOS)
    left = max(0, (new_width - width) // 2)
    top = max(0, (new_height - height) // 2)
    return resized.crop((left, top, left + width, top + height)).convert("RGBA")


def load_custom_background(path: Path | None, *, width: int, height: int) -> Image.Image | None:
    if path is None:
        logger.info("Custom banner path is not configured; using generated background.")
        return None

    if not path.exists():
        logger.info("Custom banner does not exist: %s; using generated background.", path)
        return None

    if path.suffix.lower() not in SUPPORTED_BACKGROUND_SUFFIXES:
        logger.warning("Unsupported custom banner format %s for %s; using generated background.", path.suffix, path)
        return None

    try:
        with Image.open(path) as probe:
            probe.verify()
        with Image.open(path) as image:
            if image.width < 64 or image.height < 64:
                logger.warning("Custom banner is too small (%sx%s): %s.", image.width, image.height, path)
                return None
            logger.info("Loaded custom banner background: %s (%sx%s).", path, image.width, image.height)
            return cover_image(image.convert("RGBA"), width, height)
    except (OSError, UnidentifiedImageError) as exc:
        logger.warning("Custom banner could not be loaded (%s): %s. Using generated background.", path, exc)
        return None


def draw_text_fit(
    draw: ImageDraw.ImageDraw,
    position: tuple[int, int],
    text: str,
    *,
    font_factory,
    initial_size: int,
    min_size: int,
    max_width: int,
    fill: tuple[int, int, int] | tuple[int, int, int, int],
    bold: bool = False,
    shadow: bool = True,
) -> ImageFont.ImageFont:
    clean = text or ""
    font = font_factory(initial_size, bold=bold)
    size = initial_size
    while size > min_size and draw.textlength(clean, font=font) > max_width:
        size -= 1
        font = font_factory(size, bold=bold)

    fitted = ellipsize(draw, clean, font, max_width)
    if shadow:
        draw.text((position[0] + 2, position[1] + 2), fitted, font=font, fill=(0, 0, 0, 155))
    draw.text(position, fitted, font=font, fill=fill)
    return font


def ellipsize(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> str:
    clean = text or ""
    if draw.textlength(clean, font=font) <= max_width:
        return clean
    suffix = "..."
    while clean and draw.textlength(clean + suffix, font=font) > max_width:
        clean = clean[:-1]
    return clean + suffix if clean else suffix
