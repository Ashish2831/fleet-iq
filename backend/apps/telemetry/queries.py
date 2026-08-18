from __future__ import annotations

from datetime import datetime, timedelta, timezone

from apps.common.errors import BadRequest
from apps.telemetry.geo import simplify
from apps.telemetry.store import get_store

RAW_MAX_HOURS = 6


def vehicle_track(
    *,
    tenant_id,
    vehicle_id,
    start: datetime,
    end: datetime,
    source: str = "raw",
    simplify_m: float | None = 25.0,
) -> list[dict]:
    if end < start:
        raise BadRequest("to must be after from")
    src = (source or "raw").lower()
    if src not in ("raw", "minute"):
        raise BadRequest("source must be raw or minute")
    if src == "raw" and (end - start) > timedelta(hours=RAW_MAX_HOURS):
        raise BadRequest("raw track is capped at 6 hours; use source=minute")
    points = get_store().track(
        tenant_id=str(tenant_id),
        vehicle_id=str(vehicle_id),
        start=start,
        end=end,
        source=src,
    )
    if simplify_m and src == "raw" and len(points) > 400:
        return simplify(points, simplify_m)
    return points


def downsample_window(start: datetime, end: datetime) -> int:
    """Build 1-minute buckets from raw ticks in [start, end)."""
    store = get_store()
    store.flush()
    # Memory store exposes raw list; Mongo store re-queries.
    buckets: dict[tuple, dict] = {}
    if hasattr(store, "raw"):
        rows = [
            d
            for d in store.raw
            if start <= _ts(d.get("recorded_at")) < end
        ]
    else:
        rows = []
        if hasattr(store, "_db"):
            rows = list(
                store._db["vehicle_location_events"].find(
                    {"recorded_at": {"$gte": start, "$lt": end}}
                )
            )
    for d in rows:
        meta = d.get("meta") or {}
        ts = _ts(d.get("recorded_at"))
        minute = ts.replace(second=0, microsecond=0)
        key = (str(meta.get("tenant_id")), str(meta.get("vehicle_id")), minute)
        coords = (d.get("loc") or {}).get("coordinates") or [None, None]
        speed = float(d.get("speed_kmh") or 0)
        acc = buckets.get(key)
        if acc is None:
            buckets[key] = {
                "recorded_at": minute,
                "meta": {"tenant_id": key[0], "vehicle_id": key[1]},
                "loc": d.get("loc"),
                "speed_kmh": speed,
                "speed_max": speed,
                "points": 1,
                "heading": d.get("heading"),
            }
        else:
            n = acc["points"]
            acc["speed_kmh"] = (acc["speed_kmh"] * n + speed) / (n + 1)
            acc["speed_max"] = max(acc["speed_max"], speed)
            acc["points"] = n + 1
            acc["loc"] = d.get("loc")
            acc["heading"] = d.get("heading")
    docs = list(buckets.values())
    if docs:
        store.insert_minute(docs)
    return len(docs)


def _ts(value) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    return datetime.now(timezone.utc)
