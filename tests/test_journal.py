"""Tests for the journal outbox and its delivery.

Handlers put entries into the bot's own SQLite, which is there even
when Postgres is not; a background task delivers them later. What must
hold: nothing is lost while Postgres is away, nothing is delivered out
of order, one bad entry does not hold back the rest, and the journal
never gets in the way of the sheet.
"""

import asyncio

import pytest

from app.services.db import Database
from app.services.journal import EventJournal, EventRejected, record_quietly, run_delivery


def _event(update_id):
    return {
        "update_id": update_id,
        "chat_id": -1003158922677,
        "chat_title": "Хоккей в плюсе | VIP",
        "user_id": 7175828896,
        "username": "daneksosol",
        "full_name": "настькин я",
        "actor_id": 8421258155,
        "actor_username": None,
        "event": "join",
        "invite_link": None,
        "invite_name": None,
        "occurred_at": "2026-09-10T15:01:38+00:00",
    }


class _Sink:
    """Stands in for Postgres; can be down or refuse particular entries."""

    def __init__(self, *, down=False, refuses=()):
        self.written = []
        self.down = down
        self.refuses = set(refuses)

    async def write(self, events):
        if self.down:
            raise ConnectionRefusedError("postgres is down")
        if any(e["update_id"] in self.refuses for e in events):
            raise EventRejected("new row violates check constraint")
        self.written.extend(events)


@pytest.mark.asyncio
async def test_a_delivered_entry_leaves_the_outbox(db):
    journal = EventJournal(db)
    await journal.record(_event(1))
    sink = _Sink()

    assert await journal.deliver_pending(sink) == 1
    assert sink.written == [_event(1)]
    assert await journal.deliver_pending(sink) == 0


@pytest.mark.asyncio
async def test_entries_are_delivered_in_the_order_they_happened(db):
    """A leave delivered before its join would read as the opposite."""
    journal = EventJournal(db)
    for update_id in (3, 1, 2):
        await journal.record(_event(update_id))
    sink = _Sink()

    await journal.deliver_pending(sink)

    assert [e["update_id"] for e in sink.written] == [3, 1, 2]


@pytest.mark.asyncio
async def test_an_outage_loses_nothing(db):
    journal = EventJournal(db)
    await journal.record(_event(1))

    with pytest.raises(ConnectionRefusedError):
        await journal.deliver_pending(_Sink(down=True))

    sink = _Sink()
    await journal.deliver_pending(sink)
    assert sink.written == [_event(1)]


@pytest.mark.asyncio
async def test_a_refused_entry_does_not_hold_back_the_rest(db):
    """Retrying an entry Postgres refuses would stall the journal forever."""
    journal = EventJournal(db)
    for update_id in (1, 2, 3):
        await journal.record(_event(update_id))
    sink = _Sink(refuses={2})

    assert await journal.deliver_pending(sink) == 3

    assert [e["update_id"] for e in sink.written] == [1, 3]
    assert await journal.deliver_pending(sink) == 0
    assert await db.count_parked_events() == 1


@pytest.mark.asyncio
async def test_an_unreadable_entry_is_set_aside(db):
    journal = EventJournal(db)
    await db.enqueue_event("{not json", created_at=0)
    await journal.record(_event(1))
    sink = _Sink()

    await journal.deliver_pending(sink)

    assert sink.written == [_event(1)]
    assert await db.count_parked_events() == 1


@pytest.mark.asyncio
async def test_an_entry_survives_a_restart(temp_db_path):
    first = Database(temp_db_path)
    await first.init_db()
    await EventJournal(first).record(_event(1))

    second = Database(temp_db_path)
    await second.init_db()
    sink = _Sink()
    await EventJournal(second).deliver_pending(sink)

    assert sink.written == [_event(1)]


class _BrokenJournal:
    async def record(self, event):
        raise OSError("disk I/O error")


@pytest.mark.asyncio
async def test_a_broken_journal_never_raises_into_the_handler():
    await record_quietly(_BrokenJournal(), lambda: _event(1))


@pytest.mark.asyncio
async def test_a_broken_event_builder_never_raises_into_the_handler(db):
    def build():
        raise AttributeError("'NoneType' object has no attribute 'status'")

    await record_quietly(EventJournal(db), build)


@pytest.mark.asyncio
async def test_with_the_journal_off_nothing_is_built():
    def build():
        raise AssertionError("must not be called")

    await record_quietly(None, build)


@pytest.mark.asyncio
async def test_an_update_that_is_no_membership_change_records_nothing(db):
    journal = EventJournal(db)

    await record_quietly(journal, lambda: None)

    assert await journal.deliver_pending(_Sink()) == 0


class _FlakySink(_Sink):
    """Down for the first few writes, then back."""

    def __init__(self, failures):
        super().__init__()
        self.failures = failures
        self.delivered = asyncio.Event()

    async def write(self, events):
        if self.failures:
            self.failures -= 1
            raise ConnectionRefusedError("postgres is restarting")
        await super().write(events)
        self.delivered.set()


@pytest.mark.asyncio
async def test_delivery_carries_on_once_postgres_is_back(db):
    """A tg_parser deploy restarts Postgres; the bot must not care."""
    journal = EventJournal(db)
    await journal.record(_event(1))
    sink = _FlakySink(failures=2)
    stop = asyncio.Event()

    task = asyncio.create_task(
        run_delivery(journal, sink, stop, idle_seconds=0.01, max_backoff_seconds=0.02),
    )
    try:
        await asyncio.wait_for(sink.delivered.wait(), timeout=5)
    finally:
        stop.set()
        await asyncio.wait_for(task, timeout=5)

    assert sink.written == [_event(1)]
    assert await journal.deliver_pending(_Sink()) == 0


@pytest.mark.asyncio
async def test_stopping_waits_out_a_long_pause(db):
    """A shutdown must not sit through a minute of retry backoff."""
    stop = asyncio.Event()
    task = asyncio.create_task(
        run_delivery(EventJournal(db), _Sink(down=True), stop, idle_seconds=60),
    )
    await asyncio.sleep(0.05)

    stop.set()

    await asyncio.wait_for(task, timeout=2)
