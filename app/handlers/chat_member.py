import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from aiogram import Router
from aiogram.types import ChatMemberUpdated

from ..services.container import get_container
from ..services.google_sheets import sanitize_sheet_title
from ..utils import join_cache

router = Router(name=__name__)


@router.chat_member()
async def on_chat_member(update: ChatMemberUpdated):
    """Handle new member joins via invite link and write a row to Google Sheets."""
    chat = update.chat
    if chat is None or chat.type not in ("channel", "supergroup"):
        logging.getLogger(__name__).info(
            "Skipping chat_member: unsupported chat type %s",
            getattr(chat, "type", None),
            extra={"operation": "chat_member_skip", "channel_id": getattr(chat, "id", None)},
        )
        return

    # Only when a user became "member" and joined via invite link
    new_status = update.new_chat_member.status if update.new_chat_member else None
    if new_status != "member":
        logging.getLogger(__name__).info(
            "Skipping chat_member: new_status=%s",
            new_status,
            extra={"channel_id": chat.id, "operation": "chat_member_skip"},
        )
        return
    # Extract user info early to use for de-duplication checks
    user = update.new_chat_member.user if update.new_chat_member else None
    if user is None:
        return
    # If this membership event is an approval of a previously submitted join request,
    # we do NOT log it to avoid duplicate rows (join request was already recorded).
    if getattr(update, "via_join_request", False):
        logging.getLogger(__name__).info(
            "Skipping chat_member: approval of join request (already logged at request time)",
            extra={"channel_id": chat.id, "user_id": getattr(user, "id", None), "operation": "chat_member_skip_join_request"},
        )
        return
    # Additionally, if we have a recent cached join request for this user in this chat,
    # treat this as the approval path and skip logging to avoid duplicates even if the flag is absent.
    if join_cache.pop(chat.id, user.id):
        logging.getLogger(__name__).info(
            "Skipping chat_member: matched cached join request (avoiding duplicate)",
            extra={"channel_id": chat.id, "user_id": user.id, "operation": "chat_member_skip_cached_request"},
        )
        return
    # Determine whether this is an invite-based join.
    # Bot API: invite_link present when user joins via link; via_join_request indicates approved request without link in this update;
    # via_chat_folder_invite_link indicates join via folder-wide link (no per-link name).
    invite_based = bool(update.invite_link) or getattr(update, "via_join_request", False) or getattr(update, "via_chat_folder_invite_link", False)
    if not invite_based:
        from ..config import get_settings
        if not get_settings().LOG_JOINS_WITHOUT_INVITE:
            logging.getLogger(__name__).info(
                "Skipping chat_member: no invite_link (user didn't join via invite link)",
                extra={"channel_id": chat.id, "operation": "chat_member_skip"},
            )
            return

    channel_id = chat.id
    channel_title = chat.title or f"Channel {channel_id}"

    full_name = getattr(user, "full_name", None) or ""
    username = f"@{user.username}" if getattr(user, "username", None) else ""

    invite_url = getattr(update.invite_link, "invite_link", "") or ""
    invite_name = getattr(update.invite_link, "name", "") or ""

    # Join request approvals are skipped above; no need to recover cached metadata here.
    # If joined via chat folder invite link, annotate for clarity
    if getattr(update, "via_chat_folder_invite_link", False) and not invite_name:
        invite_name = "(folder invite)"
    if not invite_url and not invite_name:
        invite_name = "(no invite)"

    # Resolve sheet name from DB or create fallback
    container = get_container()
    sheet_name = await container.db.get_sheet_name(channel_id)
    if not sheet_name:
        # Fallback: ensure sheet by channel title and persist mapping
        sheet_title = sanitize_sheet_title(channel_title)
        sheet_name = await container.gsheets.ensure_sheet(sheet_title)
        await container.db.upsert_channel(channel_id, sheet_name)

    # Prepare row, timestamp in configured timezone (default Europe/Moscow)
    from ..config import get_settings
    tz = ZoneInfo(get_settings().TIMEZONE)
    ts = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")
    # Diagnostics for invite-related flags
    logging.getLogger(__name__).info(
        "Join flags: has_invite_link=%s, via_join_request=%s, via_chat_folder_invite_link=%s",
        bool(update.invite_link),
        getattr(update, "via_join_request", False),
        getattr(update, "via_chat_folder_invite_link", False),
        extra={"channel_id": channel_id, "user_id": user.id, "operation": "chat_member_flags"},
    )
    row = [
        ts,
        str(user.id),
        full_name,
        username,
        invite_url,
        invite_name,
    ]

    logging.getLogger(__name__).info(
        "Appending join event to sheet='%s'...",
        sheet_name,
        extra={"channel_id": channel_id, "user_id": user.id, "operation": "chat_member_prepare"},
    )

    await container.gsheets.append_row(sheet_name, row)

    logging.getLogger(__name__).info(
        "Appended join event: sheet='%s'",
        sheet_name,
        extra={"channel_id": channel_id, "user_id": user.id, "operation": "chat_member_join"},
    )
