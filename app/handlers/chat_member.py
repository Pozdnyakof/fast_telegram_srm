from aiogram import Router, F
from aiogram.types import ChatMemberUpdated

router = Router(name=__name__)


@router.chat_member()
async def on_chat_member(update: ChatMemberUpdated):
    # Placeholder: will handle new member joined via invite link
    # Detailed filters and processing will be implemented in Stage 5
    pass
