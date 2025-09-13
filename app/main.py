import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode

from .config import get_settings
from .logging import setup_logging
from .handlers.my_chat_member import router as my_chat_member_router
from .handlers.chat_member import router as chat_member_router


async def main() -> None:
    settings = get_settings()
    setup_logging(settings.LOG_LEVEL)

    if not settings.BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not set. Please configure your .env or environment variables.")

    bot = Bot(token=settings.BOT_TOKEN, parse_mode=ParseMode.HTML)
    dp = Dispatcher()

    # Register routers
    dp.include_router(my_chat_member_router)
    dp.include_router(chat_member_router)

    logging.getLogger(__name__).info("Starting bot polling...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.getLogger(__name__).info("Bot stopped")
