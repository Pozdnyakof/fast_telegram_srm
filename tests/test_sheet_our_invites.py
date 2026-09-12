"""Our direct-add invites land in the client sheet, without touching it.

The sheet's structure does not change: same channel sheets, same six
columns. Where a link join puts its invite link, our direct add puts
the inviting account (its @username or id) — so the client sees who
added the person. Only our own accounts are written this way; another
admin's add is still skipped (LOG_JOINS_WITHOUT_INVITE stays false).
"""

from datetime import datetime, timezone

import pytest

from app.config import get_settings
from app.handlers.chat_member import on_chat_member
from app.services.container import ServiceContainer, set_container

pytestmark = pytest.mark.asyncio

_CHAT_ID = -1003158922677
_OUR_ID = 8535014750


class _User:
    def __init__(self, user_id, full_name="Alice", username="alice"):
        self.id = user_id
        self.full_name = full_name
        self.username = username


class _Member:
    def __init__(self, status, user):
        self.status = status
        self.user = user


class _Chat:
    id = _CHAT_ID
    type = "channel"
    title = "Хоккей в плюсе | VIP"


class _Invite:
    invite_link = "https://t.me/+xyz"
    name = "Promo"


class _Update:
    def __init__(self, user, actor, invite=None):
        self.chat = _Chat()
        self.old_chat_member = _Member("left", user)
        self.new_chat_member = _Member("member", user)
        self.from_user = actor
        self.invite_link = invite
        self.via_join_request = False
        self.date = datetime(2026, 9, 12, 10, 0, tzinfo=timezone.utc)


class _RawUpdate:
    update_id = 1


class _Sheets:
    def __init__(self):
        self.appends = []

    async def ensure_sheet(self, title):
        return title

    async def append_row(self, title, row):
        self.appends.append((title, row))


class _OurAccounts:
    def __init__(self, ids):
        self._ids = set(ids)

    def contains(self, tg_user_id):
        return tg_user_id in self._ids


@pytest.fixture(autouse=True)
def _sheet_skips_no_link(monkeypatch):
    """Server setting: joins without a link are not logged on their own."""
    monkeypatch.setenv("LOG_JOINS_WITHOUT_INVITE", "false")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


async def _serve(db, *, our_ids=(_OUR_ID,)):
    await db.upsert_channel(_CHAT_ID, "VIP")
    sheets = _Sheets()
    set_container(
        ServiceContainer(
            db=db, gsheets=sheets, journal=None, our_accounts=_OurAccounts(our_ids),
        ),
    )
    return sheets


def _row(sheets):
    assert len(sheets.appends) == 1
    return sheets.appends[0][1]


async def test_our_account_add_is_logged_with_its_username_in_the_link_column(db):
    sheets = await _serve(db)
    actor = _User(_OUR_ID, "Account GM", "our_gm")
    person = _User(7175828896, "настькин я", "daneksosol")

    await on_chat_member(_Update(person, actor=actor), event_update=_RawUpdate())

    row = _row(sheets)
    assert row[1] == "7175828896"  # invited person's id
    assert row[3] == "@daneksosol"  # invited person's username
    assert row[4] == "@our_gm"  # inviter goes where the link would be
    assert row[5] == ""  # link name stays empty, no "(no invite)"


async def test_an_account_without_a_username_is_logged_by_id(db):
    sheets = await _serve(db)
    actor = _User(_OUR_ID, "Account GM", username=None)

    await on_chat_member(
        _Update(_User(42), actor=actor), event_update=_RawUpdate(),
    )

    assert _row(sheets)[4] == str(_OUR_ID)


async def test_an_add_by_a_stranger_admin_is_not_logged(db):
    """Only our accounts are written; another admin's add is skipped."""
    sheets = await _serve(db)
    stranger = _User(999000, "Client Admin", "client_admin")

    await on_chat_member(
        _Update(_User(42), actor=stranger), event_update=_RawUpdate(),
    )

    assert sheets.appends == []


async def test_a_link_join_is_unchanged(db):
    """A real invite link still lands in the link column, not the actor."""
    sheets = await _serve(db)
    person = _User(42)  # a link join: from_user is the joiner themselves

    await on_chat_member(
        _Update(person, actor=person, invite=_Invite()),
        event_update=_RawUpdate(),
    )

    row = _row(sheets)
    assert row[4] == "https://t.me/+xyz"
    assert row[5] == "Promo"


async def test_with_the_registry_off_a_no_link_join_is_still_skipped(db):
    """No our-accounts registry (journal off) → old behaviour holds."""
    await db.upsert_channel(_CHAT_ID, "VIP")
    sheets = _Sheets()
    set_container(ServiceContainer(db=db, gsheets=sheets, journal=None))
    actor = _User(_OUR_ID, "Account GM", "our_gm")

    await on_chat_member(
        _Update(_User(42), actor=actor), event_update=_RawUpdate(),
    )

    assert sheets.appends == []
