"""The journal rides along the handlers without changing the sheet.

The sheet is what the client sees and must stay exactly as it was: the
same rows and the same skips. The journal sees more: leaves, removals,
joins the sheet skips on purpose. And whatever goes wrong with the
journal, the sheet row still gets written.
"""

from datetime import datetime, timezone

import pytest

from app.config import get_settings
from app.handlers.chat_join_request import on_chat_join_request
from app.handlers.chat_member import on_chat_member
from app.services.container import ServiceContainer, set_container

_CHAT_ID = -1003158922677
_OUR_ACCOUNT_ID = 8421258155


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
    creates_join_request = False


class _MemberUpdate:
    def __init__(self, old, new, user, actor, invite=None, via_join_request=False):
        self.chat = _Chat()
        self.old_chat_member = _Member(old, user)
        self.new_chat_member = _Member(new, user)
        self.from_user = actor
        self.invite_link = invite
        self.via_join_request = via_join_request
        self.date = datetime(2026, 9, 10, 15, 1, 38, tzinfo=timezone.utc)


class _Request:
    def __init__(self, user):
        self.chat = _Chat()
        self.from_user = user
        self.invite_link = _Invite()
        self.date = datetime(2026, 9, 10, 15, 0, 0, tzinfo=timezone.utc)


class _RawUpdate:
    update_id = 155191255


class _Sheets:
    def __init__(self):
        self.appends = []

    async def ensure_sheet(self, title):
        return title

    async def append_row(self, title, row):
        self.appends.append((title, row))


class _Journal:
    def __init__(self):
        self.events = []

    async def record(self, event):
        self.events.append(event)


class _BrokenJournal:
    async def record(self, event):
        raise OSError("disk I/O error")


@pytest.fixture()
def settings(monkeypatch):
    """Pin what the sheet's skip rules read, whatever the local .env says."""
    def pin(**values):
        for key, value in values.items():
            monkeypatch.setenv(key, value)
        get_settings.cache_clear()

    yield pin
    get_settings.cache_clear()


async def _serve(db, journal):
    await db.upsert_channel(_CHAT_ID, "Sheet")
    sheets = _Sheets()
    set_container(ServiceContainer(db=db, gsheets=sheets, journal=journal))
    return sheets


def _joined_by_link(user_id):
    user = _User(user_id)
    return _MemberUpdate("left", "member", user, actor=user, invite=_Invite())


@pytest.mark.asyncio
async def test_a_join_by_link_goes_to_both_the_sheet_and_the_journal(db):
    journal = _Journal()
    sheets = await _serve(db, journal)

    await on_chat_member(_joined_by_link(42), event_update=_RawUpdate())

    assert len(sheets.appends) == 1
    assert [(e["event"], e["invite_name"]) for e in journal.events] == [("join", "Promo")]


@pytest.mark.asyncio
async def test_the_sheet_row_is_the_same_with_the_journal_on_or_off(db):
    rows = []
    for journal in (None, _Journal()):
        sheets = await _serve(db, journal)
        await on_chat_member(_joined_by_link(43), event_update=_RawUpdate())
        sheet, row = sheets.appends[0]
        rows.append((sheet, row[1:]))  # all but the time of writing

    assert rows[0] == rows[1]


@pytest.mark.asyncio
async def test_a_direct_add_is_journaled_though_the_sheet_skips_it(db, settings):
    """How the server is set up: joins without a link stay out of the sheet.

    Our accounts add people directly, with no link, so the client's sheet
    never shows these joins. The journal is where they are confirmed.
    """
    settings(LOG_JOINS_WITHOUT_INVITE="false")
    journal = _Journal()
    sheets = await _serve(db, journal)
    update = _MemberUpdate(
        "left", "member", _User(48), actor=_User(_OUR_ACCOUNT_ID, "Xbdcnh", None),
    )

    await on_chat_member(update, event_update=_RawUpdate())

    assert sheets.appends == []
    assert [(e["event"], e["user_id"], e["actor_id"]) for e in journal.events] == [
        ("join", 48, _OUR_ACCOUNT_ID),
    ]


@pytest.mark.asyncio
async def test_leaving_is_journaled_while_the_sheet_is_left_alone(db):
    journal = _Journal()
    sheets = await _serve(db, journal)
    update = _MemberUpdate("member", "left", _User(44), actor=_User(44))

    await on_chat_member(update, event_update=_RawUpdate())

    assert sheets.appends == []
    assert [e["event"] for e in journal.events] == ["left"]


@pytest.mark.asyncio
async def test_an_approved_request_is_journaled_as_a_join_though_the_sheet_skips_it(db):
    """The sheet logged the request already; the journal needs the join."""
    journal = _Journal()
    sheets = await _serve(db, journal)
    update = _MemberUpdate(
        "left", "member", _User(45), actor=_User(1), via_join_request=True,
    )

    await on_chat_member(update, event_update=_RawUpdate())

    assert sheets.appends == []
    assert [e["event"] for e in journal.events] == ["join"]


@pytest.mark.asyncio
async def test_a_broken_journal_does_not_stop_the_sheet(db):
    sheets = await _serve(db, _BrokenJournal())

    await on_chat_member(_joined_by_link(46), event_update=_RawUpdate())

    assert len(sheets.appends) == 1


@pytest.mark.asyncio
async def test_a_join_request_goes_to_both_the_sheet_and_the_journal(db):
    journal = _Journal()
    sheets = await _serve(db, journal)

    await on_chat_join_request(_Request(_User(47)), event_update=_RawUpdate())

    assert len(sheets.appends) == 1
    assert [e["event"] for e in journal.events] == ["request"]
