from __future__ import annotations

import asyncio
import logging

import discord

from .banner import BannerOptions, BannerPayload, BannerRenderer
from .config import ConfigError, Settings, load_settings
from .database import VoiceDatabase
from .logging_setup import configure_logging
from .tasks import BannerUpdateScheduler
from .voice_tracker import VoiceTracker


logger = logging.getLogger(__name__)


class DiscordVoiceBannerClient(discord.Client):
    def __init__(self, settings: Settings) -> None:
        intents = discord.Intents.default()
        intents.guilds = True
        intents.members = True
        intents.voice_states = True

        super().__init__(intents=intents)
        self.settings = settings
        self.database = VoiceDatabase(settings.database_path)
        self.tracker = VoiceTracker(database=self.database, guild_id=settings.guild_id, period=settings.banner_period)
        self.renderer = BannerRenderer(
            options=BannerOptions(
                output_path=settings.banner_output_path,
                width=settings.banner_width,
                height=settings.banner_height,
                language=settings.language,
                custom_banner_path=settings.custom_banner_path,
                font_path=settings.font_path,
                font_bold_path=settings.font_bold_path,
            )
        )
        self.scheduler = BannerUpdateScheduler(
            update_callback=self.update_banner,
            interval_seconds=settings.update_interval_seconds,
            cooldown_seconds=settings.banner_update_cooldown_seconds,
        )
        self._ready_once = False

    async def setup_hook(self) -> None:
        await self.database.connect()
        logger.info("Discord client setup complete.")

    async def on_ready(self) -> None:
        logger.info("Authorized as %s (%s).", self.user, self.user.id if self.user else "unknown")
        guild = self.get_guild(self.settings.guild_id)
        if guild is None:
            logger.critical("Configured guild %s is not visible to the bot.", self.settings.guild_id)
            await self.close()
            return

        logger.info("Connected to guild: %s (%s).", guild.name, guild.id)
        try:
            await self.tracker.sync_from_guild(guild)
            await self.update_banner()
        except Exception:
            logger.exception("Startup synchronization failed.")

        if not self._ready_once:
            self.scheduler.start()
            self._ready_once = True
            logger.info("Bot is Ready.")

    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        try:
            changed = await self.tracker.handle_voice_state_update(member, before.channel, after.channel)
            if changed:
                self.scheduler.request_update()
        except Exception:
            logger.exception("Failed to process voice state update for member_id=%s.", getattr(member, "id", "unknown"))

    async def on_error(self, event_method: str, *args: object, **kwargs: object) -> None:
        logger.exception("Unhandled Discord event error in %s.", event_method)

    async def update_banner(self) -> None:
        guild = self.get_guild(self.settings.guild_id)
        if guild is None:
            logger.warning("Cannot update banner: guild %s is unavailable.", self.settings.guild_id)
            return

        snapshot = await self.tracker.snapshot(guild)
        avatar_bytes = await self._load_top_user_avatar(guild, snapshot.top_user.user_id if snapshot.top_user else None)
        output_path = self.renderer.render(
            BannerPayload(
                guild_name=snapshot.guild_name,
                current_users=snapshot.current_users,
                active_channels=snapshot.active_channels,
                period=snapshot.period,
                top_user=snapshot.top_user,
                top_channels=snapshot.top_channels,
                avatar_bytes=avatar_bytes,
            )
        )
        logger.info("Banner statistics updated.")

        if not self.settings.apply_guild_banner:
            logger.info("APPLY_GUILD_BANNER=false; generated image saved to %s.", output_path)
            return

        try:
            await guild.edit(banner=output_path.read_bytes(), reason="discord-voice-banner auto update")
            logger.info("Guild banner updated through Discord API.")
        except discord.Forbidden:
            logger.exception("Discord Forbidden while updating guild banner. Check Manage Server permission and server features.")
        except discord.HTTPException:
            logger.exception("Discord HTTP error while updating guild banner.")
        except OSError:
            logger.exception("Could not read generated banner file: %s", output_path)

    async def _load_top_user_avatar(self, guild: discord.Guild, user_id: int | None) -> bytes | None:
        if user_id is None:
            return None
        member = guild.get_member(user_id)
        if member is None:
            try:
                member = await guild.fetch_member(user_id)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException) as exc:
                logger.warning("Could not fetch top user %s for avatar: %s", user_id, exc)
                return None
        try:
            return await member.display_avatar.read()
        except (discord.HTTPException, OSError) as exc:
            logger.warning("Could not load avatar for user %s: %s", user_id, exc)
            return None

    async def close(self) -> None:
        try:
            await self.scheduler.stop()
        finally:
            await self.database.close()
            await super().close()


async def run_bot(settings: Settings) -> None:
    client = DiscordVoiceBannerClient(settings)
    try:
        logger.info("Starting Discord client.")
        await client.start(settings.discord_token)
    except discord.LoginFailure:
        logger.exception("Discord rejected the token. Check DISCORD_TOKEN.")
        raise
    except discord.PrivilegedIntentsRequired:
        logger.exception("Discord requires privileged intents. Enable Server Members Intent and Voice States Intent.")
        raise
    finally:
        if not client.is_closed():
            await client.close()


def main() -> int:
    try:
        settings = load_settings(validate_secrets=True)
        configure_logging(settings)
    except ConfigError as exc:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-8s %(name)s: %(message)s")
        logging.getLogger(__name__).critical("%s", exc)
        return 2
    except Exception as exc:
        logging.basicConfig(level=logging.INFO)
        logging.getLogger(__name__).critical("Configuration failed: %s", exc)
        return 2

    try:
        asyncio.run(run_bot(settings))
    except KeyboardInterrupt:
        logger.info("Shutdown requested by keyboard interrupt.")
        return 0
    except Exception:
        logger.exception("Bot stopped because of a fatal error.")
        return 1
    return 0
