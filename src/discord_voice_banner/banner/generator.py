from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
import logging
import math

from PIL import Image, ImageDraw, ImageFilter, ImageFont, UnidentifiedImageError

from ..database import TopChannel, TopUser
from ..utils import ensure_parent_dir, utc_now
from .fonts import FontManager
from .layout import Rect, build_layout
from .localization import Localizer
from .utils import draw_text_fit, ellipsize, load_custom_background


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BannerOptions:
    output_path: Path
    width: int = 1280
    height: int = 640
    language: str = "ru"
    custom_banner_path: Path | None = None
    font_path: Path | None = None
    font_bold_path: Path | None = None
    overlay_opacity: int = 142


@dataclass(frozen=True)
class BannerPayload:
    guild_name: str
    current_users: int
    active_channels: int
    period: str
    top_user: TopUser | None
    top_channels: list[TopChannel]
    avatar_bytes: bytes | None = None
    updated_at: int | None = None


class BannerRenderer:
    def __init__(
        self,
        *,
        output_path: Path | None = None,
        width: int = 1280,
        height: int = 640,
        options: BannerOptions | None = None,
        custom_banner_path: Path | None = None,
        language: str = "ru",
        font_path: Path | None = None,
        font_bold_path: Path | None = None,
    ) -> None:
        if options is None:
            if output_path is None:
                raise ValueError("output_path is required when options is not provided.")
            options = BannerOptions(
                output_path=output_path,
                width=width,
                height=height,
                language=language,
                custom_banner_path=custom_banner_path,
                font_path=font_path,
                font_bold_path=font_bold_path,
            )

        self.options = options
        self.output_path = options.output_path
        self.width = options.width
        self.height = options.height
        locales_dir = Path(__file__).resolve().parents[1] / "locales"
        self.localizer = Localizer(options.language, locales_dir)
        self.fonts = FontManager(regular_path=options.font_path, bold_path=options.font_bold_path)

    def render(self, payload: BannerPayload) -> Path:
        ensure_parent_dir(self.output_path)
        image = self._background()
        draw = ImageDraw.Draw(image)
        layout = build_layout(self.width, self.height)

        self._draw_header(draw, layout.header, payload)
        self._draw_stat(draw, layout.left_stat, self.localizer.t("users_in_voice"), str(payload.current_users))
        self._draw_stat(draw, layout.right_stat, self.localizer.t("active_channels"), str(payload.active_channels))
        self._draw_top_user(image, draw, layout.top_user_panel, payload)
        self._draw_top_channels(draw, layout.channels_panel, payload)
        self._draw_footer(draw, layout.footer, payload.updated_at or utc_now())

        self._save(image)
        logger.info("Banner image rendered: %s", self.output_path)
        return self.output_path

    def _background(self) -> Image.Image:
        custom = load_custom_background(self.options.custom_banner_path, width=self.width, height=self.height)
        if custom is not None:
            overlay = Image.new("RGBA", (self.width, self.height), (5, 8, 15, self.options.overlay_opacity))
            return Image.alpha_composite(custom.filter(ImageFilter.GaussianBlur(radius=0.2)), overlay)

        image = Image.new("RGBA", (self.width, self.height), (9, 13, 23, 255))
        pixels = image.load()
        for y in range(self.height):
            ny = y / max(1, self.height - 1)
            for x in range(self.width):
                nx = x / max(1, self.width - 1)
                wave = int(18 * math.sin((nx * 2.3 + ny * 1.1) * math.pi))
                red = 13 + int(35 * nx)
                green = 18 + int(46 * ny)
                blue = 38 + int(58 * (1 - nx * 0.42)) + wave
                pixels[x, y] = (red, green, max(28, blue), 255)
        return image

    def _draw_header(self, draw: ImageDraw.ImageDraw, rect: Rect, payload: BannerPayload) -> None:
        draw_text_fit(
            draw,
            (rect.x, rect.y),
            self.localizer.t("project_title"),
            font_factory=self.fonts.font,
            initial_size=max(42, int(self.height * 0.075)),
            min_size=28,
            max_width=rect.width,
            fill=(250, 252, 255),
            bold=True,
        )
        draw_text_fit(
            draw,
            (rect.x, rect.y + int(rect.height * 0.54)),
            payload.guild_name,
            font_factory=self.fonts.font,
            initial_size=max(24, int(self.height * 0.04)),
            min_size=18,
            max_width=rect.width,
            fill=(197, 207, 222),
            bold=False,
        )

    def _draw_stat(self, draw: ImageDraw.ImageDraw, rect: Rect, label: str, value: str) -> None:
        draw_text_fit(
            draw,
            (rect.x, rect.y),
            label,
            font_factory=self.fonts.font,
            initial_size=max(23, int(self.height * 0.04)),
            min_size=16,
            max_width=rect.width,
            fill=(197, 207, 222),
        )
        draw_text_fit(
            draw,
            (rect.x, rect.y + int(rect.height * 0.25)),
            value,
            font_factory=self.fonts.font,
            initial_size=max(74, int(self.height * 0.13)),
            min_size=44,
            max_width=rect.width,
            fill=(255, 255, 255),
            bold=True,
        )

    def _draw_top_user(self, image: Image.Image, draw: ImageDraw.ImageDraw, rect: Rect, payload: BannerPayload) -> None:
        self._panel(draw, rect)
        period_label = self.localizer.period(payload.period)
        title = f"{self.localizer.t('top_user')} · {period_label}"
        draw_text_fit(
            draw,
            (rect.x + 34, rect.y + 28),
            title,
            font_factory=self.fonts.font,
            initial_size=28,
            min_size=18,
            max_width=rect.width - 68,
            fill=(197, 207, 222),
            bold=True,
        )

        avatar_size = min(148, max(104, int(rect.height * 0.38)))
        avatar_x = rect.x + 36
        avatar_y = rect.y + 100

        if payload.top_user is None:
            draw_text_fit(
                draw,
                (avatar_x, avatar_y),
                self.localizer.t("no_activity"),
                font_factory=self.fonts.font,
                initial_size=38,
                min_size=22,
                max_width=rect.width - 72,
                fill=(255, 255, 255),
                bold=True,
            )
            draw_text_fit(
                draw,
                (avatar_x, avatar_y + 54),
                self.localizer.t("waiting_for_sessions"),
                font_factory=self.fonts.font,
                initial_size=23,
                min_size=16,
                max_width=rect.width - 72,
                fill=(160, 174, 194),
            )
            return

        avatar = self._avatar(payload.avatar_bytes, avatar_size)
        image.alpha_composite(avatar, (avatar_x, avatar_y))

        text_x = avatar_x + avatar_size + 34
        text_width = rect.right - text_x - 36
        display_name = payload.top_user.display_name or self.localizer.t("unknown_user")
        username = payload.top_user.username or self.localizer.t("unknown_user")

        draw_text_fit(
            draw,
            (text_x, avatar_y + 10),
            display_name,
            font_factory=self.fonts.font,
            initial_size=40,
            min_size=22,
            max_width=text_width,
            fill=(255, 255, 255),
            bold=True,
        )
        draw_text_fit(
            draw,
            (text_x, avatar_y + 62),
            username,
            font_factory=self.fonts.font,
            initial_size=23,
            min_size=16,
            max_width=text_width,
            fill=(160, 174, 194),
        )
        draw_text_fit(
            draw,
            (text_x, avatar_y + 105),
            f"{self.localizer.t('time_in_voice')}: {self.localizer.duration(payload.top_user.total_seconds)}",
            font_factory=self.fonts.font,
            initial_size=30,
            min_size=18,
            max_width=text_width,
            fill=(91, 226, 205),
            bold=True,
        )

    def _draw_top_channels(self, draw: ImageDraw.ImageDraw, rect: Rect, payload: BannerPayload) -> None:
        self._panel(draw, rect)
        x = rect.x + 30
        y = rect.y + 24
        draw_text_fit(
            draw,
            (x, y),
            self.localizer.t("top_channels"),
            font_factory=self.fonts.font,
            initial_size=29,
            min_size=20,
            max_width=rect.width - 60,
            fill=(197, 207, 222),
            bold=True,
        )

        y += 54
        row_gap = max(35, int(rect.height * 0.17))
        if not payload.top_channels:
            draw_text_fit(
                draw,
                (x, y),
                self.localizer.t("no_channel_stats"),
                font_factory=self.fonts.font,
                initial_size=23,
                min_size=16,
                max_width=rect.width - 60,
                fill=(160, 174, 194),
            )
            return

        rank_width = 42
        time_width = 138
        name_width = rect.width - 60 - rank_width - time_width
        for index, channel in enumerate(payload.top_channels[:3], start=1):
            if y + 30 > rect.bottom - 16:
                break
            channel_name = channel.name or self.localizer.t("unknown_channel")
            rank_font = self.fonts.font(22, bold=True)
            row_font = self.fonts.font(23, bold=True)
            time_font = self.fonts.font(22)
            draw.text((x, y), f"{index}.", fill=(91, 226, 205), font=rank_font)
            draw.text((x + rank_width, y), ellipsize(draw, channel_name, row_font, name_width), fill=(255, 255, 255), font=row_font)
            draw.text((rect.right - 30 - time_width, y), self.localizer.duration(channel.total_seconds), fill=(197, 207, 222), font=time_font)
            y += row_gap

    def _draw_footer(self, draw: ImageDraw.ImageDraw, rect: Rect, updated_at: int) -> None:
        timestamp = datetime.fromtimestamp(updated_at, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        text = f"{self.localizer.t('last_updated')}: {timestamp}"
        footer_font = self.fonts.font(22)
        fitted = ellipsize(draw, text, footer_font, rect.width)
        text_width = draw.textlength(fitted, font=footer_font)
        draw.text((rect.right - int(text_width), rect.y), fitted, fill=(160, 174, 194), font=footer_font)

    def _avatar(self, avatar_bytes: bytes | None, size: int) -> Image.Image:
        try:
            if avatar_bytes:
                source = Image.open(BytesIO(avatar_bytes)).convert("RGBA")
                source = source.resize((size, size), Image.Resampling.LANCZOS)
            else:
                source = self._fallback_avatar(size)
        except (OSError, UnidentifiedImageError) as exc:
            logger.warning("Avatar image could not be decoded; using fallback: %s", exc)
            source = self._fallback_avatar(size)

        mask = Image.new("L", (size, size), 0)
        ImageDraw.Draw(mask).ellipse((0, 0, size - 1, size - 1), fill=255)
        result = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        result.paste(source, (0, 0), mask)

        ring = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        ImageDraw.Draw(ring).ellipse((2, 2, size - 3, size - 3), outline=(91, 226, 205, 255), width=5)
        return Image.alpha_composite(result, ring)

    def _fallback_avatar(self, size: int) -> Image.Image:
        image = Image.new("RGBA", (size, size), (41, 55, 78, 255))
        draw = ImageDraw.Draw(image)
        font = self.fonts.font(max(42, size // 3), bold=True)
        text = "?"
        bbox = draw.textbbox((0, 0), text, font=font)
        draw.text(
            ((size - (bbox[2] - bbox[0])) / 2, (size - (bbox[3] - bbox[1])) / 2 - 4),
            text,
            fill=(220, 228, 240),
            font=font,
        )
        return image

    @staticmethod
    def _panel(draw: ImageDraw.ImageDraw, rect: Rect) -> None:
        draw.rounded_rectangle(
            (rect.x, rect.y, rect.right, rect.bottom),
            radius=28,
            fill=(11, 17, 29, 215),
            outline=(95, 116, 148, 120),
            width=1,
        )

    def _save(self, image: Image.Image) -> None:
        suffix = self.output_path.suffix.lower()
        try:
            if suffix in {".jpg", ".jpeg"}:
                image.convert("RGB").save(self.output_path, "JPEG", quality=94, optimize=True)
            else:
                image.convert("RGB").save(self.output_path, "PNG", optimize=True)
        except OSError:
            logger.exception("Banner image could not be saved: %s", self.output_path)
            raise
