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


@dataclass(frozen=True)
class BannerLayout:
    margin: int
    header: Rect
    left_stat: Rect
    right_stat: Rect
    top_user_panel: Rect
    channels_panel: Rect
    footer: Rect


def build_layout(width: int, height: int) -> BannerLayout:
    margin = max(42, int(width * 0.055))
    gutter = max(24, int(width * 0.025))
    header = Rect(margin, margin - 8, int(width * 0.48), 110)
    stat_width = int(width * 0.2)
    left_stat = Rect(margin, header.bottom + 26, stat_width, 150)
    right_stat = Rect(left_stat.right + gutter, header.bottom + 26, stat_width, 150)
    top_user_panel = Rect(int(width * 0.52), margin, width - int(width * 0.52) - margin, int(height * 0.46))
    channels_panel = Rect(margin, int(height * 0.58), int(width * 0.55), height - int(height * 0.58) - margin)
    footer = Rect(int(width * 0.52), height - margin - 34, width - int(width * 0.52) - margin, 34)
    return BannerLayout(
        margin=margin,
        header=header,
        left_stat=left_stat,
        right_stat=right_stat,
        top_user_panel=top_user_panel,
        channels_panel=channels_panel,
        footer=footer,
    )

