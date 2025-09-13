"""Ephemeral cache for join request metadata.

Stores recent (chat_id, user_id) -> (invite_url, invite_name) for a short TTL
so that when ChatMemberUpdated arrives after an approval, we can enrich the
row with the original invite link details.
"""
from __future__ import annotations

import time
from typing import Dict, Optional, Tuple
import logging


# key: (chat_id, user_id) -> value: (expires_at, invite_url, invite_name)
_cache: Dict[Tuple[int, int], Tuple[float, str, str]] = {}


def _prune(now: float | None = None) -> None:
    now = now or time.time()
    expired = [key for key, (exp, _u, _n) in _cache.items() if exp <= now]
    for key in expired:
        _cache.pop(key, None)


def remember(chat_id: int, user_id: int, invite_url: str, invite_name: str, ttl_seconds: int = 900) -> None:
    """Remember invite metadata for a limited time (default 15 minutes)."""
    now = time.time()
    _prune(now)
    _cache[(chat_id, user_id)] = (now + ttl_seconds, invite_url or "", invite_name or "")
    logging.getLogger(__name__).info(
        "Cached join request metadata (ttl=%ss)", ttl_seconds,
        extra={"channel_id": chat_id, "user_id": user_id, "operation": "join_cache_remember"},
    )


def pop(chat_id: int, user_id: int) -> Optional[Tuple[str, str]]:
    """Pop and return (invite_url, invite_name) if present and not expired."""
    now = time.time()
    _prune(now)
    val = _cache.pop((chat_id, user_id), None)
    if not val:
        return None
    exp, url, name = val
    if exp <= now:
        return None
    logging.getLogger(__name__).info(
        "Recovered cached invite metadata",
        extra={"channel_id": chat_id, "user_id": user_id, "operation": "join_cache_hit"},
    )
    return url, name
