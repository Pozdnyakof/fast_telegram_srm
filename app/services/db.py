"""SQLite access layer (stubs for Stage 3)."""
from __future__ import annotations

from typing import Optional


class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path

    async def init_db(self) -> None:
        raise NotImplementedError

    async def get_sheet_name(self, channel_id: int) -> Optional[str]:
        raise NotImplementedError

    async def upsert_channel(self, channel_id: int, sheet_name: str) -> None:
        raise NotImplementedError
