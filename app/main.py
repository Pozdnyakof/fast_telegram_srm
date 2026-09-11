import asyncio
import contextlib
import logging
from typing import AsyncIterator, Optional

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode

from .config import get_settings
from .logging_config import setup_logging
from .handlers.my_chat_member import router as my_chat_member_router
from .handlers.chat_member import router as chat_member_router
from .handlers.chat_join_request import router as chat_join_request_router
from .services.container import ServiceContainer, set_container
from .services.db import Database
from .services.google_sheets import create_google_sheets_service_from_settings
from .services.journal import EventJournal, PostgresSink, run_delivery


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

    # Aiogram 3.7+ moved default properties to DefaultBotProperties
    try:
        from aiogram.client.default import DefaultBotProperties  # type: ignore
    except ImportError:
        DefaultBotProperties = None  # type: ignore

    session = None
    if settings.TELEGRAM_PROXY:
        from aiogram.client.session.aiohttp import AiohttpSession
        session = AiohttpSession(proxy=settings.TELEGRAM_PROXY)
        masked = settings.TELEGRAM_PROXY.split("@")[-1]
        logging.getLogger(__name__).info("Telegram API via HTTP proxy: %s", masked)

    if DefaultBotProperties:
        bot = Bot(
            token=settings.BOT_TOKEN,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
            session=session,
        )
    else:
        # Fallback for older Aiogram versions (<3.7)
        bot = Bot(token=settings.BOT_TOKEN, parse_mode=ParseMode.HTML, session=session)
    dp = Dispatcher()

    # Basic error logging handler (Aiogram 3.x ErrorEvent)
    @dp.errors()
    async def errors_handler(event):  # type: ignore[no-redef]
        # event is ErrorEvent in Aiogram 3.x and has .exception and .update
        exception = getattr(event, "exception", None)
        update = getattr(event, "update", None)
        extra = {}
        try:
            msg = getattr(update, "message", None) or getattr(update, "callback_query", None)
            chat = getattr(getattr(msg, "chat", None), "id", None) or getattr(getattr(update, "chat", None), "id", None)
            if chat:
                extra["channel_id"] = chat
            user = getattr(getattr(msg, "from_user", None), "id", None) or getattr(getattr(update, "from_user", None), "id", None)
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
    dp.include_router(chat_join_request_router)

    # Initialize services and set container
    db = Database(settings.DB_PATH)
    await db.init_db()
    gsheets = create_google_sheets_service_from_settings(settings)
    if settings.GSHEETS_SELF_CHECK:
        try:
            await gsheets.health_check()
        except Exception as e:
            logging.getLogger(__name__).exception("Google Sheets self-check failed: %s", e)
            # proceed to run to allow transient errors to resolve via backoff
    journal = EventJournal(db) if settings.EVENT_JOURNAL_DSN else None
    set_container(ServiceContainer(db=db, gsheets=gsheets, journal=journal))

    logging.getLogger(__name__).info("Starting bot polling...")
    async with journal_delivery(journal, settings.EVENT_JOURNAL_DSN):
        await dp.start_polling(bot)


@contextlib.asynccontextmanager
async def journal_delivery(
    journal: Optional[EventJournal], dsn: Optional[str], stop_timeout: float = 30.0
) -> AsyncIterator[None]:
    """Deliver the journal in the background for as long as the bot polls."""
    if journal is None or not dsn:
        logging.getLogger(__name__).info("Membership journal is off (EVENT_JOURNAL_DSN is not set)")
        yield
        return
    sink = PostgresSink(dsn)
    stop = asyncio.Event()
    delivery = asyncio.create_task(run_delivery(journal, sink, stop), name="journal-delivery")
    logging.getLogger(__name__).info("Membership journal is on")
    try:
        yield
    finally:
        stop.set()
        try:
            await asyncio.wait_for(delivery, timeout=stop_timeout)
        except asyncio.TimeoutError:
            logging.getLogger(__name__).warning(
                "Journal delivery did not stop in time; undelivered entries wait in the outbox"
            )
        await sink.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.getLogger(__name__).info("Bot stopped")
