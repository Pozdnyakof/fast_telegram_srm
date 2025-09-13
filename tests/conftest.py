import os
import tempfile
from typing import AsyncGenerator

import pytest_asyncio

from app.services.db import Database


@pytest_asyncio.fixture()
async def temp_db_path() -> AsyncGenerator[str, None]:
    # Use a real temp file on disk so aiosqlite can reopen connections
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "test.db")
        yield path


@pytest_asyncio.fixture()
async def db(temp_db_path: str) -> AsyncGenerator[Database, None]:
    database = Database(temp_db_path)
    await database.init_db()
    yield database
