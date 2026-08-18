from __future__ import annotations

import uuid
from datetime import datetime, timezone

from apps.events.context import get_correlation_id
from apps.events.topics import TOPIC_BY_EVENT


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def envelope(
    *,
    event_type: str,
    tenant_id,
    aggregate_type: str,
    aggregate_id,
    payload: dict,
    event_id=None,
    occurred_at: datetime | None = None,
    correlation_id: str | None = None,
    causation_id: str | None = None,
    event_version: int = 1,
) -> dict:
    return {
        "event_id": str(event_id or uuid.uuid4()),
        "event_type": event_type,
        "event_version": event_version,
        "occurred_at": (occurred_at or utcnow()).isoformat(),
        "tenant_id": str(tenant_id),
        "aggregate_type": aggregate_type,
        "aggregate_id": str(aggregate_id),
        "correlation_id": correlation_id or get_correlation_id(),
        "causation_id": causation_id,
        "payload": payload,
    }


def topic_for(event_type: str) -> str:
    try:
        return TOPIC_BY_EVENT[event_type]
    except KeyError as exc:
        raise ValueError(f"Unknown event_type {event_type}") from exc


def kafka_headers(env: dict) -> list[tuple[str, bytes]]:
    return [
        ("event_type", str(env.get("event_type") or "").encode()),
        ("tenant_id", str(env.get("tenant_id") or "").encode()),
        ("event_id", str(env.get("event_id") or "").encode()),
        ("content-type", b"application/json"),
    ]
