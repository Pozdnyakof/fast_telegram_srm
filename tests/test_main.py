"""Bot lifecycle around the journal delivery task."""

import asyncio

import pytest

from app.main import journal_delivery
from app.services.journal import EventJournal


@pytest.mark.asyncio
async def test_with_the_journal_off_no_delivery_runs(db):
    before = asyncio.all_tasks()

    async with journal_delivery(None, None):
        assert asyncio.all_tasks() == before


@pytest.mark.asyncio
async def test_a_shutdown_is_prompt_while_postgres_is_unreachable(db):
    """systemd waits for the bot to stop; an outage must not stall that."""
    unreachable = "postgresql://srm_writer:x@127.0.0.1:9/nowhere"
    journal = EventJournal(db)
    await journal.record({"update_id": 1})

    async def poll_briefly():
        async with journal_delivery(journal, unreachable, stop_timeout=5):
            await asyncio.sleep(0.3)

    await asyncio.wait_for(poll_briefly(), timeout=8)
