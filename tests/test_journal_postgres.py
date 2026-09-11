"""Contract tests against the real receiving table in tg_parser's Postgres.

What these check lives on the other side: the column list, the event
kinds the table accepts, and that the bot's role, which may only
insert, can write the way the bot writes. So they run against a
database migrated by tg_parser (its test container will do), pointed
to by SRM_TEST_PG_ADMIN_DSN, and are skipped otherwise.
"""

import os
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit

import pytest
import pytest_asyncio

from app.services.journal import EventJournal, EventRejected, PostgresSink

asyncpg = pytest.importorskip("asyncpg")

_ADMIN_DSN = os.environ.get("SRM_TEST_PG_ADMIN_DSN", "")
_PASSWORD = "srm-contract-test"

pytestmark = pytest.mark.skipif(not _ADMIN_DSN, reason="SRM_TEST_PG_ADMIN_DSN is not set")


def _writer_dsn():
    parts = urlsplit(_ADMIN_DSN)
    host = f"{parts.hostname}:{parts.port}" if parts.port else parts.hostname
    return urlunsplit(parts._replace(netloc=f"srm_writer:{_PASSWORD}@{host}"))


def _event(update_id, **overrides):
    event = {
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
    event.update(overrides)
    return event


@pytest_asyncio.fixture()
async def admin():
    conn = await asyncpg.connect(_ADMIN_DSN)
    if not await conn.fetchval("SELECT to_regclass('srm.membership_events') IS NOT NULL"):
        await conn.close()
        pytest.skip("srm.membership_events is missing: apply tg_parser migrations first")
    # The role has no login in a fresh database; the password is set
    # out of band on the server, and here only for the test's duration.
    await conn.execute(f"ALTER ROLE srm_writer LOGIN PASSWORD '{_PASSWORD}'")
    await conn.execute("DELETE FROM srm.membership_events")
    try:
        yield conn
    finally:
        await conn.execute("DELETE FROM srm.membership_events")
        await conn.execute("ALTER ROLE srm_writer NOLOGIN PASSWORD NULL")
        await conn.close()


@pytest_asyncio.fixture()
async def sink(admin):
    postgres = PostgresSink(_writer_dsn())
    yield postgres
    await postgres.close()


async def _update_ids(admin):
    rows = await admin.fetch("SELECT update_id FROM srm.membership_events ORDER BY update_id")
    return [row["update_id"] for row in rows]


@pytest.mark.asyncio
async def test_the_bot_role_can_write_an_entry(sink, admin):
    await sink.write([_event(1)])

    row = await admin.fetchrow("SELECT * FROM srm.membership_events")
    assert row["actor_id"] == 8421258155
    assert row["full_name"] == "настькин я"
    assert row["occurred_at"] == datetime(2026, 9, 10, 15, 1, 38, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_a_replayed_update_is_written_once(sink, admin):
    """After a crash Telegram hands the bot the same update again."""
    await sink.write([_event(1)])
    await sink.write([_event(1), _event(2)])

    assert await _update_ids(admin) == [1, 2]


@pytest.mark.asyncio
async def test_every_kind_the_bot_emits_is_accepted(sink, admin):
    kinds = ("join", "left", "kicked", "request")

    await sink.write([_event(n, event=kind) for n, kind in enumerate(kinds, 1)])

    assert await _update_ids(admin) == [1, 2, 3, 4]


@pytest.mark.asyncio
async def test_an_entry_the_table_refuses_is_reported_as_rejected(sink):
    with pytest.raises(EventRejected):
        await sink.write([_event(1, event="joined")])


@pytest.mark.asyncio
async def test_a_refused_batch_leaves_nothing_behind_and_the_sink_usable(sink, admin):
    with pytest.raises(EventRejected):
        await sink.write([_event(1), _event(2, event="joined")])

    await sink.write([_event(3)])

    assert await _update_ids(admin) == [3]


@pytest.mark.asyncio
async def test_the_outbox_drains_into_postgres_past_a_bad_entry(db, sink, admin):
    journal = EventJournal(db)
    for update_id, kind in ((1, "join"), (2, "joined"), (3, "left")):
        await journal.record(_event(update_id, event=kind))

    await journal.deliver_pending(sink)

    assert await _update_ids(admin) == [1, 3]
    assert await db.count_parked_events() == 1


@pytest.mark.asyncio
async def test_the_bot_role_cannot_read_the_journal_back(admin):
    """A leak of the bot's settings must not become a leak of subscribers."""
    conn = await asyncpg.connect(_writer_dsn())
    try:
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await conn.fetch("SELECT * FROM srm.membership_events")
    finally:
        await conn.close()
