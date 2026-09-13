from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import logging

import aiosqlite

from .utils import ensure_parent_dir, utc_now


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ActiveSession:
    guild_id: int
    user_id: int
    channel_id: int
    started_at: int


@dataclass(frozen=True)
class TopUser:
    user_id: int
    display_name: str
    username: str
    avatar_url: str | None
    total_seconds: int


@dataclass(frozen=True)
class TopChannel:
    channel_id: int
    name: str
    total_seconds: int


class VoiceDatabase:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._connection: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        ensure_parent_dir(self.path)
        self._connection = await aiosqlite.connect(self.path)
        self._connection.row_factory = aiosqlite.Row
        await self.db.execute("PRAGMA journal_mode = WAL")
        await self.db.execute("PRAGMA foreign_keys = ON")
        await self.db.execute("PRAGMA busy_timeout = 5000")
        await self.migrate()
        logger.info("SQLite database ready: %s", self.path)

    async def close(self) -> None:
        if self._connection is None:
            return
        await self._connection.commit()
        await self._connection.close()
        self._connection = None
        logger.info("SQLite database closed.")

    @property
    def db(self) -> aiosqlite.Connection:
        if self._connection is None:
            raise RuntimeError("Database is not connected.")
        return self._connection

    async def migrate(self) -> None:
        await self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                display_name TEXT NOT NULL,
                username TEXT NOT NULL,
                avatar_url TEXT,
                updated_at INTEGER NOT NULL,
                PRIMARY KEY (guild_id, user_id)
            );

            CREATE TABLE IF NOT EXISTS channels (
                guild_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                updated_at INTEGER NOT NULL,
                PRIMARY KEY (guild_id, channel_id)
            );

            CREATE TABLE IF NOT EXISTS active_sessions (
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                started_at INTEGER NOT NULL,
                PRIMARY KEY (guild_id, user_id)
            );

            CREATE TABLE IF NOT EXISTS voice_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                started_at INTEGER NOT NULL,
                ended_at INTEGER NOT NULL,
                duration_seconds INTEGER NOT NULL,
                close_reason TEXT NOT NULL DEFAULT 'leave'
            );

            CREATE INDEX IF NOT EXISTS idx_voice_sessions_guild_user
                ON voice_sessions (guild_id, user_id);
            CREATE INDEX IF NOT EXISTS idx_voice_sessions_guild_channel
                ON voice_sessions (guild_id, channel_id);
            CREATE INDEX IF NOT EXISTS idx_voice_sessions_guild_time
                ON voice_sessions (guild_id, started_at, ended_at);
            """
        )
        await self.db.commit()

    async def upsert_user(
        self,
        *,
        guild_id: int,
        user_id: int,
        display_name: str,
        username: str,
        avatar_url: str | None,
        now: int | None = None,
    ) -> None:
        timestamp = now or utc_now()
        await self.db.execute(
            """
            INSERT INTO users (guild_id, user_id, display_name, username, avatar_url, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(guild_id, user_id) DO UPDATE SET
                display_name = excluded.display_name,
                username = excluded.username,
                avatar_url = excluded.avatar_url,
                updated_at = excluded.updated_at
            """,
            (guild_id, user_id, display_name, username, avatar_url, timestamp),
        )
        await self.db.commit()

    async def upsert_channel(self, *, guild_id: int, channel_id: int, name: str, now: int | None = None) -> None:
        timestamp = now or utc_now()
        await self.db.execute(
            """
            INSERT INTO channels (guild_id, channel_id, name, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(guild_id, channel_id) DO UPDATE SET
                name = excluded.name,
                updated_at = excluded.updated_at
            """,
            (guild_id, channel_id, name, timestamp),
        )
        await self.db.commit()

    async def start_session(self, *, guild_id: int, user_id: int, channel_id: int, started_at: int | None = None) -> None:
        timestamp = started_at or utc_now()
        await self.db.execute(
            """
            INSERT INTO active_sessions (guild_id, user_id, channel_id, started_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(guild_id, user_id) DO UPDATE SET
                channel_id = excluded.channel_id
            """,
            (guild_id, user_id, channel_id, timestamp),
        )
        await self.db.commit()

    async def move_session(self, *, guild_id: int, user_id: int, channel_id: int) -> bool:
        cursor = await self.db.execute(
            """
            UPDATE active_sessions
            SET channel_id = ?
            WHERE guild_id = ? AND user_id = ?
            """,
            (channel_id, guild_id, user_id),
        )
        await self.db.commit()
        return cursor.rowcount > 0

    async def end_session(
        self,
        *,
        guild_id: int,
        user_id: int,
        ended_at: int | None = None,
        reason: str = "leave",
    ) -> ActiveSession | None:
        timestamp = ended_at or utc_now()
        async with self.db.execute(
            """
            SELECT guild_id, user_id, channel_id, started_at
            FROM active_sessions
            WHERE guild_id = ? AND user_id = ?
            """,
            (guild_id, user_id),
        ) as cursor:
            row = await cursor.fetchone()

        if row is None:
            return None

        started_at = int(row["started_at"])
        duration = max(0, timestamp - started_at)
        await self.db.execute(
            """
            INSERT INTO voice_sessions
                (guild_id, user_id, channel_id, started_at, ended_at, duration_seconds, close_reason)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (guild_id, user_id, int(row["channel_id"]), started_at, timestamp, duration, reason),
        )
        await self.db.execute(
            "DELETE FROM active_sessions WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        )
        await self.db.commit()
        return ActiveSession(guild_id=guild_id, user_id=user_id, channel_id=int(row["channel_id"]), started_at=started_at)

    async def active_sessions(self, guild_id: int) -> list[ActiveSession]:
        async with self.db.execute(
            """
            SELECT guild_id, user_id, channel_id, started_at
            FROM active_sessions
            WHERE guild_id = ?
            """,
            (guild_id,),
        ) as cursor:
            rows = await cursor.fetchall()
        return [
            ActiveSession(
                guild_id=int(row["guild_id"]),
                user_id=int(row["user_id"]),
                channel_id=int(row["channel_id"]),
                started_at=int(row["started_at"]),
            )
            for row in rows
        ]

    async def top_user(self, *, guild_id: int, period_start: int | None, now: int | None = None) -> TopUser | None:
        timestamp = now or utc_now()
        lower_bound = 0 if period_start is None else period_start
        async with self.db.execute(
            """
            WITH finished AS (
                SELECT guild_id, user_id,
                    CASE
                        WHEN ended_at <= :lower_bound OR started_at >= :now THEN 0
                        ELSE MIN(ended_at, :now) - MAX(started_at, :lower_bound)
                    END AS seconds
                FROM voice_sessions
                WHERE guild_id = :guild_id
            ),
            active AS (
                SELECT guild_id, user_id,
                    CASE
                        WHEN started_at >= :now THEN 0
                        ELSE :now - MAX(started_at, :lower_bound)
                    END AS seconds
                FROM active_sessions
                WHERE guild_id = :guild_id
            ),
            totals AS (
                SELECT guild_id, user_id, SUM(seconds) AS total_seconds
                FROM (
                    SELECT * FROM finished
                    UNION ALL
                    SELECT * FROM active
                )
                GROUP BY guild_id, user_id
            )
            SELECT
                totals.user_id,
                COALESCE(users.display_name, CAST(totals.user_id AS TEXT)) AS display_name,
                COALESCE(users.username, CAST(totals.user_id AS TEXT)) AS username,
                users.avatar_url,
                CAST(totals.total_seconds AS INTEGER) AS total_seconds
            FROM totals
            LEFT JOIN users
                ON users.guild_id = totals.guild_id
                AND users.user_id = totals.user_id
            WHERE totals.total_seconds > 0
            ORDER BY totals.total_seconds DESC
            LIMIT 1
            """,
            {"guild_id": guild_id, "lower_bound": lower_bound, "now": timestamp},
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return None
        return TopUser(
            user_id=int(row["user_id"]),
            display_name=str(row["display_name"]),
            username=str(row["username"]),
            avatar_url=str(row["avatar_url"]) if row["avatar_url"] else None,
            total_seconds=int(row["total_seconds"]),
        )

    async def top_channels(
        self,
        *,
        guild_id: int,
        period_start: int | None,
        now: int | None = None,
        limit: int = 3,
    ) -> list[TopChannel]:
        timestamp = now or utc_now()
        lower_bound = 0 if period_start is None else period_start
        async with self.db.execute(
            """
            WITH finished AS (
                SELECT guild_id, channel_id,
                    CASE
                        WHEN ended_at <= :lower_bound OR started_at >= :now THEN 0
                        ELSE MIN(ended_at, :now) - MAX(started_at, :lower_bound)
                    END AS seconds
                FROM voice_sessions
                WHERE guild_id = :guild_id
            ),
            active AS (
                SELECT guild_id, channel_id,
                    CASE
                        WHEN started_at >= :now THEN 0
                        ELSE :now - MAX(started_at, :lower_bound)
                    END AS seconds
                FROM active_sessions
                WHERE guild_id = :guild_id
            ),
            totals AS (
                SELECT guild_id, channel_id, SUM(seconds) AS total_seconds
                FROM (
                    SELECT * FROM finished
                    UNION ALL
                    SELECT * FROM active
                )
                GROUP BY guild_id, channel_id
            )
            SELECT
                totals.channel_id,
                COALESCE(channels.name, CAST(totals.channel_id AS TEXT)) AS name,
                CAST(totals.total_seconds AS INTEGER) AS total_seconds
            FROM totals
            LEFT JOIN channels
                ON channels.guild_id = totals.guild_id
                AND channels.channel_id = totals.channel_id
            WHERE totals.total_seconds > 0
            ORDER BY totals.total_seconds DESC
            LIMIT :limit
            """,
            {"guild_id": guild_id, "lower_bound": lower_bound, "now": timestamp, "limit": limit},
        ) as cursor:
            rows = await cursor.fetchall()
        return [
            TopChannel(channel_id=int(row["channel_id"]), name=str(row["name"]), total_seconds=int(row["total_seconds"]))
            for row in rows
        ]

