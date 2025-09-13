"""Async Google Sheets client helpers (Stage 2 implementation)."""
from __future__ import annotations

import base64
import json
import os
import re
from typing import Any, Callable, Optional

import backoff
from aiohttp import ClientError
from google.oauth2.service_account import Credentials
from gspread.exceptions import APIError, WorksheetNotFound
from gspread_asyncio import AsyncioGspreadClient, AsyncioGspreadClientManager

from ..config import Settings


SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

HEADERS = [
    "Timestamp",
    "User ID",
    "Full Name",
    "Username",
    "Invite Link",
    "Link Name",
]


def _sanitize_sheet_title(title: str, max_len: int = 100) -> str:
    """Sanitize sheet title for Google Sheets constraints.

    Removes control characters and disallowed symbols, collapses whitespace,
    trims to max_len, and ensures non-empty default.
    """
    s = title.strip()
    # Remove control chars
    s = re.sub(r"[\x00-\x1F\x7F]", "", s)
    # Remove characters commonly problematic in sheet titles
    s = re.sub(r"[:\\/?*\[\]]", "", s)
    # Collapse internal whitespace
    s = re.sub(r"\s+", " ", s)
    s = s[:max_len].strip()
    return s or "Sheet"

# Public alias if needed by other modules
sanitize_sheet_title = _sanitize_sheet_title


class GoogleSheetsService:
    def __init__(self, credentials: Optional[str], spreadsheet_id: Optional[str]):
        if not credentials:
            raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_JSON is not set")
        if not spreadsheet_id:
            raise RuntimeError("GOOGLE_SPREADSHEET_ID is not set")

        self.credentials_input = credentials
        self.spreadsheet_id = spreadsheet_id

        def _creds_factory() -> Credentials:
            # Accept either file path, raw JSON string, or base64-encoded JSON
            ci = self.credentials_input
            # File path
            if ci and os.path.isfile(ci):
                return Credentials.from_service_account_file(ci, scopes=SCOPES)
            # Raw JSON
            if ci and ci.strip().startswith("{"):
                info = json.loads(ci)
                return Credentials.from_service_account_info(info, scopes=SCOPES)
            # Base64-encoded JSON (common in env/secrets)
            if ci:
                try:
                    decoded = base64.b64decode(ci).decode("utf-8")
                    info = json.loads(decoded)
                    return Credentials.from_service_account_info(info, scopes=SCOPES)
                except Exception:
                    pass
            raise RuntimeError("Invalid GOOGLE_SERVICE_ACCOUNT_JSON: provide a file path, raw JSON, or base64 JSON")

        self._manager = AsyncioGspreadClientManager(_creds_factory)

    async def _get_client(self) -> AsyncioGspreadClient:
        return await self._manager.authorize()

    @backoff.on_exception(backoff.expo, (APIError, ClientError), max_time=60)
    async def _get_spreadsheet(self):
        client = await self._get_client()
        return await client.open_by_key(self.spreadsheet_id)

    @backoff.on_exception(backoff.expo, (APIError, ClientError), max_time=60)
    async def ensure_sheet(self, title: str) -> str:
        """Ensure worksheet with sanitized title exists; return the final title used.

        If the worksheet does not exist, create it and write the header row.
        Performs basic collision resolution by appending a numeric suffix.
        """
        spreadsheet = await self._get_spreadsheet()
        base = _sanitize_sheet_title(title)
        final_title = base
        # Detect existing base sheet; if found, treat as collision and start with suffix 2
        try:
            await spreadsheet.worksheet(final_title)
            suffix = 2
            final_title = f"{base} {suffix}"[:100]
        except WorksheetNotFound:
            suffix = 1

        # Try creating; on duplicate, add incrementing suffix
        while True:
            try:
                ws = await spreadsheet.add_worksheet(title=final_title, rows=100, cols=16)
                # Write header row once for a new sheet
                await ws.append_row(HEADERS, value_input_option="USER_ENTERED")
                return final_title
            except APIError as e:
                # If title already exists (race), try next suffix; else re-raise
                message = str(e)
                if "already exists" in message.lower() or "duplicate" in message.lower():
                    suffix += 1
                    final_title = f"{base} {suffix}"[:100]
                    continue
                raise

    @backoff.on_exception(backoff.expo, (APIError, ClientError), max_time=60)
    async def append_row(self, sheet_title: str, row: list[Any]) -> None:
        """Append a row to the worksheet with retries on transient errors."""
        spreadsheet = await self._get_spreadsheet()
        try:
            ws = await spreadsheet.worksheet(sheet_title)
        except WorksheetNotFound:
            # Create sheet on the fly if missing
            created_title = await self.ensure_sheet(sheet_title)
            ws = await spreadsheet.worksheet(created_title)

        await ws.append_row(row, value_input_option="USER_ENTERED")


def create_google_sheets_service_from_settings(settings: Settings) -> GoogleSheetsService:
    return GoogleSheetsService(
        credentials=settings.GOOGLE_SERVICE_ACCOUNT_JSON,
        spreadsheet_id=settings.GOOGLE_SPREADSHEET_ID,
    )
