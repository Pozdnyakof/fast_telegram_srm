"""In-memory registry of our tg_parser accounts' Telegram ids.

The bot dishes our invites into the client sheet and must tell our own
accounts from other admins. The authoritative set lives in tg_parser
(accounts.tg_user_id), exposed to the bot as the read-only view
`srm.our_account_ids`. The bot loads it into memory and refreshes it on
a timer, so deciding "is this one of ours?" on the hot sheet path is a
plain set lookup that never waits on Postgres.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Awaitable, Callable, Optional, Set

log = logging.getLogger(__name__)

# How the set is fetched: a coroutine returning the current ids.
Source = Callable[[], Awaitable[Set[int]]]


class OurAccounts:
    def __init__(self, source: Source, *, interval_seconds: float = 300.0):
        self._source = source
        self._interval = interval_seconds
        # Empty until the first successful load: missing a row beats
        # mislabelling someone else's add as ours.
        self._ids: frozenset[int] = frozenset()
        self._loaded = False

    def contains(self, tg_user_id: Optional[int]) -> bool:
        return tg_user_id is not None and tg_user_id in self._ids

    async def refresh(self) -> None:
        """Reload the set; on failure keep the last known one."""
        try:
            ids = await self._source()
        except Exception:
            log.warning(
                "Could not refresh our-account ids; keeping the last set",
                extra={"operation": "our_accounts_refresh"},
            )
            return
        self._ids = frozenset(ids)
        self._loaded = True

    async def run(self, stop: asyncio.Event) -> None:
        """Refresh now, then every interval, until asked to stop."""
        while not stop.is_set():
            await self.refresh()
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=self._interval)


def dsn_source(dsn: str, *, timeout: float = 10.0) -> Source:
    """A Source that reads `srm.our_account_ids` from tg_parser's Postgres."""

    async def _load() -> Set[int]:
        import asyncpg

        conn = await asyncpg.connect(dsn, timeout=timeout)
        try:
            rows = await conn.fetch(
                "SELECT tg_user_id FROM srm.our_account_ids", timeout=timeout,
            )
        finally:
            await conn.close(timeout=timeout)
        return {int(row["tg_user_id"]) for row in rows}

    return _load
