from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .db import Database
from .google_sheets import GoogleSheetsService
from .journal import EventJournal


@dataclass
class ServiceContainer:
    db: Database
    gsheets: GoogleSheetsService
    # None while EVENT_JOURNAL_DSN is unset: membership changes are not journaled.
    journal: Optional[EventJournal] = None


_container: Optional[ServiceContainer] = None


def set_container(container: ServiceContainer) -> None:
    global _container
    _container = container


def get_container() -> ServiceContainer:
    if _container is None:
        raise RuntimeError("Service container is not initialized")
    return _container
