from aiogram import Router, F
from aiogram.types import ChatMemberUpdated

router = Router(name=__name__)


@router.my_chat_member()
async def on_my_chat_member(update: ChatMemberUpdated):
    # Placeholder: will handle when bot is added/removed or rights change
    # Narrow filter will be added in Stage 4
    pass
