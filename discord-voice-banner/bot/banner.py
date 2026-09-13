from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
import logging
import math

from PIL import Image, ImageDraw, ImageFont, UnidentifiedImageError

from .database import TopChannel, TopUser
from .utils import ensure_parent_dir, format_duration


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BannerPayload:
    guild_name: str
    current_users: int
    active_channels: int
    period: str
    top_user: TopUser | None
    top_channels: list[TopChannel]
    avatar_bytes: bytes | None = None


class BannerRenderer:
    def __init__(self, *, output_path: Path, width: int = 960, height: int = 540) -> None:
        self.output_path = output_path
        self.width = width
        self.height = height

    def render(self, payload: BannerPayload) -> Path:
        ensure_parent_dir(self.output_path)
        image = self._background()
        draw = ImageDraw.Draw(image)

        margin = 56
        title_font = self._font(42, bold=True)
        label_font = self._font(22)
        big_font = self._font(76, bold=True)
        name_font = self._font(31, bold=True)
        value_font = self._font(28, bold=True)
        small_font = self._font(19)

        draw.text((margin, 42), "discord-voice-banner", fill=(250, 252, 255), font=title_font)
        draw.text((margin, 96), self._fit_text(draw, payload.guild_name, label_font, 390), fill=(185, 197, 214), font=label_font)

        self._stat_block(draw, x=margin, y=150, label="Users in voice", value=str(payload.current_users), value_font=big_font)
        self._stat_block(draw, x=margin + 230, y=150, label="Active channels", value=str(payload.active_channels), value_font=big_font)

        panel = (510, 78, 910, 356)
        draw.rounded_rectangle(panel, radius=24, fill=(18, 24, 36, 224), outline=(74, 94, 122, 130), width=1)
        draw.text((panel[0] + 28, panel[1] + 24), f"Top user - {payload.period}", fill=(185, 197, 214), font=label_font)

        if payload.top_user is None:
            draw.text((panel[0] + 28, panel[1] + 95), "No activity yet", fill=(250, 252, 255), font=name_font)
            draw.text((panel[0] + 28, panel[1] + 140), "Waiting for voice sessions", fill=(150, 164, 184), font=small_font)
        else:
            avatar = self._avatar(payload.avatar_bytes, 112)
            image.alpha_composite(avatar, (panel[0] + 28, panel[1] + 92))
            text_x = panel[0] + 164
            display_name = self._fit_text(draw, payload.top_user.display_name, name_font, 205)
            username = self._fit_text(draw, payload.top_user.username, small_font, 205)
            draw.text((text_x, panel[1] + 100), display_name, fill=(250, 252, 255), font=name_font)
            draw.text((text_x, panel[1] + 142), username, fill=(150, 164, 184), font=small_font)
            draw.text(
                (text_x, panel[1] + 178),
                format_duration(payload.top_user.total_seconds),
                fill=(80, 207, 187),
                font=value_font,
            )

        draw.text((margin, 350), "Top voice channels", fill=(185, 197, 214), font=label_font)
        if payload.top_channels:
            y = 388
            for index, channel in enumerate(payload.top_channels, start=1):
                name = self._fit_text(draw, channel.name, small_font, 360)
                draw.text((margin, y), f"{index}. {name}", fill=(250, 252, 255), font=small_font)
                draw.text((margin + 390, y), format_duration(channel.total_seconds), fill=(80, 207, 187), font=small_font)
                y += 34
        else:
            draw.text((margin, 388), "No channel statistics yet", fill=(150, 164, 184), font=small_font)

        footer = "Live voice activity"
        footer_width = draw.textlength(footer, font=small_font)
        draw.text((self.width - margin - footer_width, self.height - 46), footer, fill=(150, 164, 184), font=small_font)

        image.convert("RGB").save(self.output_path, "PNG", optimize=True)
        logger.info("Banner image rendered: %s", self.output_path)
        return self.output_path

    def _background(self) -> Image.Image:
        image = Image.new("RGBA", (self.width, self.height), (9, 13, 23, 255))
        pixels = image.load()
        for y in range(self.height):
            ny = y / max(1, self.height - 1)
            for x in range(self.width):
                nx = x / max(1, self.width - 1)
                wave = int(12 * math.sin((nx * 3.2 + ny * 1.8) * math.pi))
                red = 11 + int(24 * nx)
                green = 17 + int(40 * ny)
                blue = 32 + int(48 * (1 - nx * 0.55)) + wave
                pixels[x, y] = (red, green, max(25, blue), 255)
        return image

    def _avatar(self, avatar_bytes: bytes | None, size: int) -> Image.Image:
        try:
            if avatar_bytes:
                source = Image.open(BytesIO(avatar_bytes)).convert("RGBA")
                source = source.resize((size, size), Image.Resampling.LANCZOS)
            else:
                source = self._fallback_avatar(size)
        except (OSError, UnidentifiedImageError) as exc:
            logger.warning("Avatar image could not be decoded, using fallback: %s", exc)
            source = self._fallback_avatar(size)

        mask = Image.new("L", (size, size), 0)
        ImageDraw.Draw(mask).ellipse((0, 0, size - 1, size - 1), fill=255)
        result = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        result.paste(source, (0, 0), mask)
        ring = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        ImageDraw.Draw(ring).ellipse((2, 2, size - 3, size - 3), outline=(80, 207, 187, 255), width=4)
        return Image.alpha_composite(result, ring)

    def _fallback_avatar(self, size: int) -> Image.Image:
        image = Image.new("RGBA", (size, size), (44, 57, 78, 255))
        draw = ImageDraw.Draw(image)
        font = self._font(max(32, size // 3), bold=True)
        text = "?"
        bbox = draw.textbbox((0, 0), text, font=font)
        draw.text(
            ((size - (bbox[2] - bbox[0])) / 2, (size - (bbox[3] - bbox[1])) / 2 - 4),
            text,
            fill=(220, 228, 240),
            font=font,
        )
        return image

    def _stat_block(self, draw: ImageDraw.ImageDraw, *, x: int, y: int, label: str, value: str, value_font: ImageFont.ImageFont) -> None:
        label_font = self._font(21)
        draw.text((x, y), label, fill=(185, 197, 214), font=label_font)
        draw.text((x, y + 34), value, fill=(250, 252, 255), font=value_font)

    def _font(self, size: int, *, bold: bool = False) -> ImageFont.ImageFont:
        candidates = [
            Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
            Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
            Path("/Library/Fonts/Arial Unicode.ttf"),
        ]
        for path in candidates:
            if path.exists():
                try:
                    return ImageFont.truetype(str(path), size)
                except OSError:
                    logger.warning("Font exists but could not be loaded: %s", path)
        return ImageFont.load_default()

    @staticmethod
    def _fit_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> str:
        clean = text or "Unknown"
        if draw.textlength(clean, font=font) <= max_width:
            return clean
        suffix = "..."
        while clean and draw.textlength(clean + suffix, font=font) > max_width:
            clean = clean[:-1]
        return clean + suffix if clean else suffix

