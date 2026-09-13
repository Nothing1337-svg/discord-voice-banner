from __future__ import annotations

import asyncio
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bot.banner import BannerPayload, BannerRenderer
from bot.database import TopChannel, TopUser, VoiceDatabase
from bot.voice_tracker import VoiceTracker, count_active_voice_channels, count_human_voice_members
from bot.utils import utc_now


class FakeAvatar:
    url = "https://example.invalid/avatar.png"


class FakeGuild:
    def __init__(self) -> None:
        self.id = 100
        self.name = "Fake Guild"
        self.voice_channels: list[FakeChannel] = []
        self.stage_channels: list[FakeChannel] = []


class FakeChannel:
    def __init__(self, channel_id: int, name: str) -> None:
        self.id = channel_id
        self.name = name
        self.members: list[FakeMember] = []


class FakeMember:
    def __init__(self, guild: FakeGuild, user_id: int, name: str, *, bot: bool = False) -> None:
        self.guild = guild
        self.id = user_id
        self.name = name
        self.display_name = name
        self.bot = bot
        self.display_avatar = FakeAvatar()


async def check_database() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        database = VoiceDatabase(Path(tmpdir) / "voice.sqlite3")
        await database.connect()
        now = utc_now()
        await database.upsert_user(
            guild_id=100,
            user_id=200,
            display_name="Unicode Пользователь",
            username="unicode_user",
            avatar_url=None,
            now=now,
        )
        await database.upsert_channel(guild_id=100, channel_id=300, name="Voice Канал", now=now)
        await database.start_session(guild_id=100, user_id=200, channel_id=300, started_at=now - 120)
        await database.end_session(guild_id=100, user_id=200, ended_at=now, reason="smoke")
        top_user = await database.top_user(guild_id=100, period_start=None, now=now)
        top_channels = await database.top_channels(guild_id=100, period_start=None, now=now)
        await database.close()

    assert top_user is not None
    assert top_user.total_seconds == 120
    assert top_channels
    assert top_channels[0].total_seconds == 120


def check_banner() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        output = Path(tmpdir) / "banner.png"
        renderer = BannerRenderer(output_path=output)
        renderer.render(
            BannerPayload(
                guild_name="Smoke Test Guild",
                current_users=5,
                active_channels=2,
                period="all",
                top_user=TopUser(
                    user_id=200,
                    display_name="Очень длинный Discord display name",
                    username="unicode_user",
                    avatar_url=None,
                    total_seconds=120,
                ),
                top_channels=[TopChannel(channel_id=300, name="Voice Канал", total_seconds=120)],
                avatar_bytes=b"broken avatar bytes",
            )
        )
        assert output.exists()
        assert output.stat().st_size > 0


async def check_voice_tracker() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        database = VoiceDatabase(Path(tmpdir) / "tracker.sqlite3")
        await database.connect()
        try:
            tracker = VoiceTracker(database=database, guild_id=100, period="all")
            guild = FakeGuild()
            channel = FakeChannel(300, "Voice Канал")
            guild.voice_channels.append(channel)
            member = FakeMember(guild, 200, "Real User")
            bot_member = FakeMember(guild, 201, "Bot User", bot=True)

            await tracker.handle_voice_state_update(member, None, channel)
            await tracker.handle_voice_state_update(bot_member, None, channel)
            await database.db.execute(
                "UPDATE active_sessions SET started_at = ? WHERE guild_id = ? AND user_id = ?",
                (utc_now() - 90, 100, 200),
            )
            await database.db.commit()
            channel.members = [member, bot_member]

            assert count_human_voice_members(guild) == 1
            assert count_active_voice_channels(guild) == 1

            snapshot = await tracker.snapshot(guild)
            assert snapshot.current_users == 1
            assert snapshot.active_channels == 1
            assert snapshot.top_user is not None

            await tracker.handle_voice_state_update(member, channel, None)
        finally:
            await database.close()


async def main() -> None:
    await check_database()
    await check_voice_tracker()
    check_banner()
    print("smoke ok")


if __name__ == "__main__":
    asyncio.run(main())
