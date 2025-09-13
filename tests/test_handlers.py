import os
import tempfile
import pytest

from app.handlers.chat_member import on_chat_member
from app.handlers.my_chat_member import on_my_chat_member
from app.services.container import set_container, ServiceContainer
from app.services.db import Database


class DummyUser:
    def __init__(self, user_id, full_name="John Doe", username=None):
        self.id = user_id
        self.full_name = full_name
        self.username = username


class DummyMember:
    def __init__(self, status, user=None):
        self.status = status
        self.user = user


class DummyChat:
    def __init__(self, chat_id, type_="channel", title="Test Channel"):
        self.id = chat_id
        self.type = type_
        self.title = title


class DummyInvite:
    def __init__(self, invite_link="https://t.me/+abc", name="Link A"):
        self.invite_link = invite_link
        self.name = name


class DummyUpdate:
    def __init__(self):
        self.chat = None
        self.old_chat_member = None
        self.new_chat_member = None
        self.invite_link = None


class FakeSheets:
    def __init__(self):
        self.appends = []
        self.ensure_calls = []

    async def ensure_sheet(self, title: str):
        self.ensure_calls.append(title)
        return title

    async def append_row(self, title: str, row):
        self.appends.append((title, row))


@pytest.mark.asyncio
async def test_my_chat_member_initializes_mapping():
    update = DummyUpdate()
    update.chat = DummyChat(chat_id=777, type_="channel", title="My Channel")
    update.old_chat_member = DummyMember(status="member")
    update.new_chat_member = DummyMember(status="administrator")

    sheets = FakeSheets()
    with tempfile.TemporaryDirectory() as tmp:
        db = Database(os.path.join(tmp, "t.db"))
        await db.init_db()
        set_container(ServiceContainer(db=db, gsheets=sheets))

        await on_my_chat_member(update)

        assert await db.get_sheet_name(777) == "My Channel"
        assert sheets.ensure_calls == ["My Channel"]


@pytest.mark.asyncio
async def test_chat_member_appends_row():
    update = DummyUpdate()
    update.chat = DummyChat(chat_id=555, type_="channel", title="Ch 555")
    update.new_chat_member = DummyMember(status="member", user=DummyUser(42, "Alice", "alice"))
    update.invite_link = DummyInvite(invite_link="https://t.me/+xyz", name="Promo")

    sheets = FakeSheets()
    with tempfile.TemporaryDirectory() as tmp:
        db = Database(os.path.join(tmp, "t.db"))
        await db.init_db()
        # Pre-init mapping
        await db.upsert_channel(555, "Ch 555")
        set_container(ServiceContainer(db=db, gsheets=sheets))

        await on_chat_member(update)

        assert len(sheets.appends) == 1
        sheet, row = sheets.appends[0]
        assert sheet == "Ch 555"
        assert row[1] == "42"  # user id as str
        assert row[2] == "Alice"
        assert row[3] == "@alice"
        assert row[4] == "https://t.me/+xyz"
        assert row[5] == "Promo"
