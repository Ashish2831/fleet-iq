# Phase C — Live fleet tracking

**Goal:** A driver (or simulator) publishes GPS. Django validates and rate-limits it. Redis holds **latest** vehicle state. Django Channels pushes throttled updates to the ops `/live-map`. Auth and `tenant_id` apply to sockets the same way they apply to REST.

**Depends on:** Phase A vehicles/drivers/routes, Phase B JWT + Next.js `(fleet)` group.

**Out of scope for C (still on the roadmap):** Kafka between ingest and Redis (Phase D), MongoDB history (Phase E), ES geo search (Phase F), dispatch solver (Phase G).

Phase C **uses Redis for all four jobs it will have in production**, even if two of them are small:

| Redis job | Phase C | Later |
|---|---|---|
| Live vehicle hash | yes — source of the map | still Redis; Kafka is the bus |
| Channels layer | yes — `channels_redis` | same |
| Rate limit GPS/API | yes — replace in-memory DRF throttle | same keys at scale |
| Distributed locks | yes — stub `lock:order:{id}` / `lock:dispatch:{tenant}` | Phase G dispatch |
| ETA cache | yes — simple haversine + remaining stops | traffic API in G/H |

---

## 1. Data path (now vs target)

**Phase C (learn Redis + Channels without Kafka):**

```
Driver app / simulator
        │  POST /api/v1/tracking/locations
        ▼
   Tracking ingest (Django)
        │  auth, validate, rate-limit
        ├── Redis HSET  vehicle:{tenant}:{id}
        ├── optional: vehicle.last_seen_* columns (not the history store)
        └── Channel group  tenant.{id}.fleet
                │
                ▼
         WebSocket  /ws/fleet
                │
                ▼
         Next.js /live-map
```

**From Phase D onward (nothing in C is thrown away):**

```
POST ingest
    → Redis latest (still; ops map cannot wait for a consumer lag)
    → Outbox or direct produce  VehicleLocationUpdated
    → Kafka (key = vehicle_id)
         ├── MongoDB history
         ├── ETA worker
         └── optional second consumer → Channels (if you want ingest workers off HTTP)
```

In C, ingest **writes Redis and broadcasts**. In D, ingest still writes Redis (low-latency map) **and** publishes Kafka for everyone else. Do not move the map onto Kafka-only in D — ops dashboards hate consumer lag.

---

## 2. Django app

```
apps/tracking/
  models.py          # DeviceHeartbeat optional; do not store GPS ticks in Postgres
  services.py        # ingest_location()
  consumers.py       # FleetConsumer
  routing.py         # websocket URL
  redis_state.py     # get/set vehicle hash, geo, locks
  throttles.py
  simulator.py       # management command
```

ASGI (required — WSGI cannot do WebSockets):

```python
# config/asgi.py
application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": JwtAuthMiddleware(URLRouter(tracking.routing.websocket_urlpatterns)),
})
```

Run Daphne or Uvicorn in C. Gunicorn+uvicorn workers later. Channel layer:

```python
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {"hosts": [REDIS_URL], "capacity": 1000, "expiry": 15},
    }
}
```

`capacity` / `expiry` are how you talk about **backpressure**: slow clients get dropped rather than unbounded queues.

---

## 3. GPS ingest API

```
POST /api/v1/tracking/locations
Authorization: Bearer <driver or device token>
```

```json
{
  "vehicle_id": "uuid",
  "recorded_at": "2026-08-17T11:30:01.120Z",
  "lat": 12.9698,
  "lng": 77.7500,
  "speed_kmh": 32.4,
  "heading": 85,
  "accuracy_m": 8,
  "battery": 0.72,
  "fuel_level": 0.41,
  "event_id": "uuid"
}
```

### Rules

| Rule | Why |
|---|---|
| `event_id` unique per tenant | Idempotent ingest (duplicates from retries) |
| `recorded_at` not > 30s in the future | Clock skew |
| Reject if `recorded_at` < last Redis `recorded_at` | Out-of-order GPS (store stale flag, do not move the pin backwards) |
| Vehicle must belong to JWT `tid` | Isolation |
| Driver token: vehicle must have a **current** `vehicle_assignment` for that driver | Prevent spoofing another truck |
| Device token (optional): `vehicles.metadata.device_id` | Telematics box path |
| Rate limit **per vehicle**: 1 accepted write / second | Phones should not send 5–10 Hz; batch on device |

HTTP **202** after Redis update. Do not wait on Channels `group_send` failure to fail the request — log and move on.

Idempotency: Redis `SET ingest:{tenant}:{event_id} 1 EX 3600 NX`. If NX fails, return 202 with `{ "duplicate": true }`.

---

## 4. Redis layout (the real schema)

All keys **include tenant**.

### Latest vehicle (hash)

```
vehicle:{tid}:{vehicle_id}
  lat, lng, speed, heading, status, recorded_at, driver_id, route_id, battery, fuel_level
TTL  120s     # missing TTL → vehicle goes Offline on the map
```

`status` is derived, not blindly trusted from the client:

| Input | Status |
|---|---|
| speed > 3 and on an in-progress route | `delivering` |
| speed ≤ 3 and on route | `stopped` / `idle_on_route` |
| no route, recent ping | `active` |
| TTL expired / no key | `offline` (computed at read time) |

### Tenant index (for dashboard + map snapshot)

```
tenant:{tid}:vehicles          SET of vehicle_ids that have been seen
tenant:{tid}:geo               GEOADD lng lat vehicle_id     # Redis GEO
```

`GEOADD` is how you later answer “vehicles near Whitefield” without Elasticsearch. Phase F can still add ES; GEO is the Redis lesson.

### Presence / counts (optional cache)

```
tenant:{tid}:counts            HASH  active, delivering, delayed, offline
TTL 5s                         # cheap dashboard; GraphQL can read this
```

Recompute from the SET + hashes every 5s in a loop, or on ingest (last is hotter, skip in C unless you want to).

### ETA cache

```
eta:shipment:{tid}:{shipment_id}    STRING  {"seconds": 840, "computed_at": ...}
TTL 30s
```

Phase C ETA: remaining stops on the route + haversine / average 25 km/h city speed. Good enough for the map. Replace with a traffic API behind the same key shape later.

### Rate limit

```
rl:gps:{tid}:{vehicle_id}      INCR + EXPIRE 1s     allow if value == 1
rl:login:{ip}                  sliding window
```

### Locks (API exists in C; dispatch uses it in G)

```
lock:order:{tid}:{order_id}           SET NX EX 15
lock:route:{tid}:{route_id}
```

Helper:

```python
def acquire(key: str, token: str, ttl: int = 15) -> bool:
    return redis.set(key, token, nx=True, ex=ttl)

def release(key: str, token: str) -> None:
    # Lua: delete only if value == token
```

Call `acquire` in C from a unit test and from `assign_route` (prevent double-assign). That is enough to **learn** locks before the solver exists.

---

## 5. WebSockets

```
GET /ws/fleet?bounds=south,west,north,east
Sec-WebSocket-Protocol: Bearer, <access_token>
```

Query-string tokens leak in logs; prefer the WS subprotocol or a first-message `{ "type": "auth", "token": "..." }`.

### Rooms

```
tenant.{tid}.fleet                 all vehicles (dev / small tenant)
tenant.{tid}.fleet.cell.{geohash}  viewport later
```

Phase C: one group per tenant is fine (your seed is ~10 vehicles). Design the cell key now; subscribe to geohash prefixes when the user pans the map. Do **not** broadcast every GPS tick to every connected tab in the written design — throttle.

### Server → client messages

```json
{ "type": "snapshot", "vehicles": [ { "id", "lat", "lng", "status", "speed" } ], "counts": { "active": 8, "delivering": 5, "delayed": 1, "offline": 2 } }

{ "type": "vehicle.updated", "vehicle": { "id", "lat", "lng", "status", "speed", "heading", "recorded_at" } }

{ "type": "counts", "counts": { "active": 8, "delivering": 5, "delayed": 1, "offline": 2 } }
```

On connect: `HGETALL` (or pipeline) all vehicles in the tenant SET → `snapshot`. Then stream diffs.

### Throttle (required)

Ingest may accept 1 Hz. The dashboard should get **~1–2s** or “moved > 15 m”. Implementation:

```
last_broadcast:{tid}:{vehicle_id}    recorded_at or epoch
```

Skip `group_send` if last broadcast < 1000 ms and distance < 15 m, unless `status` changed (offline ↔ delivering).

### Heartbeat / offline

Client ping every 20s. Server: scan is expensive — instead, map UI treats `recorded_at` older than 90s as offline. A periodic task (`vehicle_offline_watcher`) on a 30s beat: if hash TTL gone, `group_send` `{ type: vehicle.updated, status: offline }` once. That emits the **`VehicleOffline` domain event into outbox in Phase D**; in C you only push the socket.

### Auth on the socket

Same JWT. Bind the consumer to `tid`. A forged subscribe to another tenant’s group name must be ignored — **group name is derived from the token**, never from client payload.

```python
self.group = f"tenant.{user.tenant_id}.fleet"
```

---

## 6. Next.js `/live-map`

Route: `app/(fleet)/live-map/page.tsx`.

Libraries: MapLibre GL (no Google key) or Leaflet. Markers by `vehicle.id`. Status colour: delivering / delayed / offline.

UI matches the original mock:

```
┌─────────────────────────────────────────────┐
│              LIVE FLEET MAP                 │
│         markers from WebSocket              │
├─────────────────────────────────────────────┤
│ Active    Delivering    Delayed    Offline  │
│   8           5            1          2     │
└─────────────────────────────────────────────┘
```

- First paint: GraphQL `dashboard` + optional REST `GET /api/v1/tracking/vehicles` (snapshot if WS is slow).
- Live: WS diffs only.
- Click marker → drawer: plate, driver, current route, ETA (from `eta:` key via GraphQL `vehicle(id) { live { ... } }`).

Add to GraphQL in C (resolver reads Redis, **not** Postgres):

```graphql
extend type Vehicle {
  live: VehicleLive
}

type VehicleLive {
  lat: Float
  lng: Float
  speedKmh: Float
  heading: Float
  status: VehicleLiveStatus!
  recordedAt: DateTime
}

extend type Dashboard {
  liveCounts: LiveCounts!
}

type LiveCounts {
  active: Int!
  delivering: Int!
  delayed: Int!
  offline: Int!
}
```

Delayed count still comes from Postgres (`promised_at < now`). Mix of stores on one GraphQL type is the BFF lesson.

Simulator in the UI: a “simulate GPS” button for local demo is fine; the **real** simulator is a Django command so you can talk about load later.

---

## 7. Simulator (this is the demo)

```
python manage.py simulate_gps --tenant acme-logistics --interval 1
```

For each in-progress route:

- Walk from stop `n` to `n+1` along a polyline (encode a few Bangalore paths as fixtures, or call OSRM once and cache).
- POST ingest as the assigned driver/device.
- At dropoff, optionally `POST` delivery arrived (or leave that for later).

10 vehicles × 1 Hz is enough to see the map move. Document the 1M vehicles thought experiment in comments/tests:

- Partition / shard key = `vehicle_id`
- Redis Cluster hash tags `{tid}` vs `{vehicle_id}` (talk, do not deploy cluster)
- Sampling: keep latest in Redis, history sampled to 0.2 Hz in Mongo (Phase E)

---

## 8. Postgres: only pointers, not ticks

Optional columns (migration in C):

```sql
ALTER TABLE vehicles
    ADD COLUMN last_lat DOUBLE PRECISION,
    ADD COLUMN last_lng DOUBLE PRECISION,
    ADD COLUMN last_seen_at TIMESTAMPTZ;
```

Update these **at most every 15–30s** from ingest (or skip and keep Redis-only). They help GraphQL/REST when Redis is empty. They are **not** telemetry history.

Do **not** `INSERT` a `vehicle_locations` table in Postgres. That is how you accidentally kill OLTP. History = MongoDB in E.

`event_id` de-dupe for ingest can live in Redis only (TTL 1h). After Kafka, the consumer idempotency table can move to Postgres/Mongo.

---

## 9. Failure modes you should demo / test

| Case | Expected |
|---|---|
| Duplicate `event_id` | 202 duplicate, pin does not jump |
| Older `recorded_at` | ignored for Redis latest |
| Burst 20 Hz from one vehicle | 429 / drop extras via `rl:gps` |
| WS with tenant B token, subscribe payload tenant A | still room B |
| Redis down | ingest 503; map stale; Postgres still serves orders |
| Channel layer full | ingest still 202; log drop |
| Vehicle TTL expires | marker goes Offline within ~2 min |

---

## 10. What you should be able to explain after C

- Why latest state is Redis and history is not Postgres.
- Why WebSocket groups are keyed by tenant from JWT, not from the client.
- Why you throttle broadcast independently of ingest rate.
- Why GPS ingest is 202 and not a Postgres insert per tick.
- How `SET NX` locks prevent double assign.
- What changes in D: Kafka gets `VehicleLocationUpdated`; Redis stays the hot read.

---

## 11. Phase C done when

- [ ] `POST /api/v1/tracking/locations` authenticated, tenant-safe, rate-limited, idempotent
- [ ] Redis hash + GEO + TTL updated; missing TTL surfaces as Offline
- [ ] `/ws/fleet` snapshot + throttled diffs; second tenant cannot join
- [ ] Next.js `/live-map` with live markers and Active / Delivering / Delayed / Offline counts
- [ ] GraphQL `dashboard.liveCounts` and `vehicle.live` read Redis
- [ ] `simulate_gps` walks Bangalore seed routes
- [ ] `assign_route` uses a Redis lock
- [ ] DRF login + GPS throttles are Redis-backed

Next: **Phase D** — outbox worker publishes `OrderCreated` / `VehicleLocationUpdated` to Kafka; consumers are no-ops or log-only except you keep Redis ingest as-is. DLQ + idempotency keys on the consumer.
