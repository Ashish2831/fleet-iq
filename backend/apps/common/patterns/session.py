"""Session storage strategy — pluggable backends for session metadata."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4


class SessionData(dict):
    """JSON-serializable session payload."""


class SessionStorage(ABC):
    @abstractmethod
    def create(self, data: dict[str, Any], *, ttl_seconds: int = 86400) -> str: ...

    @abstractmethod
    def get(self, session_id: str) -> SessionData | None: ...

    @abstractmethod
    def delete(self, session_id: str) -> None: ...

    @abstractmethod
    def touch(self, session_id: str, *, ttl_seconds: int = 86400) -> bool: ...


class MemorySessionStorage(SessionStorage):
    def __init__(self):
        self._rows: dict[str, tuple[SessionData, datetime]] = {}

    def create(self, data: dict[str, Any], *, ttl_seconds: int = 86400) -> str:
        sid = str(uuid4())
        expires = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
        self._rows[sid] = (SessionData(data), expires)
        return sid

    def get(self, session_id: str) -> SessionData | None:
        row = self._rows.get(session_id)
        if not row:
            return None
        payload, expires = row
        if expires < datetime.now(timezone.utc):
            self._rows.pop(session_id, None)
            return None
        return payload

    def delete(self, session_id: str) -> None:
        self._rows.pop(session_id, None)

    def touch(self, session_id: str, *, ttl_seconds: int = 86400) -> bool:
        payload = self.get(session_id)
        if payload is None:
            return False
        expires = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
        self._rows[session_id] = (payload, expires)
        return True


class CacheSessionStorage(SessionStorage):
    prefix = "fq:session:"

    def create(self, data: dict[str, Any], *, ttl_seconds: int = 86400) -> str:
        from django.core.cache import cache

        sid = str(uuid4())
        cache.set(self.prefix + sid, dict(data), timeout=ttl_seconds)
        return sid

    def get(self, session_id: str) -> SessionData | None:
        from django.core.cache import cache

        raw = cache.get(self.prefix + session_id)
        return SessionData(raw) if isinstance(raw, dict) else None

    def delete(self, session_id: str) -> None:
        from django.core.cache import cache

        cache.delete(self.prefix + session_id)

    def touch(self, session_id: str, *, ttl_seconds: int = 86400) -> bool:
        payload = self.get(session_id)
        if payload is None:
            return False
        from django.core.cache import cache

        cache.set(self.prefix + session_id, dict(payload), timeout=ttl_seconds)
        return True


def default_session_storage() -> SessionStorage:
    try:
        from django.core.cache import cache

        cache.get("fq-session-probe")
        return CacheSessionStorage()
    except Exception:
        return MemorySessionStorage()
