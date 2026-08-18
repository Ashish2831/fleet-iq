from __future__ import annotations

from datetime import datetime, timezone
from threading import Lock


class MemoryTelemetryStore:
    """Process-local stand-in so tests do not need mongod.

    Same document shape as Mongo: time-series-like raw list + dedupe set + 1min buckets.
    Shard key in production would be {tenant_id, vehicle_id}; here it is just a list.
    """

    def __init__(self):
        self.raw: list[dict] = []
        self.minute: list[dict] = []
        self.dedupe: set[str] = set()
        self.traces: list[dict] = []
        self._buf: list[dict] = []
        self._lock = Lock()

    def claim_event(self, event_id: str) -> bool:
        with self._lock:
            if event_id in self.dedupe:
                return False
            self.dedupe.add(str(event_id))
            return True

    def insert_raw(self, docs: list[dict]) -> int:
        with self._lock:
            self.raw.extend(docs)
            return len(docs)

    def insert_minute(self, docs: list[dict]) -> int:
        with self._lock:
            self.minute.extend(docs)
            return len(docs)

    def track(self, *, tenant_id: str, vehicle_id: str, start: datetime, end: datetime, source: str = "raw") -> list[dict]:
        coll = self.minute if source == "minute" else self.raw
        with self._lock:
            rows = [
                d
                for d in coll
                if str(d.get("meta", {}).get("tenant_id")) == str(tenant_id)
                and str(d.get("meta", {}).get("vehicle_id")) == str(vehicle_id)
                and start <= _ts(d.get("recorded_at")) <= end
            ]
        rows.sort(key=lambda d: _ts(d.get("recorded_at")))
        return [_point(d) for d in rows]

    def expire_raw(self, older_than: datetime) -> int:
        with self._lock:
            keep, drop = [], 0
            for d in self.raw:
                if _ts(d.get("recorded_at")) < older_than:
                    drop += 1
                else:
                    keep.append(d)
            self.raw = keep
            return drop

    def flush(self) -> None:
        with self._lock:
            if self._buf:
                self.raw.extend(self._buf)
                self._buf.clear()

    def buffer(self, doc: dict) -> None:
        with self._lock:
            self._buf.append(doc)

    def raw_count(self, *, tenant_id: str | None = None) -> int:
        with self._lock:
            if tenant_id is None:
                return len(self.raw) + len(self._buf)
            return sum(
                1
                for d in (*self.raw, *self._buf)
                if str(d.get("meta", {}).get("tenant_id")) == str(tenant_id)
            )


def _ts(value) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    return datetime.now(timezone.utc)


def _point(d: dict) -> dict:
    coords = (d.get("loc") or {}).get("coordinates") or [None, None]
    lng, lat = (coords + [None, None])[:2]
    return {
        "recorded_at": _ts(d.get("recorded_at")),
        "lat": lat,
        "lng": lng,
        "speed_kmh": float(d.get("speed_kmh") or 0),
        "heading": d.get("heading"),
    }
