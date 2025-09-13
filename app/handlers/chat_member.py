import logging
from datetime import datetime, timezone
from aiogram import Router
from aiogram.types import ChatMemberUpdated

from ..services.container import get_container
from ..services.google_sheets import sanitize_sheet_title

router = Router(name=__name__)


@router.chat_member()
async def on_chat_member(update: ChatMemberUpdated):
    """Handle new member joins via invite link and write a row to Google Sheets."""
    chat = update.chat
    if chat is None or chat.type != "channel":
        return

    # Only when a user became "member" and joined via invite link
    new_status = update.new_chat_member.status if update.new_chat_member else None
    if new_status != "member":
        logging.getLogger(__name__).debug(
            "Ignoring chat_member: status=%s", new_status, extra={"channel_id": chat.id, "operation": "chat_member_skip"}
        )
        return
    if not update.invite_link:
        logging.getLogger(__name__).debug(
            "Ignoring chat_member without invite_link", extra={"channel_id": chat.id, "operation": "chat_member_skip"}
        )
        return

    channel_id = chat.id
    channel_title = chat.title or f"Channel {channel_id}"

    # Extract user info
    user = update.new_chat_member.user if update.new_chat_member else None
    if user is None:
        return

    full_name = getattr(user, "full_name", None) or ""
    username = f"@{user.username}" if getattr(user, "username", None) else ""

    invite_url = getattr(update.invite_link, "invite_link", "") or ""
    invite_name = getattr(update.invite_link, "name", "") or ""

    # Resolve sheet name from DB or create fallback
    container = get_container()
    sheet_name = await container.db.get_sheet_name(channel_id)
    if not sheet_name:
        # Fallback: ensure sheet by channel title and persist mapping
        sheet_title = sanitize_sheet_title(channel_title)
        sheet_name = await container.gsheets.ensure_sheet(sheet_title)
        await container.db.upsert_channel(channel_id, sheet_name)

    # Prepare row, timestamp in UTC
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    row = [
        ts,
        str(user.id),
        full_name,
        username,
        invite_url,
        invite_name,
    ]

    await container.gsheets.append_row(sheet_name, row)

    logging.getLogger(__name__).info(
        "Appended join event: sheet='%s'",
        sheet_name,
        extra={"channel_id": channel_id, "user_id": user.id, "operation": "chat_member_join"},
    )
