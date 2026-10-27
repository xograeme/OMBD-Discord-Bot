"""Per-server trivia scores stored in a separate SQLite database."""

import asyncio
from contextlib import closing
import sqlite3


class Leaderboard:
    def __init__(self, db_path: str):
        self.db_path = db_path

    async def init(self):
        await asyncio.to_thread(self._init)

    def _init(self):
        with closing(sqlite3.connect(self.db_path, timeout=30)) as conn:
            with conn:
                conn.execute(
                    "CREATE TABLE IF NOT EXISTS scores ("
                    "guild_id INTEGER, user_id INTEGER, points INTEGER, "
                    "PRIMARY KEY(guild_id, user_id))"
                )

    async def add_points(self, guild_id: int, user_id: int, points: int) -> int:
        return await asyncio.to_thread(self._add_points, guild_id, user_id, points)

    def _add_points(self, guild_id: int, user_id: int, points: int) -> int:
        with closing(sqlite3.connect(self.db_path, timeout=30)) as conn:
            with conn:
                conn.execute(
                    "INSERT INTO scores (guild_id, user_id, points) VALUES (?, ?, ?) "
                    "ON CONFLICT(guild_id, user_id) DO UPDATE "
                    "SET points = scores.points + excluded.points",
                    (guild_id, user_id, points),
                )
                # Keep the write transaction open until its resulting total is read.
                row = conn.execute(
                    "SELECT points FROM scores WHERE guild_id = ? AND user_id = ?",
                    (guild_id, user_id),
                ).fetchone()
                return row[0]

    async def get(self, guild_id: int, user_id: int) -> int:
        return await asyncio.to_thread(self._get, guild_id, user_id)

    def _get(self, guild_id: int, user_id: int) -> int:
        with closing(sqlite3.connect(self.db_path, timeout=30)) as conn:
            row = conn.execute(
                "SELECT points FROM scores WHERE guild_id = ? AND user_id = ?",
                (guild_id, user_id),
            ).fetchone()
            return row[0] if row else 0

    async def top(self, guild_id: int, limit: int = 10) -> list[tuple[int, int]]:
        return await asyncio.to_thread(self._top, guild_id, limit)

    def _top(self, guild_id: int, limit: int) -> list[tuple[int, int]]:
        with closing(sqlite3.connect(self.db_path, timeout=30)) as conn:
            return conn.execute(
                "SELECT user_id, points FROM scores WHERE guild_id = ? "
                "ORDER BY points DESC, user_id ASC LIMIT ?",
                (guild_id, max(0, limit)),
            ).fetchall()
