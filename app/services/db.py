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

