"""Tests for the in-memory registry of our tg_parser account ids.

The bot writes our invites into the client sheet and must tell our own
accounts from other admins. The set of our Telegram ids lives in
tg_parser; the bot loads it, keeps it in memory, and refreshes it in
the background so the sheet path never waits on Postgres.
"""

import asyncio

import pytest

from app.services.our_accounts import OurAccounts


class _Source:
    """Stands in for the Postgres view; can be slow or broken."""

    def __init__(self, ids, *, fail=False):
        self.ids = ids
        self.fail = fail
        self.calls = 0

    async def __call__(self):
        self.calls += 1
        if self.fail:
            raise ConnectionRefusedError("postgres is down")
        return set(self.ids)


@pytest.mark.asyncio
async def test_before_a_load_it_owns_no_one():
    """Empty until first load: better to miss a row than mislabel one."""
    accounts = OurAccounts(_Source([1, 2]))

    assert accounts.contains(1) is False


@pytest.mark.asyncio
async def test_a_refresh_makes_the_set_current():
    accounts = OurAccounts(_Source([8421258155, 860514564]))

    await accounts.refresh()

    assert accounts.contains(8421258155) is True
    assert accounts.contains(999) is False


@pytest.mark.asyncio
async def test_a_failed_refresh_keeps_the_last_known_set():
    """A Postgres outage must not blank the registry mid-run."""
    source = _Source([1, 2])
    accounts = OurAccounts(source)
    await accounts.refresh()

    source.fail = True
    await accounts.refresh()  # must not raise

    assert accounts.contains(1) is True


@pytest.mark.asyncio
async def test_the_first_refresh_failing_leaves_it_empty_not_crashed():
    accounts = OurAccounts(_Source([], fail=True))

    await accounts.refresh()

    assert accounts.contains(1) is False


@pytest.mark.asyncio
async def test_the_background_loop_refreshes_then_stops_cleanly():
    source = _Source([7])
    accounts = OurAccounts(source, interval_seconds=0.01)
    stop = asyncio.Event()

    task = asyncio.create_task(accounts.run(stop))
    for _ in range(200):
        if accounts.contains(7):
            break
        await asyncio.sleep(0.01)
    stop.set()
    await asyncio.wait_for(task, timeout=2)

    assert accounts.contains(7) is True
