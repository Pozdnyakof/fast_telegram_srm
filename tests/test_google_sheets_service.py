import asyncio
from types import SimpleNamespace

import pytest

from app.services.google_sheets import GoogleSheetsService, HEADERS


class FakeWorksheet:
    def __init__(self, title):
        self.title = title
        self.rows = []

    async def append_row(self, row, value_input_option=None):
        self.rows.append(row)


class FakeSpreadsheet:
    def __init__(self):
        self.sheets = {}

    async def worksheet(self, title):
        if title not in self.sheets:
            from gspread.exceptions import WorksheetNotFound
            raise WorksheetNotFound(title)
        return self.sheets[title]

    async def add_worksheet(self, title, rows, cols):
        if title in self.sheets:
            from gspread.exceptions import APIError
            raise APIError({"error": {"message": "already exists"}})
        ws = FakeWorksheet(title)
        self.sheets[title] = ws
        return ws


class FakeClient:
    def __init__(self, spreadsheet: FakeSpreadsheet):
        self._spreadsheet = spreadsheet

    async def open_by_key(self, key):
        return self._spreadsheet


class FakeManager:
    def __init__(self, client: FakeClient):
        self._client = client

    async def authorize(self):
        return self._client


@pytest.mark.asyncio
async def test_ensure_sheet_creates_with_headers(monkeypatch):
    spreadsheet = FakeSpreadsheet()

    # Build a GoogleSheetsService wired to our fake manager
    svc = GoogleSheetsService(credentials_path="/dev/null", spreadsheet_id="dummy")
    monkeypatch.setattr(svc, "_manager", FakeManager(FakeClient(spreadsheet)))

    final_title = await svc.ensure_sheet("My Channel")
    # Since no initial sheet exists, header will be added to created sheet
    ws = await spreadsheet.worksheet(final_title)
    # Header should be the first append
    assert ws.rows[0] == HEADERS


@pytest.mark.asyncio
async def test_ensure_sheet_collision_adds_suffix(monkeypatch):
    spreadsheet = FakeSpreadsheet()
    # Precreate a conflicting sheet
    spreadsheet.sheets["Channel"] = FakeWorksheet("Channel")

    svc = GoogleSheetsService(credentials_path="/dev/null", spreadsheet_id="dummy")
    monkeypatch.setattr(svc, "_manager", FakeManager(FakeClient(spreadsheet)))

    final_title = await svc.ensure_sheet("Channel")
    assert final_title != "Channel"
    assert final_title.startswith("Channel ")


@pytest.mark.asyncio
async def test_append_row_creates_sheet_if_missing(monkeypatch):
    spreadsheet = FakeSpreadsheet()

    svc = GoogleSheetsService(credentials_path="/dev/null", spreadsheet_id="dummy")
    monkeypatch.setattr(svc, "_manager", FakeManager(FakeClient(spreadsheet)))

    await svc.append_row("New One", ["a", "b"])  # should auto-create and append
    ws = await spreadsheet.worksheet("New One")
    # First row is headers, second is our data
    assert ws.rows[0] == HEADERS
    assert ws.rows[1] == ["a", "b"]
