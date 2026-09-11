"""SQLite access layer (Stage 3)."""
from __future__ import annotations

import os
from typing import List, Optional, Sequence, Tuple

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
            # Outbox of the membership journal: entries wait here until
            # delivered, so an outage on the receiving side loses nothing.
            # Parked entries were refused for good and are kept for a look.
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS event_outbox (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    payload TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    parked_at INTEGER,
                    last_error TEXT
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

    async def enqueue_event(self, payload: str, created_at: int) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO event_outbox (payload, created_at) VALUES (?, ?)",
                (payload, created_at),
            )
            await db.commit()

    async def fetch_pending_events(self, limit: int) -> List[Tuple[int, str]]:
        """Oldest pending entries first: the receiver must see them in order."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT id, payload FROM event_outbox WHERE parked_at IS NULL ORDER BY id LIMIT ?",
                (limit,),
            ) as cursor:
                return [(int(row[0]), str(row[1])) for row in await cursor.fetchall()]

    async def delete_events(self, ids: Sequence[int]) -> None:
        if not ids:
            return
        placeholders = ", ".join("?" for _ in ids)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(f"DELETE FROM event_outbox WHERE id IN ({placeholders})", tuple(ids))
            await db.commit()

    async def park_event(self, event_id: int, error: str, parked_at: int) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE event_outbox SET parked_at = ?, last_error = ? WHERE id = ?",
                (parked_at, error, event_id),
            )
            await db.commit()

    async def count_parked_events(self) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT count(*) FROM event_outbox WHERE parked_at IS NOT NULL") as cursor:
                row = await cursor.fetchone()
                return int(row[0]) if row else 0

