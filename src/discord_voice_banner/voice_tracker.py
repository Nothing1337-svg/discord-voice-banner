from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any

import discord

from .database import TopChannel, TopUser, VoiceDatabase
from .utils import period_start, utc_now


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class VoicePresence:
    member: discord.Member
    channel: discord.abc.GuildChannel


@dataclass(frozen=True)
class VoiceSnapshot:
    guild_name: str
    current_users: int
    active_channels: int
    top_user: TopUser | None
    top_channels: list[TopChannel]
    period: str


class VoiceTracker:
    def __init__(self, *, database: VoiceDatabase, guild_id: int, period: str) -> None:
        self.database = database
        self.guild_id = guild_id
        self.period = period

    async def sync_from_guild(self, guild: discord.Guild) -> None:
        now = utc_now()
        current = human_voice_members(guild)
        stored = await self.database.active_sessions(guild.id)
        stored_user_ids = {session.user_id for session in stored}
        current_user_ids = set(current)

        for user_id, presence in current.items():
            await self._upsert_member(presence.member, now=now)
            await self._upsert_channel(presence.channel, guild.id, now=now)
            if user_id in stored_user_ids:
                await self.database.move_session(guild_id=guild.id, user_id=user_id, channel_id=presence.channel.id)
            else:
                await self.database.start_session(
                    guild_id=guild.id,
                    user_id=user_id,
                    channel_id=presence.channel.id,
                    started_at=now,
                )
                logger.info("Recovered active voice session for user_id=%s channel_id=%s.", user_id, presence.channel.id)

        for session in stored:
            if session.user_id not in current_user_ids:
                await self.database.end_session(
                    guild_id=guild.id,
                    user_id=session.user_id,
                    ended_at=now,
                    reason="startup_reconcile",
                )
                logger.info("Closed stale active session for user_id=%s during startup reconcile.", session.user_id)

        logger.info(
            "Voice sync complete: %s active user(s), %s active channel(s).",
            len(current_user_ids),
            count_active_voice_channels(guild),
        )

    async def handle_voice_state_update(
        self,
        member: discord.Member,
        before_channel: discord.abc.GuildChannel | None,
        after_channel: discord.abc.GuildChannel | None,
    ) -> bool:
        if member.bot:
            return False
        if member.guild.id != self.guild_id:
            return False
        if before_channel == after_channel:
            return False

        now = utc_now()
        await self._upsert_member(member, now=now)
        if after_channel is not None:
            await self._upsert_channel(after_channel, member.guild.id, now=now)
        if before_channel is not None:
            await self._upsert_channel(before_channel, member.guild.id, now=now)

        if before_channel is None and after_channel is not None:
            await self.database.start_session(
                guild_id=member.guild.id,
                user_id=member.id,
                channel_id=after_channel.id,
                started_at=now,
            )
            logger.info("Voice join: user=%s channel=%s.", member_display(member), channel_display(after_channel))
            return True

        if before_channel is not None and after_channel is None:
            closed = await self.database.end_session(
                guild_id=member.guild.id,
                user_id=member.id,
                ended_at=now,
                reason="leave",
            )
            if closed is None:
                logger.warning("Voice leave without active session: user_id=%s.", member.id)
            else:
                logger.info("Voice leave: user=%s channel=%s.", member_display(member), channel_display(before_channel))
            return True

        if before_channel is not None and after_channel is not None:
            moved = await self.database.move_session(
                guild_id=member.guild.id,
                user_id=member.id,
                channel_id=after_channel.id,
            )
            if not moved:
                await self.database.start_session(
                    guild_id=member.guild.id,
                    user_id=member.id,
                    channel_id=after_channel.id,
                    started_at=now,
                )
                logger.warning("Voice move recreated missing session: user_id=%s.", member.id)
            logger.info(
                "Voice move: user=%s from=%s to=%s.",
                member_display(member),
                channel_display(before_channel),
                channel_display(after_channel),
            )
            return True

        return False

    async def snapshot(self, guild: discord.Guild) -> VoiceSnapshot:
        now = utc_now()
        start = period_start(self.period, now)
        return VoiceSnapshot(
            guild_name=guild.name,
            current_users=count_human_voice_members(guild),
            active_channels=count_active_voice_channels(guild),
            top_user=await self.database.top_user(guild_id=guild.id, period_start=start, now=now),
            top_channels=await self.database.top_channels(guild_id=guild.id, period_start=start, now=now, limit=3),
            period=self.period,
        )

    async def _upsert_member(self, member: discord.Member, *, now: int) -> None:
        avatar_url = str(member.display_avatar.url) if getattr(member, "display_avatar", None) else None
        await self.database.upsert_user(
            guild_id=member.guild.id,
            user_id=member.id,
            display_name=member.display_name or member.name or str(member.id),
            username=member.name or str(member.id),
            avatar_url=avatar_url,
            now=now,
        )

    async def _upsert_channel(self, channel: discord.abc.GuildChannel, guild_id: int, *, now: int) -> None:
        await self.database.upsert_channel(
            guild_id=guild_id,
            channel_id=channel.id,
            name=getattr(channel, "name", str(channel.id)),
            now=now,
        )


def human_voice_members(guild: discord.Guild) -> dict[int, VoicePresence]:
    presences: dict[int, VoicePresence] = {}
    for channel in voice_channels(guild):
        for member in getattr(channel, "members", []):
            if not getattr(member, "bot", False):
                presences[member.id] = VoicePresence(member=member, channel=channel)
    return presences


def count_human_voice_members(guild: discord.Guild) -> int:
    return len(human_voice_members(guild))


def count_active_voice_channels(guild: discord.Guild) -> int:
    total = 0
    for channel in voice_channels(guild):
        if any(not getattr(member, "bot", False) for member in getattr(channel, "members", [])):
            total += 1
    return total


def voice_channels(guild: discord.Guild) -> list[Any]:
    return list(getattr(guild, "voice_channels", [])) + list(getattr(guild, "stage_channels", []))


def member_display(member: discord.Member) -> str:
    return f"{member.display_name} ({member.id})"


def channel_display(channel: discord.abc.GuildChannel) -> str:
    return f"{getattr(channel, 'name', channel.id)} ({channel.id})"

