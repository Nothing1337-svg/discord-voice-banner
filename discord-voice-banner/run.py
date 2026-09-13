from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from bot.banner import BannerPayload, BannerRenderer
from bot.config import ConfigError, load_settings
from bot.database import TopChannel, TopUser, VoiceDatabase
from bot.logging_setup import configure_logging
from bot.main import main as run_main
from bot.utils import utc_now


logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run discord-voice-banner.")
    parser.add_argument("--check", action="store_true", help="Validate configuration and imports without connecting to Discord.")
    parser.add_argument("--render-sample", action="store_true", help="Render a sample banner without connecting to Discord.")
    return parser.parse_args()


async def render_sample() -> None:
    settings = load_settings(validate_secrets=False)
    configure_logging(settings)
    renderer = BannerRenderer(output_path=settings.banner_output_path)
    renderer.render(
        BannerPayload(
            guild_name="Sample Guild",
            current_users=7,
            active_channels=3,
            period=settings.banner_period,
            top_user=TopUser(
                user_id=1,
                display_name="Очень длинный Unicode username для проверки",
                username="sample_user",
                avatar_url=None,
                total_seconds=98765,
            ),
            top_channels=[
                TopChannel(channel_id=10, name="General Voice", total_seconds=54321),
                TopChannel(channel_id=11, name="Gaming", total_seconds=32100),
            ],
            avatar_bytes=b"not an image",
        )
    )
    logger.info("Sample banner rendered to %s.", settings.banner_output_path)


async def check_runtime() -> int:
    try:
        settings = load_settings(validate_secrets=False)
        configure_logging(settings)
        database = VoiceDatabase(settings.project_root / "data" / "check.sqlite3")
        await database.connect()
        now = utc_now()
        await database.upsert_user(
            guild_id=1,
            user_id=2,
            display_name="Check User",
            username="check_user",
            avatar_url=None,
            now=now,
        )
        await database.upsert_channel(guild_id=1, channel_id=3, name="Check Voice", now=now)
        await database.start_session(guild_id=1, user_id=2, channel_id=3, started_at=now - 60)
        await database.end_session(guild_id=1, user_id=2, ended_at=now, reason="check")
        top_user = await database.top_user(guild_id=1, period_start=None, now=now)
        top_channels = await database.top_channels(guild_id=1, period_start=None, now=now)
        await database.close()
        if top_user is None or not top_channels:
            logger.error("Runtime check failed: expected persisted statistics.")
            return 1
        logger.info("Runtime check completed successfully.")
        return 0
    except ConfigError as exc:
        logging.basicConfig(level=logging.INFO)
        logging.getLogger(__name__).critical("%s", exc)
        return 2


def main() -> int:
    args = parse_args()
    if args.render_sample:
        asyncio.run(render_sample())
        return 0
    if args.check:
        return asyncio.run(check_runtime())
    return run_main()


if __name__ == "__main__":
    sys.exit(main())

