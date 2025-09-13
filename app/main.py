import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode

from .config import get_settings
from .logging_config import setup_logging
from .handlers.my_chat_member import router as my_chat_member_router
from .handlers.chat_member import router as chat_member_router
from .services.container import ServiceContainer, set_container
from .services.db import Database
from .services.google_sheets import create_google_sheets_service_from_settings


async def main() -> None:
    settings = get_settings()
    setup_logging(settings.LOG_LEVEL)

    # Optional: Sentry init
    if settings.SENTRY_DSN:
        try:
            import sentry_sdk  # type: ignore
            sentry_sdk.init(dsn=settings.SENTRY_DSN, traces_sample_rate=0.0)
            logging.getLogger(__name__).info("Sentry initialized")
        except Exception as e:
            logging.getLogger(__name__).warning("Sentry init failed: %s", e)

    if not settings.BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not set. Please configure your .env or environment variables.")

    bot = Bot(token=settings.BOT_TOKEN, parse_mode=ParseMode.HTML)
    dp = Dispatcher()

    # Basic error logging middleware
    @dp.errors()
    async def errors_handler(update, exception):  # type: ignore[no-redef]
        extra = {}
        try:
            chat = getattr(update, "chat", None) or getattr(getattr(update, "message", None), "chat", None)
            if chat and getattr(chat, "id", None):
                extra["channel_id"] = getattr(chat, "id")
            user = getattr(getattr(update, "from_user", None), "id", None)
            if user:
                extra["user_id"] = user
        except Exception:
            pass
        extra["operation"] = "errors_handler"
        logging.getLogger(__name__).exception(
            "Unhandled exception in update handler: %s", exception, extra=extra
        )
        return True

    # Register routers
    dp.include_router(my_chat_member_router)
    dp.include_router(chat_member_router)

    # Initialize services and set container
    db = Database(settings.DB_PATH)
    await db.init_db()
    gsheets = create_google_sheets_service_from_settings(settings)
    set_container(ServiceContainer(db=db, gsheets=gsheets))

    logging.getLogger(__name__).info("Starting bot polling...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.getLogger(__name__).info("Bot stopped")
