import tempfile
import os
import pytest

from app.services.db import Database


@pytest.mark.asyncio
async def test_db_upsert_and_get():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "test.db")
        db = Database(path)
        await db.init_db()

        # Initially not found
        assert await db.get_sheet_name(12345) is None

        # Insert
        await db.upsert_channel(12345, "Sheet A")
        assert await db.get_sheet_name(12345) == "Sheet A"

        # Update
        await db.upsert_channel(12345, "Sheet B")
        assert await db.get_sheet_name(12345) == "Sheet B"
