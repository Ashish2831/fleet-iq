from __future__ import annotations

import json
import logging

from apps.events.bus import EventBus, get_bus
from apps.events.envelopes import envelope, kafka_headers
from apps.events.topics import LOCATION

logger = logging.getLogger(__name__)

LOCATION_BUFFER = "kafka:location:buffer"
BUFFER_MAX = 10_000


def produce_location(
    *,
    tenant,
    vehicle_id,
    event_id: str,
    lat: float,
    lng: float,
    speed_kmh: float,
    heading,
    recorded_at,
    battery=None,
    fuel_level=None,
    bus: EventBus | None = None,
) -> bool:
    """Direct produce after Redis HSET. Never writes Postgres outbox.

    HTTP already returned 202 semantics at the view; Kafka failure must not
    fail ingest. A bounded Redis list is the overflow, not an unbounded queue.
    """
    env = envelope(
        event_type="VehicleLocationUpdated",
        tenant_id=tenant.id,
        aggregate_type="vehicle",
        aggregate_id=vehicle_id,
        payload={
            "lat": lat,
            "lng": lng,
            "speed_kmh": speed_kmh,
            "heading": heading,
            "recorded_at": recorded_at.isoformat() if hasattr(recorded_at, "isoformat") else str(recorded_at),
            "battery": battery,
            "fuel_level": fuel_level,
        },
        event_id=event_id,
        occurred_at=recorded_at if hasattr(recorded_at, "isoformat") else None,
    )
    try:
        (bus or get_bus()).produce(
            LOCATION,
            str(vehicle_id),
            env,
            headers=dict(kafka_headers(env)),
        )
        return True
    except Exception:
        logger.exception("gps kafka produce dropped vehicle=%s", vehicle_id)
        _buffer(env)
        return False


def _buffer(env: dict) -> None:
    try:
        from apps.tracking.redis_state import get_redis

        r = get_redis()
        r.lpush(LOCATION_BUFFER, json.dumps(env))
        r.ltrim(LOCATION_BUFFER, 0, BUFFER_MAX - 1)
    except Exception:
        logger.exception("gps kafka buffer failed")
