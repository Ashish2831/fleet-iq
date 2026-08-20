from __future__ import annotations

"""
Redis live-vehicle schema.

At 1M vehicles the shard key is vehicle_id. Cluster hash tags would be
`{tid}` vs `{vehicle_id}` — talk, do not deploy cluster in C.
Latest pin stays in Redis; history is sampled later (Mongo, Phase E).
"""

import json
import logging
from datetime import datetime, timezone

import redis
from django.conf import settings

logger = logging.getLogger(__name__)

_client = None
RELEASE_LUA = """
if redis.call("get", KEYS[1]) == ARGV[1] then
  return redis.call("del", KEYS[1])
else
  return 0
end
"""


def get_redis():
    global _client
    if _client is None:
        _client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
    return _client


def reset_client():
    global _client
    _client = None


def _tid(tenant) -> str:
    return str(getattr(tenant, "id", tenant))


def vehicle_key(tenant, vehicle_id) -> str:
    return f"vehicle:{_tid(tenant)}:{vehicle_id}"


def seen_key(tenant) -> str:
    return f"tenant:{_tid(tenant)}:vehicles"


def geo_key(tenant) -> str:
    return f"tenant:{_tid(tenant)}:geo"


def acquire(key: str, token: str, ttl: int = 15) -> bool | None:
    """True if this caller holds the lock, False if held, None if Redis is down (fail-open)."""
    try:
        got = get_redis().set(key, token, nx=True, ex=ttl)
        return bool(got)
    except redis.RedisError:
        logger.exception("redis lock acquire failed")
        return None


def release(key: str, token: str) -> None:
    r = get_redis()
    try:
        r.eval(RELEASE_LUA, 1, key, token)
    except redis.ResponseError:
        # fakeredis (and some Redis builds) may lack EVAL; still require token match.
        if r.get(key) == token:
            r.delete(key)
    except redis.RedisError:
        logger.exception("redis lock release failed")


def route_lock_key(tenant, route_id) -> str:
    return f"lock:route:{_tid(tenant)}:{route_id}"


def order_lock_key(tenant, order_id) -> str:
    return f"lock:order:{_tid(tenant)}:{order_id}"


def derive_status(*, speed_kmh: float, on_route: bool) -> str:
    if on_route and speed_kmh > 3:
        return "delivering"
    if on_route:
        return "stopped"
    return "active"


def ingest_key(tenant, event_id: str) -> str:
    return f"ingest:{_tid(tenant)}:{event_id}"


def event_seen(tenant, event_id: str) -> bool:
    return bool(get_redis().exists(ingest_key(tenant, event_id)))


def ingest_event_id(tenant, event_id: str) -> bool:
    """True if this event_id is new."""
    return bool(get_redis().set(ingest_key(tenant, event_id), "1", nx=True, ex=3600))


def rate_limit_gps(tenant, vehicle_id) -> bool:
    """True if this write is allowed (first in the 1s window). Uses RateLimitStore strategy."""
    from apps.common.patterns.rate_limit import RedisRateLimitStore, allow_request

    key = f"gps:{_tid(tenant)}:{vehicle_id}"
    return allow_request(RedisRateLimitStore(), key, limit=1, window_seconds=1)


def write_live(tenant, vehicle_id: str, payload: dict) -> dict:
    r = get_redis()
    key = vehicle_key(tenant, vehicle_id)
    mapping = {k: "" if v is None else str(v) for k, v in payload.items()}
    r.hset(key, mapping=mapping)
    r.expire(key, 120)
    r.sadd(seen_key(tenant), str(vehicle_id))
    lat, lng = float(payload["lat"]), float(payload["lng"])
    r.geoadd(geo_key(tenant), [lng, lat, str(vehicle_id)])
    return payload


def last_recorded_at(tenant, vehicle_id) -> datetime | None:
    raw = get_redis().hget(vehicle_key(tenant, vehicle_id), "recorded_at")
    if not raw:
        return None
    return datetime.fromisoformat(raw.replace("Z", "+00:00"))


def should_broadcast(tenant, vehicle_id, *, lat, lng, status: str) -> bool:
    r = get_redis()
    bkey = f"last_broadcast:{_tid(tenant)}:{vehicle_id}"
    prev = r.hgetall(bkey)
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    if not prev:
        r.hset(bkey, mapping={"ms": str(now_ms), "lat": str(lat), "lng": str(lng), "status": status})
        r.expire(bkey, 30)
        return True
    elapsed = now_ms - int(prev.get("ms") or 0)
    dist = 0.0
    if prev.get("lat") and prev.get("lng"):
        from apps.tracking.geo import haversine_m

        dist = haversine_m(float(prev["lat"]), float(prev["lng"]), lat, lng)
    status_changed = prev.get("status") != status
    if elapsed < 1000 and dist < 15 and not status_changed:
        return False
    r.hset(bkey, mapping={"ms": str(now_ms), "lat": str(lat), "lng": str(lng), "status": status})
    r.expire(bkey, 30)
    return True


def get_vehicle_hash(tenant, vehicle_id) -> dict | None:
    data = get_redis().hgetall(vehicle_key(tenant, vehicle_id))
    return data or None


def snapshot(tenant, delayed_ids: set[str] | None = None) -> tuple[list[dict], dict]:
    r = get_redis()
    ids = list(r.smembers(seen_key(tenant)))
    vehicles = []
    counts = {"active": 0, "delivering": 0, "delayed": 0, "offline": 0}
    delayed_ids = delayed_ids or set()
    pipe = r.pipeline()
    for vid in ids:
        pipe.hgetall(vehicle_key(tenant, vid))
    hashes = pipe.execute()
    for vid, data in zip(ids, hashes):
        if not data:
            counts["offline"] += 1
            vehicles.append({"id": vid, "status": "offline"})
            continue
        redis_status = data.get("status") or "active"
        display = "delayed" if vid in delayed_ids else redis_status
        row = {
            "id": vid,
            "lat": float(data["lat"]) if data.get("lat") else None,
            "lng": float(data["lng"]) if data.get("lng") else None,
            "speed": float(data["speed"]) if data.get("speed") else 0,
            "heading": float(data["heading"]) if data.get("heading") else None,
            "status": display,
            "recorded_at": data.get("recorded_at"),
            "driver_id": data.get("driver_id") or None,
            "route_id": data.get("route_id") or None,
            "plate": data.get("plate") or None,
        }
        vehicles.append(row)
        if redis_status == "delivering":
            counts["delivering"] += 1
        else:
            counts["active"] += 1
    return vehicles, counts


def cache_eta(tenant, shipment_id, seconds: int) -> None:
    get_redis().set(
        f"eta:shipment:{_tid(tenant)}:{shipment_id}",
        json.dumps({"seconds": seconds, "computed_at": datetime.now(timezone.utc).isoformat()}),
        ex=30,
    )


def get_eta(tenant, shipment_id) -> dict | None:
    raw = get_redis().get(f"eta:shipment:{_tid(tenant)}:{shipment_id}")
    return json.loads(raw) if raw else None
