import logging
from aiogram import Router
from aiogram.types import ChatMemberUpdated

from ..services.container import get_container
from ..services.google_sheets import sanitize_sheet_title

router = Router(name=__name__)


@router.my_chat_member()
async def on_my_chat_member(update: ChatMemberUpdated):
    """Handle when bot's status changes in a chat (e.g., added as admin to a channel)."""
    # We only care about channels and when the bot becomes an administrator or member
    chat = update.chat
    if chat is None or chat.type not in {"channel"}:
        return

    old_status = update.old_chat_member.status if update.old_chat_member else None
    new_status = update.new_chat_member.status if update.new_chat_member else None

    # Proceed only when bot becomes administrator in the channel (strict per plan)
    if new_status != "administrator" or old_status == "administrator":
        return

    channel_id = chat.id
    channel_title = chat.title or f"Channel {channel_id}"

    container = get_container()

    # Check mapping in DB first
    existing = await container.db.get_sheet_name(channel_id)
    if existing:
        logging.getLogger(__name__).info(
            "Channel already initialized: channel_id=%s -> sheet='%s'", channel_id, existing
        )
        return

    # Ensure a sheet exists for this channel; use channel title (sanitized)
    sheet_title = sanitize_sheet_title(channel_title)
    final_title = await container.gsheets.ensure_sheet(sheet_title)

    # Save mapping in the local DB
    await container.db.upsert_channel(channel_id=channel_id, sheet_name=final_title)

    logging.getLogger(__name__).info(
        "Initialized channel mapping: channel_id=%s -> sheet='%s'", channel_id, final_title
    )
