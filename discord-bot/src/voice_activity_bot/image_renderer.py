from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
import math

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .database import TopUser
from .time_utils import format_duration


@dataclass(frozen=True)
class BannerData:
    guild_name: str
    active_voice_users: int
    period: str
    top_user: TopUser | None
    top_user_avatar: bytes | None


class BannerRenderer:
    def __init__(
        self,
        *,
        output_path: Path,
        width: int,
        height: int,
        background_path: Path | None = None,
        font_path: Path | None = None,
    ) -> None:
        self.output_path = output_path
        self.width = width
        self.height = height
        self.background_path = background_path
        self.font_path = font_path

    def render(self, data: BannerData) -> Path:
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        image = self._background()
        draw = ImageDraw.Draw(image)

        margin = int(self.width * 0.07)
        top = int(self.height * 0.1)
        title_font = self._font(44, bold=True)
        label_font = self._font(24)
        number_font = self._font(112, bold=True)
        name_font = self._font(34, bold=True)
        stat_font = self._font(28)

        draw.text((margin, top), data.guild_name, font=title_font, fill=(245, 248, 255))
        draw.text((margin, top + 62), "Users currently in voice", font=label_font, fill=(174, 184, 201))
        draw.text((margin, top + 98), str(data.active_voice_users), font=number_font, fill=(255, 255, 255))

        panel_x = int(self.width * 0.48)
        panel_y = int(self.height * 0.22)
        panel_w = self.width - panel_x - margin
        panel_h = int(self.height * 0.55)
        self._rounded_rect(draw, (panel_x, panel_y, panel_x + panel_w, panel_y + panel_h), 28, (22, 28, 41, 216))

        draw.text((panel_x + 34, panel_y + 30), f"Top user: {data.period}", font=label_font, fill=(174, 184, 201))

        if data.top_user is None:
            draw.text((panel_x + 34, panel_y + 88), "No voice activity yet", font=name_font, fill=(245, 248, 255))
        else:
            avatar_size = min(128, max(84, panel_h // 3))
            avatar_x = panel_x + 34
            avatar_y = panel_y + 96
            avatar = self._avatar(data.top_user_avatar, avatar_size)
            image.alpha_composite(avatar, (avatar_x, avatar_y))

            text_x = avatar_x + avatar_size + 28
            text_w = panel_x + panel_w - text_x - 28
            display_name = self._fit_text(draw, data.top_user.display_name, name_font, text_w)
            draw.text((text_x, avatar_y + 18), display_name, font=name_font, fill=(255, 255, 255))
            draw.text(
                (text_x, avatar_y + 68),
                format_duration(data.top_user.total_seconds),
                font=stat_font,
                fill=(88, 196, 220),
            )

        footer = "Live voice activity"
        footer_bbox = draw.textbbox((0, 0), footer, font=label_font)
        draw.text(
            (self.width - margin - (footer_bbox[2] - footer_bbox[0]), self.height - top),
            footer,
            font=label_font,
            fill=(174, 184, 201),
        )

        image.convert("RGB").save(self.output_path, "PNG", optimize=True)
        return self.output_path

    def to_bytes(self, data: BannerData) -> bytes:
        path = self.render(data)
        return path.read_bytes()

    def _background(self) -> Image.Image:
        if self.background_path and self.background_path.exists():
            source = Image.open(self.background_path).convert("RGB")
            source.thumbnail((self.width, self.height), Image.Resampling.LANCZOS)
            background = Image.new("RGB", (self.width, self.height), (12, 16, 24))
            x = (self.width - source.width) // 2
            y = (self.height - source.height) // 2
            background.paste(source, (x, y))
            background = background.resize((self.width, self.height), Image.Resampling.LANCZOS)
            background = background.filter(ImageFilter.GaussianBlur(radius=4))
            overlay = Image.new("RGBA", (self.width, self.height), (7, 10, 18, 152))
            return Image.alpha_composite(background.convert("RGBA"), overlay)

        image = Image.new("RGBA", (self.width, self.height), (10, 14, 23, 255))
        pixels = image.load()
        for y in range(self.height):
            for x in range(self.width):
                nx = x / max(1, self.width - 1)
                ny = y / max(1, self.height - 1)
                wave = int(18 * math.sin((nx * 2.4 + ny) * math.pi))
                red = 12 + int(28 * nx)
                green = 18 + int(30 * ny)
                blue = 34 + int(46 * (1 - nx)) + wave
                pixels[x, y] = (red, green, max(25, blue), 255)
        return image

    def _avatar(self, avatar_bytes: bytes | None, size: int) -> Image.Image:
        if avatar_bytes:
            avatar = Image.open(BytesIO(avatar_bytes)).convert("RGBA").resize((size, size), Image.Resampling.LANCZOS)
        else:
            avatar = Image.new("RGBA", (size, size), (54, 66, 88, 255))
            draw = ImageDraw.Draw(avatar)
            draw.text((size // 2 - 12, size // 2 - 20), "?", font=self._font(46, bold=True), fill=(220, 228, 240))

        mask = Image.new("L", (size, size), 0)
        ImageDraw.Draw(mask).ellipse((0, 0, size - 1, size - 1), fill=255)
        result = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        result.paste(avatar, (0, 0), mask)

        ring = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        ring_draw = ImageDraw.Draw(ring)
        ring_draw.ellipse((1, 1, size - 2, size - 2), outline=(88, 196, 220, 255), width=4)
        return Image.alpha_composite(result, ring)

    def _font(self, size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        candidates = []
        if self.font_path:
            candidates.append(self.font_path)

        candidates.extend(
            [
                Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
                Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf"),
                Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
            ]
        )

        for path in candidates:
            if path.exists():
                return ImageFont.truetype(str(path), size)
        return ImageFont.load_default()

    @staticmethod
    def _rounded_rect(
        draw: ImageDraw.ImageDraw,
        box: tuple[int, int, int, int],
        radius: int,
        fill: tuple[int, int, int, int],
    ) -> None:
        draw.rounded_rectangle(box, radius=radius, fill=fill)

    @staticmethod
    def _fit_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> str:
        if draw.textlength(text, font=font) <= max_width:
            return text

        ellipsis = "..."
        trimmed = text
        while trimmed and draw.textlength(trimmed + ellipsis, font=font) > max_width:
            trimmed = trimmed[:-1]
        return trimmed + ellipsis if trimmed else ellipsis

