import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from aiogram import Router
from aiogram.types import ChatJoinRequest

from ..services.container import get_container
from ..services.google_sheets import sanitize_sheet_title
from ..config import get_settings
from ..utils import join_cache


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
    if getattr(update.invite_link, "creates_join_request", False) and not invite_name:
        invite_name = "(request link)"

    container = get_container()
    sheet_name = await container.db.get_sheet_name(channel_id)
    if not sheet_name:
        sheet_title = sanitize_sheet_title(channel_title)
        sheet_name = await container.gsheets.ensure_sheet(sheet_title)
        await container.db.upsert_channel(channel_id, sheet_name)

    # Deduplicate: skip if the same (channel_id, user_id) was logged within the last 12 hours
    try:
        last_logged = await container.db.get_last_join_request_logged_at(channel_id, user.id)
    except Exception as e:
        last_logged = None
        logging.getLogger(__name__).warning(
            "Failed to read dedup state: %s",
            e,
            extra={"channel_id": channel_id, "user_id": user.id, "operation": "chat_join_request_dedup"},
        )

    tz = ZoneInfo(get_settings().TIMEZONE)
    now_local = datetime.now(tz)
    ts = now_local.strftime("%Y-%m-%d %H:%M:%S")
    now_epoch = int(datetime.now(timezone.utc).timestamp())

    # If last_logged exists and is within 12 hours (43200 seconds), skip writing
    if last_logged is not None and (now_epoch - int(last_logged)) < 12 * 60 * 60:
        logging.getLogger(__name__).info(
            "Skipping join request (dedup 12h): already logged at %s",
            last_logged,
            extra={"channel_id": channel_id, "user_id": user.id, "operation": "chat_join_request_skip_dedup"},
        )
        # Refresh in-memory cache to ensure approval path is still recognized
        try:
            join_cache.remember(chat_id=channel_id, user_id=user.id, invite_url=invite_url, invite_name=invite_name)
        except Exception:
            pass
        return
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
    # Remember metadata for later ChatMemberUpdated after approval
    try:
        join_cache.remember(chat_id=channel_id, user_id=user.id, invite_url=invite_url, invite_name=invite_name)
    except Exception:
        logging.getLogger(__name__).warning(
            "Failed to cache join request metadata",
            extra={"channel_id": channel_id, "user_id": user.id, "operation": "chat_join_request"},
        )
    await container.gsheets.append_row(sheet_name, row)
    # Update dedup log timestamp
    try:
        await container.db.upsert_join_request_logged_at(channel_id, user.id, now_epoch)
    except Exception as e:
        logging.getLogger(__name__).warning(
            "Failed to update dedup state: %s",
            e,
            extra={"channel_id": channel_id, "user_id": user.id, "operation": "chat_join_request_dedup"},
        )
    logging.getLogger(__name__).info(
        "Appended join request: sheet='%s'",
        sheet_name,
        extra={"channel_id": channel_id, "user_id": user.id, "operation": "chat_join_request"},
    )
