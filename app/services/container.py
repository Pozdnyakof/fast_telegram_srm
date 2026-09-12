from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .db import Database
from .google_sheets import GoogleSheetsService
from .journal import EventJournal
from .our_accounts import OurAccounts


@dataclass
class ServiceContainer:
    db: Database
    gsheets: GoogleSheetsService
    # None while EVENT_JOURNAL_DSN is unset: membership changes are not journaled.
    journal: Optional[EventJournal] = None
    # None while EVENT_JOURNAL_DSN is unset: our own accounts cannot be told
    # apart from other admins, so their direct adds are not written to the sheet.
    our_accounts: Optional[OurAccounts] = None


_container: Optional[ServiceContainer] = None


def set_container(container: ServiceContainer) -> None:
    global _container
    _container = container


def get_container() -> ServiceContainer:
    if _container is None:
        raise RuntimeError("Service container is not initialized")
    return _container
