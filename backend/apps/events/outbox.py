from __future__ import annotations

import logging

from django.db import transaction
from django.utils import timezone

from apps.common.models import OutboxEvent
from apps.common.patterns.observer import DomainEvent, domain_events
from apps.common.repositories import OutboxEventRepository
from apps.events.bus import EventBus, get_bus
from apps.events.envelopes import envelope, kafka_headers, topic_for

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 20


def enqueue(
    *,
    tenant,
    event_type: str,
    aggregate_type: str,
    aggregate_id,
    payload: dict,
    partition_key: str | None = None,
    correlation_id: str | None = None,
) -> OutboxEvent:
    env = envelope(
        event_type=event_type,
        tenant_id=tenant.id,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        payload=payload,
        correlation_id=correlation_id,
    )
    row = OutboxEventRepository(tenant).create(
        id=env["event_id"],
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        event_type=event_type,
        payload=env,
        topic=topic_for(event_type),
        partition_key=str(partition_key or aggregate_id),
    )
    tenant_id = str(tenant.id)
    agg_id = str(aggregate_id)
    snapshot = dict(payload)

    def _emit():
        domain_events.emit(
            DomainEvent(
                type=event_type,
                payload=snapshot,
                tenant_id=tenant_id,
                aggregate_id=agg_id,
            )
        )

    transaction.on_commit(_emit)
    return row


def publish_batch(*, limit: int = 100, bus: EventBus | None = None) -> dict:
    """Claim unpublished rows with SKIP LOCKED, produce, then mark published.

    Produce-then-crash-before-commit is at-least-once: the row stays unpublished
    and is produced again. Consumers must be idempotent on event_id.
    """
    bus = bus or get_bus()
    published = 0
    failed = 0
    with transaction.atomic():
        rows = OutboxEventRepository.claim_unpublished(limit=limit, max_attempts=MAX_ATTEMPTS)
        for row in rows:
            topic = row.topic or topic_for(row.event_type)
            key = row.partition_key or str(row.aggregate_id)
            value = row.payload if isinstance(row.payload, dict) and "event_id" in row.payload else envelope(
                event_type=row.event_type,
                tenant_id=row.tenant_id,
                aggregate_type=row.aggregate_type,
                aggregate_id=row.aggregate_id,
                payload=row.payload if isinstance(row.payload, dict) else {},
                event_id=row.id,
                occurred_at=row.created_at,
            )
            try:
                bus.produce(topic, key, value, headers=dict(kafka_headers(value)))
                row.published_at = timezone.now()
                row.last_error = ""
                row.save(update_fields=["published_at", "last_error"])
                published += 1
            except Exception as exc:
                logger.exception("outbox produce failed id=%s", row.id)
                row.attempts = (row.attempts or 0) + 1
                row.last_error = str(exc)[:2000]
                row.save(update_fields=["attempts", "last_error"])
                failed += 1
    return {"published": published, "failed": failed, "claimed": published + failed}
