from __future__ import annotations

import asyncio
import logging
from pathlib import Path
import sys

import discord
from discord import app_commands
from discord.ext import commands

from .config import AppConfig, load_config
from .database import TopUser, VoiceActivityStore, utc_now
from .image_renderer import BannerData, BannerRenderer
from .time_utils import format_duration, period_start


logger = logging.getLogger(__name__)


class VoiceActivityBot(commands.Bot):
    def __init__(self, config: AppConfig) -> None:
        intents = discord.Intents.default()
        intents.guilds = True
        intents.members = True
        intents.voice_states = True

        super().__init__(
            command_prefix=config.bot.command_prefix,
            intents=intents,
            help_command=None,
        )

        self.config = config
        self.store = VoiceActivityStore(config.database.path)
        self.renderer = BannerRenderer(
            output_path=config.banner.output_path,
            width=config.banner.width,
            height=config.banner.height,
            background_path=config.banner.background_path,
            font_path=config.banner.font_path,
        )
        self._ready_once = False
        self._banner_update_lock = asyncio.Lock()
        self._banner_update_task: asyncio.Task[None] | None = None
        self._last_banner_request = 0.0
        self._register_app_commands()
        self.tree.on_error = self.on_app_command_error

    async def setup_hook(self) -> None:
        await self.store.connect()
        guild_object = discord.Object(id=self.config.discord.guild_id)
        self.tree.copy_global_to(guild=guild_object)
        await self.tree.sync(guild=guild_object)
        logger.info("Slash commands synced for guild %s.", self.config.discord.guild_id)

    async def close(self) -> None:
        if self._banner_update_task is not None and not self._banner_update_task.done():
            self._banner_update_task.cancel()
            try:
                await self._banner_update_task
            except asyncio.CancelledError:
                pass
        await self.store.close()
        await super().close()

    async def on_ready(self) -> None:
        logger.info("Logged in as %s (%s).", self.user, self.user.id if self.user else "unknown")
        guild = self._target_guild()
        if guild is None:
            logger.error("Guild %s is not available to the bot.", self.config.discord.guild_id)
            return

        if not self._ready_once:
            await self._sync_active_voice_sessions(guild)
            await self.update_banner(guild)
            self._ready_once = True

    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        if member.bot or member.guild.id != self.config.discord.guild_id:
            return

        before_channel = before.channel
        after_channel = after.channel
        if before_channel == after_channel:
            return

        try:
            now = utc_now()
            avatar_url = str(member.display_avatar.url) if member.display_avatar else None
            await self.store.upsert_user(
                guild_id=member.guild.id,
                user_id=member.id,
                display_name=member.display_name,
                avatar_url=avatar_url,
                now=now,
            )

            if before_channel is None and after_channel is not None:
                await self.store.start_session(
                    guild_id=member.guild.id,
                    user_id=member.id,
                    channel_id=after_channel.id,
                    started_at=now,
                )
                logger.info("%s joined voice channel %s.", member, after_channel)
            elif before_channel is not None and after_channel is None:
                closed = await self.store.close_session(
                    guild_id=member.guild.id,
                    user_id=member.id,
                    ended_at=now,
                )
                if closed is None:
                    logger.warning("No active session found for %s while leaving voice.", member)
                logger.info("%s left voice channel %s.", member, before_channel)
            elif after_channel is not None:
                updated = await self.store.update_session_channel(
                    guild_id=member.guild.id,
                    user_id=member.id,
                    channel_id=after_channel.id,
                )
                if not updated:
                    await self.store.start_session(
                        guild_id=member.guild.id,
                        user_id=member.id,
                        channel_id=after_channel.id,
                        started_at=now,
                    )
                logger.info("%s moved from %s to %s.", member, before_channel, after_channel)

            self.request_banner_update()
        except Exception:
            logger.exception("Failed to process voice-state update for member %s.", member.id)

    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError) -> None:
        logger.exception("Prefix command error: %s", error)
        if ctx.channel:
            await ctx.reply("Command failed. Check bot logs for details.", mention_author=False)

    async def on_app_command_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        logger.exception("Slash command error: %s", error)
        message = "Command failed. Check bot logs for details."
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)

    def request_banner_update(self) -> None:
        self._last_banner_request = asyncio.get_running_loop().time()
        if self._banner_update_task is None or self._banner_update_task.done():
            self._banner_update_task = asyncio.create_task(self._debounced_banner_update())

    async def _debounced_banner_update(self) -> None:
        debounce = max(0.0, self.config.bot.update_debounce_seconds)
        while True:
            await asyncio.sleep(debounce)
            elapsed = asyncio.get_running_loop().time() - self._last_banner_request
            if elapsed >= debounce:
                break

        guild = self._target_guild()
        if guild is None:
            logger.warning("Cannot update banner: target guild is unavailable.")
            return
        await self.update_banner(guild)

    async def update_banner(self, guild: discord.Guild) -> Path:
        async with self._banner_update_lock:
            data = await self._banner_data(guild, self.config.banner.period)
            output_path = self.renderer.render(data)
            logger.info("Voice activity banner rendered: %s", output_path)

            if self.config.banner.mode == "guild":
                try:
                    await guild.edit(
                        banner=output_path.read_bytes(),
                        reason="Voice activity banner auto-update",
                    )
                    logger.info("Discord guild banner updated.")
                except discord.Forbidden:
                    logger.exception("Missing permissions to update the guild banner.")
                except discord.HTTPException:
                    logger.exception("Discord rejected guild banner update.")

            return output_path

    async def _banner_data(self, guild: discord.Guild, period: str) -> BannerData:
        now = utc_now()
        top_user = await self.store.get_top_user(
            guild_id=guild.id,
            period_start=period_start(period, now),
            now=now,
        )
        return BannerData(
            guild_name=guild.name,
            active_voice_users=count_human_voice_members(guild),
            period=period,
            top_user=top_user,
            top_user_avatar=await self._top_user_avatar(guild, top_user),
        )

    async def _top_user_avatar(self, guild: discord.Guild, top_user: TopUser | None) -> bytes | None:
        if top_user is None:
            return None

        member = guild.get_member(top_user.user_id)
        if member is None:
            try:
                member = await guild.fetch_member(top_user.user_id)
            except discord.HTTPException:
                logger.info("Could not fetch top user %s for avatar.", top_user.user_id)
                return None

        try:
            return await member.display_avatar.read()
        except discord.HTTPException:
            logger.info("Could not download avatar for user %s.", top_user.user_id)
            return None

    async def _sync_active_voice_sessions(self, guild: discord.Guild) -> None:
        logger.info("Synchronizing active voice sessions for guild %s.", guild.id)
        now = utc_now()
        current_members = current_human_voice_members(guild)
        active_sessions = await self.store.get_active_sessions(guild.id)
        active_user_ids = {session.user_id for session in active_sessions}
        current_user_ids = set(current_members)

        for user_id, member_channel in current_members.items():
            member, channel = member_channel
            avatar_url = str(member.display_avatar.url) if member.display_avatar else None
            await self.store.upsert_user(
                guild_id=guild.id,
                user_id=member.id,
                display_name=member.display_name,
                avatar_url=avatar_url,
                now=now,
            )
            if user_id not in active_user_ids:
                await self.store.start_session(
                    guild_id=guild.id,
                    user_id=member.id,
                    channel_id=channel.id,
                    started_at=now,
                )
                logger.info("Started recovered voice session for %s.", member)
            else:
                await self.store.update_session_channel(
                    guild_id=guild.id,
                    user_id=member.id,
                    channel_id=channel.id,
                )

        for session in active_sessions:
            if session.user_id not in current_user_ids:
                await self.store.close_session(
                    guild_id=guild.id,
                    user_id=session.user_id,
                    ended_at=now,
                )
                logger.info("Closed stale voice session for user %s.", session.user_id)

    def _target_guild(self) -> discord.Guild | None:
        return self.get_guild(self.config.discord.guild_id)

    def _register_app_commands(self) -> None:
        @app_commands.command(name="voice_top", description="Show the most active voice user.")
        @app_commands.describe(period="Period to calculate: day, week, month, or all.")
        @app_commands.choices(
            period=[
                app_commands.Choice(name="day", value="day"),
                app_commands.Choice(name="week", value="week"),
                app_commands.Choice(name="month", value="month"),
                app_commands.Choice(name="all", value="all"),
            ]
        )
        async def voice_top(
            interaction: discord.Interaction,
            period: str = self.config.banner.period,
        ) -> None:
            if interaction.guild_id != self.config.discord.guild_id or interaction.guild is None:
                await interaction.response.send_message("This command is not available here.", ephemeral=True)
                return

            now = utc_now()
            top_user = await self.store.get_top_user(
                guild_id=interaction.guild_id,
                period_start=period_start(period, now),
                now=now,
            )
            if top_user is None:
                await interaction.response.send_message("No voice activity for this period yet.", ephemeral=True)
                return

            await interaction.response.send_message(
                f"Top voice user for `{period}`: **{top_user.display_name}** - {format_duration(top_user.total_seconds)}."
            )

        @app_commands.command(name="voice_banner", description="Send the current voice activity banner.")
        async def voice_banner(interaction: discord.Interaction) -> None:
            if interaction.guild_id != self.config.discord.guild_id or interaction.guild is None:
                await interaction.response.send_message("This command is not available here.", ephemeral=True)
                return

            await interaction.response.defer()
            output_path = await self.update_banner(interaction.guild)
            await interaction.followup.send(file=discord.File(str(output_path), filename="voice-banner.png"))

        self.tree.add_command(voice_top, guild=discord.Object(id=self.config.discord.guild_id))
        self.tree.add_command(voice_banner, guild=discord.Object(id=self.config.discord.guild_id))


def current_human_voice_members(guild: discord.Guild) -> dict[int, tuple[discord.Member, discord.abc.GuildChannel]]:
    members: dict[int, tuple[discord.Member, discord.abc.GuildChannel]] = {}
    voice_channels = list(guild.voice_channels) + list(guild.stage_channels)
    for channel in voice_channels:
        for member in channel.members:
            if not member.bot:
                members[member.id] = (member, channel)
    return members


def count_human_voice_members(guild: discord.Guild) -> int:
    return len(current_human_voice_members(guild))


def configure_logging(config: AppConfig) -> None:
    log_dir = config.root_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=getattr(logging, config.bot.log_level, logging.INFO),
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_dir / "bot.log", encoding="utf-8"),
        ],
    )


def run() -> None:
    config = load_config()
    configure_logging(config)
    bot = VoiceActivityBot(config)
    bot.run(config.discord.token, log_handler=None)
