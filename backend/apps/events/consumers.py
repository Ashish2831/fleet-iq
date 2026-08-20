from __future__ import annotations

import logging
from datetime import datetime, timezone

from django.db import IntegrityError, transaction

from apps.common.repositories import DailyEventCountRepository, ProcessedEventRepository, TenantRepository
from apps.events.bus import BusRecord, EventBus, get_bus
from apps.events.topics import DLQ, DELIVERIES, FLEET, LOCATION, ORDERS, ROUTING

logger = logging.getLogger(__name__)

INBOX_CONSUMERS = ("fleetiq-notify", "fleetiq-analytics", "fleetiq-dispatch")


class PoisonMessage(ValueError):
    """Unretryable payload — goes to DLQ immediately."""


def _parse(record: BusRecord) -> dict:
    value = record.value
    if not isinstance(value, dict):
        raise PoisonMessage("payload is not a JSON object")
    if not value.get("event_id") or not value.get("event_type") or not value.get("tenant_id"):
        raise PoisonMessage("missing event_id, event_type, or tenant_id")
    return value


def already_processed(consumer_name: str, event_id: str) -> bool:
    return ProcessedEventRepository().already_processed(consumer_name, event_id)


def mark_processed(consumer_name: str, event_id: str) -> bool:
    try:
        ProcessedEventRepository().create(consumer_name=consumer_name, event_id=str(event_id))
        return True
    except IntegrityError:
        return False


def send_dlq(bus: EventBus, record: BusRecord, error: str, group: str) -> None:
    original = record.value if isinstance(record.value, dict) else {"raw": record.value}
    bus.produce(
        DLQ,
        record.key,
        {
            "original_topic": record.topic,
            "original_offset": record.offset,
            "error": error[:2000],
            "consumer_group": group,
            "payload": original,
        },
        headers={
            "original_topic": record.topic,
            "error": error[:200],
            "consumer_group": group,
        },
    )


def handle_notify(env: dict) -> None:
    logger.info("notify %s tenant=%s aggregate=%s", env.get("event_type"), env.get("tenant_id"), env.get("aggregate_id"))


def handle_analytics(env: dict) -> None:
    tenant = TenantRepository().by_id(env["tenant_id"])
    if tenant is None:
        raise PoisonMessage("unknown tenant_id")
    occurred = env.get("occurred_at") or ""
    try:
        day = datetime.fromisoformat(occurred.replace("Z", "+00:00")).date()
    except (TypeError, ValueError):
        day = datetime.now(timezone.utc).date()
    counts = DailyEventCountRepository(tenant)
    with transaction.atomic():
        row, created = counts.get_or_create_locked(
            day=day,
            event_type=env["event_type"],
            defaults={"count": 1},
        )
        if not created:
            counts.increment(row.pk)


def handle_dispatch(env: dict) -> None:
    if env.get("event_type") != "OrderConfirmed":
        return
    from apps.dispatch.graph import run_dispatch

    tenant = TenantRepository().by_id(env.get("tenant_id"))
    payload = env.get("payload") or {}
    order_id = payload.get("order_id") or env.get("aggregate_id")
    if tenant and order_id:
        run_dispatch(tenant, order_id, auto=True)


def handle_search(env: dict) -> None:
    from apps.search.indexer import apply_search_event

    apply_search_event(env)


def handle_location(env: dict) -> None:
    from apps.telemetry.ingest import TelemetryPoison, ingest_location_event

    try:
        ingest_location_event(env)
    except TelemetryPoison as exc:
        raise PoisonMessage(str(exc)) from exc


HANDLERS = {
    "fleetiq-notify": handle_notify,
    "fleetiq-analytics": handle_analytics,
    "fleetiq-dispatch": handle_dispatch,
    "fleetiq-location": handle_location,
    "fleetiq-search": handle_search,
}

GROUP_TOPICS = {
    "fleetiq-notify": [ORDERS, DELIVERIES, FLEET],
    "fleetiq-analytics": [ORDERS, ROUTING, DELIVERIES, FLEET],
    "fleetiq-dispatch": [ORDERS],
    "fleetiq-location": [LOCATION],
    "fleetiq-search": [ORDERS, ROUTING, DELIVERIES, FLEET],
}


def consume_once(group: str, *, bus: EventBus | None = None, max_records: int = 50) -> dict:
    bus = bus or get_bus()
    topics = GROUP_TOPICS[group]
    handler = HANDLERS[group]
    use_inbox = group in INBOX_CONSUMERS
    records = bus.poll(group, topics, max_records=max_records)
    ok = skipped = dlq = 0
    try:
        for record in records:
            try:
                env = _parse(record)
            except PoisonMessage as exc:
                send_dlq(bus, record, str(exc), group)
                dlq += 1
                continue
            event_id = str(env["event_id"])
            if use_inbox and already_processed(group, event_id):
                skipped += 1
                continue
            retries = 0
            while True:
                try:
                    handler(env)
                    if use_inbox:
                        mark_processed(group, event_id)
                    ok += 1
                    break
                except PoisonMessage as exc:
                    send_dlq(bus, record, str(exc), group)
                    dlq += 1
                    break
                except Exception as exc:
                    retries += 1
                    logger.exception("handler %s failed event=%s try=%s", group, event_id, retries)
                    if retries >= 3:
                        send_dlq(bus, record, str(exc), group)
                        dlq += 1
                        break
    finally:
        if group == "fleetiq-location":
            from apps.telemetry.store import get_store

            get_store().flush()
    return {"ok": ok, "skipped": skipped, "dlq": dlq, "polled": len(records)}
