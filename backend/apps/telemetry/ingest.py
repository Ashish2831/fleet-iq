from __future__ import annotations

from datetime import datetime, timezone

from django.conf import settings

from apps.telemetry.store import get_store


class TelemetryPoison(ValueError):
    """Unretryable GPS payload — consumer sends it to the DLQ."""


def ingest_location_event(env: dict) -> str:
    """Claim event_id, buffer a time-series document. Returns 'written' | 'duplicate'.

    Missing tenant_id / lat / lng is poison. Mongo/network errors propagate so the
    consumer retries instead of DLQ (lag, not poison).
    """
    tenant_id = env.get("tenant_id")
    payload = env.get("payload") if isinstance(env.get("payload"), dict) else {}
    vehicle_id = env.get("aggregate_id") or payload.get("vehicle_id")
    event_id = env.get("event_id")
    try:
        lat = float(payload["lat"])
        lng = float(payload["lng"])
    except (KeyError, TypeError, ValueError) as exc:
        raise TelemetryPoison("lat and lng are required") from exc
    if not tenant_id:
        raise TelemetryPoison("tenant_id is required")
    if not vehicle_id:
        raise TelemetryPoison("vehicle_id is required")
    if not event_id:
        raise TelemetryPoison("event_id is required")

    store = get_store()
    if not store.claim_event(str(event_id)):
        return "duplicate"

    recorded = _ts(payload.get("recorded_at") or env.get("occurred_at"))
    doc = {
        "event_id": str(event_id),
        "recorded_at": recorded,
        "meta": {
            "tenant_id": str(tenant_id),
            "vehicle_id": str(vehicle_id),
            "driver_id": _opt(payload.get("driver_id")),
            "route_id": _opt(payload.get("route_id")),
        },
        "loc": {"type": "Point", "coordinates": [lng, lat]},
        "speed_kmh": float(payload.get("speed_kmh") or 0),
        "heading": payload.get("heading"),
        "accuracy_m": payload.get("accuracy_m"),
        "battery": payload.get("battery"),
        "fuel_level": payload.get("fuel_level"),
        "ingested_at": datetime.now(timezone.utc),
        "metadata": payload.get("metadata") or {},
    }
    buf = getattr(store, "buffer", None)
    if callable(buf):
        buf(doc)
        batch = int(getattr(settings, "TELEMETRY_BATCH_SIZE", 500))
        pending = getattr(store, "_buf", [])
        if len(pending) >= batch:
            store.flush()
    else:
        store.insert_raw([doc])
    return "written"


def _opt(value):
    if value in (None, "", "null"):
        return None
    return str(value)


def _ts(value) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str) and value:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    return datetime.now(timezone.utc)
