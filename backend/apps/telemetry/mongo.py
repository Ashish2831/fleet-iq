from __future__ import annotations

from datetime import datetime, timezone

from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError

RAW = "vehicle_location_events"
DEDUPE = "vehicle_location_dedupe"
MINUTE = "vehicle_location_1min"


class MongoTelemetryStore:
    """Time-series GPS history. Unique event_id lives on the companion dedupe collection
    because Mongo time-series collections cannot take a unique index on event_id.

    Production shard key: hashed meta.vehicle_id (or {tenant_id, vehicle_id} compound).
    A single busy tenant must not be the only shard key.
    """

    def __init__(self, uri: str, db_name: str, *, raw_ttl: int = 604800, minute_ttl: int = 7776000):
        self._client = MongoClient(uri, serverSelectionTimeoutMS=2000)
        self._db = self._client[db_name]
        self.raw_ttl = raw_ttl
        self.minute_ttl = minute_ttl
        self._buf: list[dict] = []
        self._ensured = False

    def ensure(self) -> None:
        if self._ensured:
            return
        names = set(self._db.list_collection_names())
        if RAW not in names:
            self._db.create_collection(
                RAW,
                timeseries={"timeField": "recorded_at", "metaField": "meta", "granularity": "seconds"},
                expireAfterSeconds=self.raw_ttl,
            )
        if MINUTE not in names:
            self._db.create_collection(
                MINUTE,
                timeseries={"timeField": "recorded_at", "metaField": "meta", "granularity": "minutes"},
                expireAfterSeconds=self.minute_ttl,
            )
        if DEDUPE not in names:
            self._db.create_collection(DEDUPE)
        self._db[RAW].create_index([("meta.tenant_id", 1), ("meta.vehicle_id", 1), ("recorded_at", -1)])
        self._db[RAW].create_index([("meta.tenant_id", 1), ("recorded_at", -1)])
        self._db[MINUTE].create_index([("meta.tenant_id", 1), ("meta.vehicle_id", 1), ("recorded_at", -1)])
        self._db[DEDUPE].create_index("created_at", expireAfterSeconds=86400)
        self._ensured = True

    def claim_event(self, event_id: str) -> bool:
        self.ensure()
        try:
            self._db[DEDUPE].insert_one({"_id": str(event_id), "created_at": datetime.now(timezone.utc)})
            return True
        except DuplicateKeyError:
            return False

    def insert_raw(self, docs: list[dict]) -> int:
        self.ensure()
        if not docs:
            return 0
        self._db[RAW].insert_many(docs, ordered=False)
        return len(docs)

    def insert_minute(self, docs: list[dict]) -> int:
        self.ensure()
        if not docs:
            return 0
        self._db[MINUTE].insert_many(docs, ordered=False)
        return len(docs)

    def track(self, *, tenant_id: str, vehicle_id: str, start: datetime, end: datetime, source: str = "raw") -> list[dict]:
        self.ensure()
        coll = MINUTE if source == "minute" else RAW
        cursor = self._db[coll].find(
            {
                "meta.tenant_id": str(tenant_id),
                "meta.vehicle_id": str(vehicle_id),
                "recorded_at": {"$gte": start, "$lte": end},
            },
            sort=[("recorded_at", 1)],
        )
        out = []
        for d in cursor:
            coords = (d.get("loc") or {}).get("coordinates") or [None, None]
            lng, lat = (coords + [None, None])[:2]
            out.append(
                {
                    "recorded_at": d.get("recorded_at"),
                    "lat": lat,
                    "lng": lng,
                    "speed_kmh": float(d.get("speed_kmh") or 0),
                    "heading": d.get("heading"),
                }
            )
        return out

    def expire_raw(self, older_than: datetime) -> int:
        # Time-series TTL is cluster-side. This is a test/admin hook for the memory store.
        return 0

    def buffer(self, doc: dict) -> None:
        self._buf.append(doc)

    def flush(self) -> None:
        if not self._buf:
            return
        batch, self._buf = self._buf, []
        self.insert_raw(batch)

    def raw_count(self, *, tenant_id: str | None = None) -> int:
        self.ensure()
        q = {"meta.tenant_id": str(tenant_id)} if tenant_id else {}
        return self._db[RAW].count_documents(q) + len(self._buf)
