"""Shared helpers — keep views/services free of one-off string/date/chunk logic."""

from __future__ import annotations

import math
import re
from datetime import date, datetime
from typing import Any, Iterable, Iterator, TypeVar
from uuid import UUID

from django.utils import timezone
from django.utils.dateparse import parse_datetime

T = TypeVar("T")

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def as_uuid(value: Any) -> UUID | None:
    if value is None or value == "":
        return None
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        return None


def parse_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on", "y"}


def parse_aware_datetime(value: Any, *, default: datetime | None = None) -> datetime | None:
    if value is None or value == "":
        return default
    if isinstance(value, datetime):
        dt = value
    else:
        dt = parse_datetime(str(value))
        if dt is None:
            return default
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt)
    return dt


def isoformat(value: datetime | date | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime) and timezone.is_aware(value):
        return value.isoformat()
    return value.isoformat()


def chunked(items: Iterable[T], size: int) -> Iterator[list[T]]:
    if size < 1:
        raise ValueError("size must be >= 1")
    batch: list[T] = []
    for item in items:
        batch.append(item)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


def clamp(n: float | int, lo: float | int, hi: float | int) -> float | int:
    return max(lo, min(hi, n))


def deep_get(data: dict | None, *keys: str, default: Any = None) -> Any:
    cur: Any = data or {}
    for key in keys:
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    return cur


def slugify(value: str, *, max_len: int = 64) -> str:
    s = _SLUG_RE.sub("-", (value or "").strip().lower()).strip("-")
    return s[:max_len]


def pages_for(total: int, page_size: int) -> int:
    if page_size < 1:
        return 0
    return int(math.ceil(total / page_size)) if total else 0
