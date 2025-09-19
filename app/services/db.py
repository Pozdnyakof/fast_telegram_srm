"""SQLite access layer (Stage 3)."""
from __future__ import annotations

import os
from typing import Optional

import aiosqlite


class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path

    async def init_db(self) -> None:
        """Create database schema if not exists."""
        # Ensure directory exists
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS channels (
                    channel_id INTEGER PRIMARY KEY,
                    sheet_name TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            # Deduplication log for join requests: store last logged timestamp (epoch seconds)
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS join_request_log (
                    channel_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    last_logged_at INTEGER NOT NULL,
                    PRIMARY KEY (channel_id, user_id)
                )
                """
            )
            await db.commit()

    async def get_sheet_name(self, channel_id: int) -> Optional[str]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT sheet_name FROM channels WHERE channel_id = ?", (channel_id,)
            ) as cursor:
                row = await cursor.fetchone()
                return row["sheet_name"] if row else None

    async def upsert_channel(self, channel_id: int, sheet_name: str) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO channels (channel_id, sheet_name)
                VALUES (?, ?)
                ON CONFLICT(channel_id) DO UPDATE SET sheet_name = excluded.sheet_name
                """,
                (channel_id, sheet_name),
            )
            await db.commit()

    async def get_last_join_request_logged_at(self, channel_id: int, user_id: int) -> Optional[int]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT last_logged_at FROM join_request_log WHERE channel_id = ? AND user_id = ?",
                (channel_id, user_id),
            ) as cursor:
                row = await cursor.fetchone()
                return int(row["last_logged_at"]) if row else None

    async def upsert_join_request_logged_at(self, channel_id: int, user_id: int, ts_epoch: int) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO join_request_log (channel_id, user_id, last_logged_at)
                VALUES (?, ?, ?)
                ON CONFLICT(channel_id, user_id) DO UPDATE SET last_logged_at = excluded.last_logged_at
                """,
                (channel_id, user_id, ts_epoch),
            )
            await db.commit()

