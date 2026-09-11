"""Membership journal: every join, leave and join request, as it happened.

Google Sheets shows the client the joins they care about, with the
handlers' own skip rules. The journal records every membership change
so that tg_parser can confirm who invited whom and tell who stayed. The
two are independent: nothing here touches the sheet.

Handlers only append to an outbox in the bot's own SQLite, which is
there even when Postgres is not. A background task delivers entries in
order and deletes what was delivered. Postgres ignores an update it
already has, so delivering an entry twice is harmless, and that is what
makes a crash between "delivered" and "deleted" safe.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Callable, List, Optional, Protocol, Tuple

from .db import Database

log = logging.getLogger(__name__)

_CHAT_TYPES = ("channel", "supergroup")
_INSIDE = ("creator", "administrator", "member")


def event_from_member_update(update: Any, raw_update: Any) -> Optional[dict]:
    """Entry for a ChatMemberUpdated, or None if nobody came or went.

    A join is a move from outside to inside, not any update that ends
    with "member": a demoted administrator was inside all along.
    `from_user` is whoever caused the change: the person themselves when
    they came on their own, the admin who added them otherwise.
    """
    new_member = update.new_chat_member
    if new_member is None:
        return None
    was_inside = _is_inside(update.old_chat_member)
    is_inside = _is_inside(new_member)
    if is_inside and not was_inside:
        kind = "join"
    elif was_inside and not is_inside:
        kind = "kicked" if new_member.status == "kicked" else "left"
    else:
        return None
    return _event(kind, update, new_member.user, raw_update)


def event_from_join_request(request: Any, raw_update: Any) -> Optional[dict]:
    """Entry for a ChatJoinRequest; the requester is the actor."""
    return _event("request", request, request.from_user, raw_update)


def _event(kind: str, update: Any, user: Any, raw_update: Any) -> Optional[dict]:
    chat = update.chat
    # update_id is the idempotency key downstream: without it a replayed
    # update would be written twice, so such an event is not written.
    update_id = getattr(raw_update, "update_id", None)
    if user is None or update_id is None or chat is None or chat.type not in _CHAT_TYPES:
        return None
    actor = update.from_user
    invite = update.invite_link
    return {
        "update_id": update_id,
        "chat_id": chat.id,
        "chat_title": chat.title,
        "user_id": user.id,
        "username": user.username,
        "full_name": user.full_name,
        "actor_id": actor.id if actor else None,
        "actor_username": actor.username if actor else None,
        "event": kind,
        "invite_link": invite.invite_link if invite else None,
        "invite_name": invite.name if invite else None,
        "occurred_at": _as_utc(update.date).isoformat(),
    }


def _is_inside(member: Any) -> bool:
    if member is None:
        return False
    # A restricted user may be inside or outside; Telegram says which.
    if member.status == "restricted":
        return bool(getattr(member, "is_member", False))
    return member.status in _INSIDE


def _as_utc(moment: Optional[datetime]) -> datetime:
    if moment is None:
        return datetime.now(timezone.utc)
    if moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


class EventRejected(Exception):
    """The receiver refused the entry itself; retrying will not help."""


class _Sink(Protocol):
    async def write(self, events: List[dict]) -> None: ...


class EventJournal:
    def __init__(self, db: Database):
        self._db = db

    async def record(self, event: dict) -> None:
        await self._db.enqueue_event(json.dumps(event, ensure_ascii=False), int(time.time()))

    async def deliver_pending(self, sink: _Sink, batch_size: int = 200) -> int:
        """Deliver one batch; return how many entries were settled.

        A connection problem propagates and leaves the batch in place.
        If the receiver refuses the batch, entries go one by one, so a
        single bad one is parked instead of stalling the journal forever.
        """
        pending = await self._db.fetch_pending_events(batch_size)
        if not pending:
            return 0
        readable = await self._parse(pending)
        if readable:
            try:
                await sink.write([event for _, event in readable])
            except EventRejected:
                await self._deliver_one_by_one(sink, readable)
            else:
                await self._db.delete_events([event_id for event_id, _ in readable])
        return len(pending)

    async def _parse(self, pending: List[Tuple[int, str]]) -> List[Tuple[int, dict]]:
        readable = []
        for event_id, payload in pending:
            try:
                readable.append((event_id, json.loads(payload)))
            except ValueError as exc:
                await self._park(event_id, f"unreadable payload: {exc}")
        return readable

    async def _deliver_one_by_one(self, sink: _Sink, entries: List[Tuple[int, dict]]) -> None:
        for event_id, event in entries:
            try:
                await sink.write([event])
            except EventRejected as exc:
                await self._park(event_id, str(exc))
            else:
                await self._db.delete_events([event_id])

    async def _park(self, event_id: int, error: str) -> None:
        log.error(
            "Journal entry %s refused and set aside: %s",
            event_id,
            error,
            extra={"operation": "journal_park"},
        )
        await self._db.park_event(event_id, error, int(time.time()))


# No conflict target on purpose. With `ON CONFLICT (update_id)` Postgres
# infers the arbiter index and needs SELECT on the column for that, and
# the writer may only insert. The table's one unique key is update_id,
# so any conflict here is a replayed update.
_INSERT = """
    INSERT INTO srm.membership_events (
        update_id, chat_id, chat_title, user_id, username, full_name,
        actor_id, actor_username, event, invite_link, invite_name,
        occurred_at
    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
    ON CONFLICT DO NOTHING
"""


class PostgresSink:
    """Writes entries to tg_parser's `srm.membership_events`.

    The role behind the DSN may only insert into that one table, so a
    leak of the bot's settings does not expose anybody's data.
    """

    def __init__(self, dsn: str, *, timeout: float = 10.0):
        self._dsn = dsn
        self._timeout = timeout
        self._conn: Any = None

    async def write(self, events: List[dict]) -> None:
        # Imported here: the bot runs without asyncpg while the journal is off.
        import asyncpg

        rows = [_row(event) for event in events]
        conn = await self._connection(asyncpg)
        try:
            async with conn.transaction():
                await conn.executemany(_INSERT, rows, timeout=self._timeout)
        except (asyncpg.DataError, asyncpg.IntegrityConstraintViolationError) as exc:
            raise EventRejected(str(exc)) from exc
        except BaseException:
            # The connection state is unknown now; the next write reconnects.
            self._conn = None
            conn.terminate()
            raise

    async def close(self) -> None:
        conn, self._conn = self._conn, None
        if conn is not None:
            with contextlib.suppress(Exception):
                await conn.close(timeout=self._timeout)

    async def _connection(self, asyncpg: Any) -> Any:
        if self._conn is None or self._conn.is_closed():
            self._conn = await asyncpg.connect(
                self._dsn,
                timeout=self._timeout,
                server_settings={"application_name": "fast_telegram_srm"},
            )
        return self._conn


def _row(event: dict) -> tuple:
    try:
        return (
            event["update_id"],
            event["chat_id"],
            event.get("chat_title"),
            event["user_id"],
            event.get("username"),
            event.get("full_name"),
            event.get("actor_id"),
            event.get("actor_username"),
            event["event"],
            event.get("invite_link"),
            event.get("invite_name"),
            datetime.fromisoformat(event["occurred_at"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise EventRejected(f"malformed entry: {exc!r}") from exc


async def record_quietly(journal: Optional[EventJournal], build: Callable[[], Optional[dict]]) -> None:
    """Journal an update without ever getting in the sheet's way.

    Building the entry happens here too, so an update of an unexpected
    shape fails in the journal, not in the handler that writes the sheet.
    """
    if journal is None:
        return
    try:
        event = build()
        if event is not None:
            await journal.record(event)
    except Exception:
        log.exception("Failed to journal a membership event", extra={"operation": "journal_record"})


async def run_delivery(
    journal: EventJournal,
    sink: _Sink,
    stop: asyncio.Event,
    *,
    idle_seconds: float = 2.0,
    max_backoff_seconds: float = 60.0,
    batch_size: int = 200,
) -> None:
    """Deliver the outbox until `stop` is set; outages only slow it down.

    Stopping finishes the batch in hand rather than cutting it off, so
    a shutdown does not leave a delivered entry behind in the outbox.
    """
    backoff = idle_seconds
    while not stop.is_set():
        try:
            settled = await journal.deliver_pending(sink, batch_size)
        except Exception as exc:
            log.warning(
                "Journal delivery failed, retrying in %.0fs: %s",
                backoff,
                exc,
                extra={"operation": "journal_delivery"},
            )
            await _pause(stop, backoff)
            backoff = min(backoff * 2, max_backoff_seconds)
            continue
        backoff = idle_seconds
        if settled < batch_size:
            await _pause(stop, idle_seconds)


async def _pause(stop: asyncio.Event, seconds: float) -> None:
    """Sleep, but wake up at once when asked to stop."""
    with contextlib.suppress(asyncio.TimeoutError):
        await asyncio.wait_for(stop.wait(), timeout=seconds)
