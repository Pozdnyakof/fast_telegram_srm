"""The journal wired through aiogram itself, with real Telegram types.

The other tests use stand-ins, and this one checks what they assume:
that aiogram hands the handler the raw update, and with it the
update_id, and that real member statuses read the way the journal
expects them to.
"""

from datetime import datetime, timezone

import pytest
from aiogram import Bot, Dispatcher
from aiogram.types import Chat, ChatMemberLeft, ChatMemberMember, ChatMemberUpdated, Update, User

from app.handlers.chat_member import router as chat_member_router
from app.services.container import ServiceContainer, set_container


class _Sheets:
    async def ensure_sheet(self, title):
        return title

    async def append_row(self, title, row):
        pass


class _Journal:
    def __init__(self):
        self.events = []

    async def record(self, event):
        self.events.append(event)


@pytest.mark.asyncio
async def test_a_real_update_reaches_the_journal_whole(db):
    journal = _Journal()
    set_container(ServiceContainer(db=db, gsheets=_Sheets(), journal=journal))
    dispatcher = Dispatcher()
    dispatcher.include_router(chat_member_router)
    person = User(id=7175828896, is_bot=False, first_name="настькин", last_name="я", username="daneksosol")
    account = User(id=8421258155, is_bot=False, first_name="Xbdcnh")
    update = Update(
        update_id=155191255,
        chat_member=ChatMemberUpdated(
            chat=Chat(id=-1003158922677, type="channel", title="Хоккей в плюсе | VIP"),
            from_user=account,
            date=datetime(2026, 9, 10, 15, 1, 38, tzinfo=timezone.utc),
            old_chat_member=ChatMemberLeft(user=person),
            new_chat_member=ChatMemberMember(user=person),
        ),
    )
    bot = Bot(token="42:TEST")
    try:
        await dispatcher.feed_update(bot, update)
    finally:
        await bot.session.close()

    assert journal.events == [
        {
            "update_id": 155191255,
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
        },
    ]
