import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram import Router
from aiogram.types import ChatJoinRequest

from ..services.container import get_container
from ..services.google_sheets import sanitize_sheet_title
from ..config import get_settings


router = Router(name=__name__)


@router.chat_join_request()
async def on_chat_join_request(update: ChatJoinRequest):
    """Handle join requests (channels with approval). Write a row to Google Sheets."""
    chat = update.chat
    if chat is None or chat.type not in ("channel", "supergroup"):
        return

    user = update.from_user
    if user is None:
        return

    channel_id = chat.id
    channel_title = chat.title or f"Channel {channel_id}"

    full_name = getattr(user, "full_name", None) or ""
    username = f"@{user.username}" if getattr(user, "username", None) else ""

    invite_url = getattr(update.invite_link, "invite_link", "") or ""
    invite_name = getattr(update.invite_link, "name", "") or ""

    container = get_container()
    sheet_name = await container.db.get_sheet_name(channel_id)
    if not sheet_name:
        sheet_title = sanitize_sheet_title(channel_title)
        sheet_name = await container.gsheets.ensure_sheet(sheet_title)
        await container.db.upsert_channel(channel_id, sheet_name)

    tz = ZoneInfo(get_settings().TIMEZONE)
    ts = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")
    row = [
        ts,
        str(user.id),
        full_name,
        username,
        invite_url,
        invite_name or "(request)",
    ]

    logging.getLogger(__name__).info(
        "Appending join request to sheet='%s'...",
        sheet_name,
        extra={"channel_id": channel_id, "user_id": user.id, "operation": "chat_join_request"},
    )
    await container.gsheets.append_row(sheet_name, row)
    logging.getLogger(__name__).info(
        "Appended join request: sheet='%s'",
        sheet_name,
        extra={"channel_id": channel_id, "user_id": user.id, "operation": "chat_join_request"},
    )
