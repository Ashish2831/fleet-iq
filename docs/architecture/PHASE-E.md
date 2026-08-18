# Phase E — MongoDB telemetry

**Goal:** The `fleetiq-location` consumer (Phase D stub) writes high-volume GPS documents to MongoDB. Redis remains **latest pin**. Postgres remains **orders/fleet OLTP**. Kafka remains the bus. You learn time-series write patterns, TTL, indexes, aggregation, and how sharding *would* work — without pretending you are ingesting 1M events/s locally.

**Depends on:** Phase C Redis + ingest, Phase D `fleetiq.vehicle.location` topic and consumer group.

**Out of scope for E:** Elasticsearch, OR-Tools, LangGraph, Mongo as a second source of truth for orders.

---

## 1. Why MongoDB is here (and why it is not everywhere)

Your original design is correct **for this collection**:

- High insert rate
- Flexible `metadata` (device firmware, extra sensors)
- Documents you rarely update
- Queries like “points for vehicle X between 10:00 and 11:00”
- TTL expiry so the cluster does not grow forever

It is the **wrong** store for tenants, orders, money, and assignments. Those stay in Postgres with constraints.

| Store | Data |
|---|---|
| PostgreSQL | Domain + outbox + analytics counts |
| Redis | Latest vehicle hash, GEO, locks, WS layer |
| Kafka | Event log / bus |
| MongoDB | GPS history (and later other telemetry blobs) |

Interview sentence: *Mongo is a specialized sink, not a second ORM.*

TimescaleDB could do the same history inside Postgres. You still implement Mongo because the curriculum (and many telematics stacks) use a document/time-series store off the OLTP node. If asked “why not Timescale?”: one less technology vs operational isolation of ingest. Both are legitimate; you chose isolation + flexible metadata.

---

## 2. Collection: `vehicle_location_events`

Use a **time series collection** (Mongo 5.0+) keyed on `recorded_at` with `meta` = identity fields that do not change per tick.

```javascript
db.createCollection("vehicle_location_events", {
  timeseries: {
    timeField: "recorded_at",
    metaField: "meta",
    granularity: "seconds"
  },
  expireAfterSeconds: 604800  // 7 days raw ticks
})
```

Document (close to your original schema):

```javascript
{
  event_id: UUID,              // Kafka event_id; unique in overflow/dedupe collection
  recorded_at: ISODate,        // timeField
  meta: {
    tenant_id: UUID,
    vehicle_id: UUID,
    driver_id: UUID | null,
    route_id: UUID | null
  },
  loc: { type: "Point", coordinates: [lng, lat] },  // GeoJSON: lng first
  speed_kmh: Number,
  heading: Number,
  accuracy_m: Number,
  battery: Number,
  fuel_level: Number,
  ingested_at: ISODate,
  metadata: { }                // extra sensors — this is the “flexible document” reason
}
```

**Time series collections cannot have a unique index on `event_id`.** Two options companies use:

1. **Accept duplicates** in TS and de-dupe in the aggregation (`$group` by `event_id`), plus Redis NX on consume for a short TTL.
2. **Companion collection** `vehicle_location_dedupe` `{ _id: event_id }` with TTL 24h — insert first; if duplicate key, skip TS insert.

Use **(2)** in FleetIQ. You can show unique-index idempotency without fighting TS limitations.

Raw ticks live 7 days. Downsample (below) lives longer.

---

## 3. Indexes

On the time series collection, compound indexes go on `meta` + time:

```javascript
db.vehicle_location_events.createIndex({ "meta.tenant_id": 1, "meta.vehicle_id": 1, recorded_at: -1 })
db.vehicle_location_events.createIndex({ "meta.tenant_id": 1, recorded_at: -1 })
db.vehicle_location_events.createIndex({ loc: "2dsphere" })  // geofence / “who was in Whitefield”
```

Every query **starts with `meta.tenant_id`**. Same rule as Postgres.

Dedupe:

```javascript
db.vehicle_location_dedupe.createIndex({ created_at: 1 }, { expireAfterSeconds: 86400 })
// _id = event_id is already unique
```

---

## 4. Kafka consumer (the Phase D stub becomes real)

Group: `fleetiq-location`  
Topic: `fleetiq.vehicle.location`  
Key: `vehicle_id` (ordering per vehicle → ordered inserts for that truck)

```
for each record:
  envelope = json
  reject if tenant_id missing → DLQ
  try insert dedupe { _id: event_id }
  except DuplicateKey: ack, skip
  append to batch[]
  if batch 500 docs or 200ms:
    insertMany(ordered=False) into vehicle_location_events
    ack offsets for that batch
```

**Bulk insert**, not one round-trip per GPS tick. `ordered=False` so one bad doc does not abort the batch; send poison to DLQ.

Python: Motor or PyMongo in the same `apps/events/consumers/location_mongo.py` worker. Django models are **not** required. Keep a thin `TelemetryStore` protocol so Phase I can extract Tracking without rewriting queries.

Consumer lag is a **first-class metric**. If lag grows, Mongo is slow or the batch size is 1 — not “Kafka is broken”.

---

## 5. Downsampling (so 10k vehicles do not ruin you)

Raw 1 Hz × 10k vehicles × 7 days is already tens of billions of points. Locally you will not hit that. **Write the job anyway** — it is the retention story from the original scale scenario.

```
vehicle_location_1min     meta + recorded_at (bucket start)
  lat, lng, speed_avg, speed_max, points
  expireAfterSeconds: 90 days
```

Scheduled job (or Mongo `$merge` from a windowed aggregation every minute):

- `$match` last 2 minutes
- `$group` by tenant, vehicle, `$dateTrunc: { unit: "minute" }`
- `$avg` / `$max` speed, `$last` loc

Phase H Operations Agent reads **1min** for “what happened this morning” and raw only for ±5 minutes around an incident.

---

## 6. Query patterns (API + GraphQL)

REST (driver history, ops drawer):

```
GET /api/v1/vehicles/{id}/track?from=&to=
```

- Auth + tenant
- Cap range (max 6h raw, else 1min collection)
- Return simplified polyline (optional Douglas–Peucker on the server)

GraphQL:

```graphql
extend type Vehicle {
  track(from: DateTime!, to: DateTime!, source: TrackSource = RAW): [TrackPoint!]!
}

enum TrackSource { RAW MINUTE }
type TrackPoint { recordedAt: DateTime! lat: Float! lng: Float! speedKmh: Float }
```

Resolver hits Mongo, **not** DataLoader-from-Postgres. This is the second store on the BFF (after Redis `vehicle.live`).

Breadcrumb on `/live-map` plus vehicle drawer: last 15 minutes of track.

---

## 7. Aggregations you should implement (interview ammo)

**Distance today (approx):**

```javascript
{ $match: { "meta.tenant_id": tid, "meta.vehicle_id": vid, recorded_at: { $gte: startOfDay } } },
{ $sort: { recorded_at: 1 } },
{ $group: { _id: null, points: { $push: "$loc.coordinates" } } }
// then geodesic length in app code — or $reduce with $radians
```

**Stop detection (speed < 3 for ≥ 2 min)** — pipeline or app. Feeds “8 vehicles exceeded expected stop duration” for the Operations Agent later.

**Geofence:** `$geoWithin` polygon for Whitefield. Count distinct `meta.vehicle_id` in a time window. Same question ES will answer in F with different tradeoffs (search vs telemetry).

**Fuel / battery trend:** `$group` by hour on `fuel_level`. Flexible `metadata` fields used in a pipeline only when present (`$ifNull`).

---

## 8. Scaling story (talk, do not deploy a 100-shard cluster)

Original thought experiment: 1M vehicles × 1 Hz = 1M inserts/s.

| Lever | What you say |
|---|---|
| **Do not ingest 10 Hz** | Device samples on movement / 1s max (already Phase C) |
| **Partition Kafka by `vehicle_id`** | Ordered writes per truck; many consumers |
| **Shard Mongo on `meta.tenant_id` + `meta.vehicle_id`** | Avoid one hot shard; hashed `vehicle_id` if one tenant owns almost all vehicles |
| **Batch inserts** | 200–500 docs |
| **TTL + downsample** | Raw 7d, 1min 90d, 1h 1y |
| **Hot vehicle** | One bus on a demo loop is fine; a stuck partition is a **hot key** — split by `vehicle_id` granularity already |
| **Read path** | Live map never queries Mongo; only Redis |

Local: **unsharded replica set** (even a single node). Put shard-key choice in a comment and in this doc. That is honest; claiming a sharded 1M/s lab is not.

---

## 9. What else may live in Mongo later (not Phase E)

Flexible event documents, same cluster, different collections — still telemetry/ops, not money:

| Collection | When |
|---|---|
| `device_heartbeats` | firmware, IMEI, signal |
| `incidents` | unstructured exception payloads before Postgres incident table |
| `agent_traces` | LangGraph run logs (Phase H) |

Do not move `orders` here.

---

## 10. Failure modes

| Case | Expected |
|---|---|
| Duplicate Kafka delivery | Dedupe `_id = event_id`; one TS point |
| Mongo down | Kafka lag grows; Redis map still live; DLQ only for poison, not for downtime (retry) |
| Clock skew `recorded_at` | Same reject rules as ingest |
| Query 30 days raw | API 400 — force `source=MINUTE` |
| Missing `tenant_id` | DLQ, never insert |

---

## 11. What you should be able to explain after E

- Why GPS history is Mongo and latest is Redis.
- Why time series + a dedupe collection instead of one unique index on the TS collection.
- Why every query includes `tenant_id`.
- Bulk consume + `$dateTrunc` downsample as the real cost control.
- Shard key thought process vs hot partitions.
- How the Operations Agent will pull a window of points without touching Postgres.

---

## 12. Phase E done when

- [x] Time series collection + dedupe collection exist in docker-compose Mongo
- [x] `fleetiq-location` bulk-inserts from Kafka; unique `event_id` skips duplicates
- [x] TTL expires raw points (set a 10-minute TTL in a test collection to prove it)
- [x] `GET /api/v1/vehicles/{id}/track` and GraphQL `vehicle.track` return breadcrumbs
- [x] Map drawer shows last 15 minutes from Mongo; live pin still Redis
- [x] 1-minute downsample job runs
- [x] Tenant B cannot read tenant A’s track by vehicle UUID
- [x] Stopping Mongo does not freeze `/live-map`

Next: **Phase F** — Elasticsearch for shipment/driver ops search plus the start of SOP hybrid search (BM25 + vectors). Postgres remains truth; ES is a projection + RAG index.
