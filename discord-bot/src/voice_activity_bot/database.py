from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import time

import aiosqlite


@dataclass(frozen=True)
class ActiveSession:
    guild_id: int
    user_id: int
    channel_id: int
    started_at: int


@dataclass(frozen=True)
class TopUser:
    guild_id: int
    user_id: int
    display_name: str
    avatar_url: str | None
    total_seconds: int


class VoiceActivityStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._db: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(self.path)
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("PRAGMA journal_mode = WAL")
        await self._db.execute("PRAGMA foreign_keys = ON")
        await self.migrate()

    async def close(self) -> None:
        if self._db is not None:
            await self._db.close()
            self._db = None

    @property
    def db(self) -> aiosqlite.Connection:
        if self._db is None:
            raise RuntimeError("Database is not connected.")
        return self._db

    async def migrate(self) -> None:
        await self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                display_name TEXT NOT NULL,
                avatar_url TEXT,
                updated_at INTEGER NOT NULL,
                PRIMARY KEY (guild_id, user_id)
            );

            CREATE TABLE IF NOT EXISTS active_sessions (
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                started_at INTEGER NOT NULL,
                PRIMARY KEY (guild_id, user_id)
            );

            CREATE TABLE IF NOT EXISTS voice_intervals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                started_at INTEGER NOT NULL,
                ended_at INTEGER NOT NULL,
                duration_seconds INTEGER NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_voice_intervals_guild_user
                ON voice_intervals (guild_id, user_id);
            CREATE INDEX IF NOT EXISTS idx_voice_intervals_guild_time
                ON voice_intervals (guild_id, started_at, ended_at);
            """
        )
        await self.db.commit()

    async def upsert_user(
        self,
        *,
        guild_id: int,
        user_id: int,
        display_name: str,
        avatar_url: str | None,
        now: int | None = None,
    ) -> None:
        now = now or utc_now()
        await self.db.execute(
            """
            INSERT INTO users (guild_id, user_id, display_name, avatar_url, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(guild_id, user_id) DO UPDATE SET
                display_name = excluded.display_name,
                avatar_url = excluded.avatar_url,
                updated_at = excluded.updated_at
            """,
            (guild_id, user_id, display_name, avatar_url, now),
        )
        await self.db.commit()

    async def start_session(
        self,
        *,
        guild_id: int,
        user_id: int,
        channel_id: int,
        started_at: int | None = None,
    ) -> None:
        started_at = started_at or utc_now()
        await self.db.execute(
            """
            INSERT INTO active_sessions (guild_id, user_id, channel_id, started_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(guild_id, user_id) DO UPDATE SET
                channel_id = excluded.channel_id
            """,
            (guild_id, user_id, channel_id, started_at),
        )
        await self.db.commit()

    async def update_session_channel(self, *, guild_id: int, user_id: int, channel_id: int) -> bool:
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

    async def close_session(
        self,
        *,
        guild_id: int,
        user_id: int,
        ended_at: int | None = None,
    ) -> ActiveSession | None:
        ended_at = ended_at or utc_now()
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
        duration = max(0, ended_at - started_at)

        await self.db.execute(
            """
            INSERT INTO voice_intervals (guild_id, user_id, channel_id, started_at, ended_at, duration_seconds)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (guild_id, user_id, int(row["channel_id"]), started_at, ended_at, duration),
        )
        await self.db.execute(
            """
            DELETE FROM active_sessions
            WHERE guild_id = ? AND user_id = ?
            """,
            (guild_id, user_id),
        )
        await self.db.commit()

        return ActiveSession(
            guild_id=int(row["guild_id"]),
            user_id=int(row["user_id"]),
            channel_id=int(row["channel_id"]),
            started_at=started_at,
        )

    async def get_active_sessions(self, guild_id: int) -> list[ActiveSession]:
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

    async def get_top_user(self, *, guild_id: int, period_start: int | None, now: int | None = None) -> TopUser | None:
        now = now or utc_now()
        lower_bound = 0 if period_start is None else period_start

        async with self.db.execute(
            """
            WITH finished AS (
                SELECT
                    guild_id,
                    user_id,
                    CASE
                        WHEN ended_at <= :lower_bound OR started_at >= :now THEN 0
                        ELSE MIN(ended_at, :now) - MAX(started_at, :lower_bound)
                    END AS seconds
                FROM voice_intervals
                WHERE guild_id = :guild_id
            ),
            active AS (
                SELECT
                    guild_id,
                    user_id,
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
                totals.guild_id,
                totals.user_id,
                COALESCE(users.display_name, CAST(totals.user_id AS TEXT)) AS display_name,
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
            {"guild_id": guild_id, "lower_bound": lower_bound, "now": now},
        ) as cursor:
            row = await cursor.fetchone()

        if row is None:
            return None

        return TopUser(
            guild_id=int(row["guild_id"]),
            user_id=int(row["user_id"]),
            display_name=str(row["display_name"]),
            avatar_url=str(row["avatar_url"]) if row["avatar_url"] else None,
            total_seconds=int(row["total_seconds"]),
        )


def utc_now() -> int:
    return int(time.time())
