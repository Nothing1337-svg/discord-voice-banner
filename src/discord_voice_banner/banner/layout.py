from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Rect:
    x: int
    y: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.x + self.width

    @property
    def bottom(self) -> int:
        return self.y + self.height

    def inset(self, value: int) -> Rect:
        return Rect(self.x + value, self.y + value, self.width - value * 2, self.height - value * 2)

    def intersects(self, other: Rect) -> bool:
        return self.x < other.right and self.right > other.x and self.y < other.bottom and self.bottom > other.y


@dataclass(frozen=True)
class BannerLayout:
    canvas: Rect
    safe_area: Rect
    header: Rect
    stats: Rect
    top_user_panel: Rect
    channels_panel: Rect
    footer: Rect
    padding: int
    gap: int

    def validate(self) -> None:
        for name, rect in {
            "safe_area": self.safe_area,
            "header": self.header,
            "stats": self.stats,
            "top_user_panel": self.top_user_panel,
            "channels_panel": self.channels_panel,
            "footer": self.footer,
        }.items():
            if rect.x < self.canvas.x or rect.y < self.canvas.y or rect.right > self.canvas.right or rect.bottom > self.canvas.bottom:
                raise ValueError(f"{name} is outside canvas: {rect}")
            if rect.x < self.safe_area.x or rect.right > self.safe_area.right:
                raise ValueError(f"{name} is outside horizontal safe area: {rect}")

        overlaps = [
            ("header", self.header, "top_user_panel", self.top_user_panel),
            ("stats", self.stats, "top_user_panel", self.top_user_panel),
            ("stats", self.stats, "channels_panel", self.channels_panel),
            ("top_user_panel", self.top_user_panel, "channels_panel", self.channels_panel),
            ("channels_panel", self.channels_panel, "footer", self.footer),
        ]
        for left_name, left, right_name, right in overlaps:
            if left.intersects(right):
                raise ValueError(f"{left_name} overlaps {right_name}: {left} / {right}")


def build_layout(width: int, height: int) -> BannerLayout:
    canvas = Rect(0, 0, width, height)
    margin_x = max(50, int(width * 0.044))
    margin_top = max(44, int(height * 0.075))
    margin_bottom = max(40, int(height * 0.069))
    safe_area = Rect(margin_x, margin_top, width - margin_x * 2, height - margin_top - margin_bottom)
    gap = max(28, int(width * 0.024))
    padding = max(28, int(width * 0.026))

    left_width = int((safe_area.width - gap) * 0.49)
    right_width = safe_area.width - gap - left_width
    right_x = safe_area.x + left_width + gap

    header = Rect(safe_area.x, safe_area.y, left_width, 92)
    stats = Rect(safe_area.x, header.bottom + 26, left_width, 154)
    top_user_panel = Rect(right_x, safe_area.y, right_width, 300)

    footer_height = 28
    footer = Rect(right_x, safe_area.bottom - footer_height, right_width, footer_height)
    channels_top = max(stats.bottom + 38, top_user_panel.bottom + 30)
    channels_height = footer.y - channels_top - 22
    channels_panel = Rect(safe_area.x, channels_top, min(int(width * 0.58), safe_area.width - 260), channels_height)

    layout = BannerLayout(
        canvas=canvas,
        safe_area=safe_area,
        header=header,
        stats=stats,
        top_user_panel=top_user_panel,
        channels_panel=channels_panel,
        footer=footer,
        padding=padding,
        gap=gap,
    )
    layout.validate()
    return layout
