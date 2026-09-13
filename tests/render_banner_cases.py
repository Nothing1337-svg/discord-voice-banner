from __future__ import annotations

from pathlib import Path
import sys

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from discord_voice_banner.banner import BannerOptions, BannerPayload, BannerRenderer
from discord_voice_banner.database import TopChannel, TopUser


OUT_DIR = ROOT / "data" / "test-banners"


def payload(
    *,
    guild_name: str = "Тестовый Discord сервер",
    current_users: int = 0,
    active_channels: int = 0,
    top_user: TopUser | None = None,
    top_channels: list[TopChannel] | None = None,
) -> BannerPayload:
    return BannerPayload(
        guild_name=guild_name,
        current_users=current_users,
        active_channels=active_channels,
        period="all",
        top_user=top_user,
        top_channels=top_channels or [],
        avatar_bytes=None,
        updated_at=1_800_000_000,
    )


def make_custom_background(path: Path) -> None:
    image = Image.new("RGB", (760, 1120), (60, 32, 82))
    pixels = image.load()
    for y in range(image.height):
        for x in range(image.width):
            pixels[x, y] = (40 + x % 80, 26 + y % 70, 92 + (x + y) % 90)
    image.save(path, "PNG")


def render_case(name: str, options: BannerOptions, data: BannerPayload) -> None:
    output = BannerRenderer(options=options).render(data)
    with Image.open(output) as image:
        assert image.size == (1280, 640), f"{output} has invalid size {image.size}"


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    custom = OUT_DIR / "custom-source.png"
    make_custom_background(custom)

    top = TopUser(
        user_id=1,
        display_name="ОченьДлинныйРусскийНикКоторыйДолженАккуратноОбрезаться✨",
        username="username_with_unicode_и_кириллица",
        avatar_url=None,
        total_seconds=456_789,
    )
    channels = [
        TopChannel(channel_id=1, name="Главный голосовой канал с длинным названием", total_seconds=98_765),
        TopChannel(channel_id=2, name="Droom 1", total_seconds=5_432),
        TopChannel(channel_id=3, name="Музыка и разговоры", total_seconds=3_210),
    ]

    cases = [
        (
            "01-empty-ru-standard.png",
            BannerOptions(output_path=OUT_DIR / "01-empty-ru-standard.png", width=1280, height=640, language="ru"),
            payload(),
        ),
        (
            "02-top-ru-standard.png",
            BannerOptions(output_path=OUT_DIR / "02-top-ru-standard.png", width=1280, height=640, language="ru"),
            payload(current_users=1, active_channels=1, top_user=top, top_channels=channels),
        ),
        (
            "03-many-en-custom.png",
            BannerOptions(
                output_path=OUT_DIR / "03-many-en-custom.png",
                width=1280,
                height=640,
                language="en",
                custom_banner_path=custom,
            ),
            payload(guild_name="Long English Guild Name With Unicode ✨", current_users=16, active_channels=4, top_user=top, top_channels=channels),
        ),
        (
            "04-empty-ru-custom.png",
            BannerOptions(
                output_path=OUT_DIR / "04-empty-ru-custom.png",
                width=1280,
                height=640,
                language="ru",
                custom_banner_path=custom,
            ),
            payload(guild_name="Сервер без статистики", current_users=0, active_channels=0),
        ),
    ]

    for name, options, data in cases:
        render_case(name, options, data)
        print(OUT_DIR / name)


if __name__ == "__main__":
    main()

