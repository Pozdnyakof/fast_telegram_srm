"""Async Google Sheets client helpers (stubs for Stage 2)."""
from __future__ import annotations

from typing import Any, Optional


class GoogleSheetsService:
    def __init__(self, credentials_path: Optional[str], spreadsheet_id: Optional[str]):
        self.credentials_path = credentials_path
        self.spreadsheet_id = spreadsheet_id

    async def ensure_sheet(self, title: str) -> Any:  # will return Worksheet in Stage 2
        raise NotImplementedError

    async def append_row(self, sheet_title: str, row: list[Any]) -> None:
        raise NotImplementedError
