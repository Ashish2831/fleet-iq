# Phase D — Kafka + transactional outbox

**Goal:** Domain writes in Postgres become Kafka events **without dual-write failure**. GPS ticks go to Kafka as a **high-volume path** (not through the outbox table). Consumers are idempotent modules in the same Django deployable. DLQ exists. Redis from Phase C stays the hot map read.

**Depends on:** Phase A `outbox_events`, Phase B order/assign services, Phase C ingest + Redis.

**Out of scope for D:** MongoDB collections (Phase E writes the first real location consumer), Elasticsearch, LangGraph, new microservices. Consumers are **apps inside Django** (or small worker processes sharing the repo). Extract Tracking in Phase I.

Local broker: **Redpanda** (Kafka API, one binary). Same client libraries as Kafka.

---

## 1. The problem this phase exists to teach

```
BEGIN write order
COMMIT
publish Kafka   ← process dies here
```

Order exists; Dispatch never runs. Or:

```
publish Kafka
BEGIN write order  ← fails
```

Dispatch saw an order that does not exist.

**Transactional outbox** makes “DB + event” one commit. That is the senior pattern. Use it for **low-volume domain events**. Do **not** insert 1 GPS event/sec/vehicle into `outbox_events` — that is how you DDoS Postgres.

### Two producer paths (both used in production)

| Path | When | How |
|---|---|---|
| **Outbox** | Order, shipment, route, delivery, assignment, payment, `VehicleOffline` | Same transaction as the row; worker publishes |
| **Direct produce** | `VehicleLocationUpdated` | After Redis HSET succeeds; at-least-once to Kafka; consumer de-dupes on `event_id` |

Map latency still comes from Redis (Phase C). Kafka is for everyone else (Mongo, ETA rebuild, analytics, replay).

```
                    Postgres write
                          │
              ┌───────────┴───────────┐
              ▼                       ▼
         domain row              outbox_events
              │                       │
              └───────────┬───────────┘
                          │ COMMIT
                          ▼
                    Outbox worker
                          ▼
                        Kafka

GPS ingest ──► Redis latest ──► (throttle) Channels
         └──► Kafka vehicle.location   (direct)
```

---

## 2. Envelope (every message, every topic)

```json
{
  "event_id": "9c0e…",
  "event_type": "OrderCreated",
  "event_version": 1,
  "occurred_at": "2026-08-17T11:30:01.120Z",
  "tenant_id": "…",
  "aggregate_type": "order",
  "aggregate_id": "…",
  "correlation_id": "http-request-id",
  "causation_id": null,
  "payload": { }
}
```

Rules:

- `event_id` is the idempotency key (same as outbox `id` or ingest `event_id`).
- `tenant_id` is always present.
- Payload holds **business fields**, not the whole ORM dump.
- `event_version` + optional JSON Schema: consumers tolerate added fields; breaking changes get `OrderCreated.v2` or a new versioned payload.

Headers (Kafka record headers, duplicate of envelope for filtering):

`event_type`, `tenant_id`, `event_id`, `content-type: application/json`

---

## 3. Topics and partition keys

Fewer topics, event type in the envelope. One extra topic only because of **volume**.

| Topic | Events | Partition key | Why that key |
|---|---|---|---|
| `fleetiq.orders` | `OrderCreated`, `OrderConfirmed`, `OrderAssigned`, `OrderCancelled` | `order_id` | Ordered transitions per order |
| `fleetiq.routing` | `RouteCreated`, `RouteUpdated`, `DriverAssigned` | `route_id` | Stops/assign in order |
| `fleetiq.deliveries` | `DeliveryStarted`, `DeliveryCompleted`, `DeliveryFailed` | `shipment_id` | Delivery timeline |
| `fleetiq.fleet` | `VehicleOffline`, `VehicleMaintenanceDue` | `vehicle_id` | |
| `fleetiq.payments` | `PaymentCompleted` | `invoice_id` | stub OK |
| `fleetiq.vehicle.location` | `VehicleLocationUpdated` | `vehicle_id` | **Per-vehicle ordering** at scale |
| `fleetiq.dlq` | failed handlers | original key | |

**Never partition only on `tenant_id`.** One busy tenant becomes a hot partition.

Start with **3–6 partitions** locally. Interview math for “1M vehicles × 1 Hz”:

- 1M events/s on `vehicle.location`
- key = `vehicle_id` → ~even spread, order preserved **per vehicle**
- Consumer group scaled to partition count, not to “number of Python workers at random”

GPS producer linger (~50–100 ms) + batching is how ingest does not make one `produce()` syscall per HTTP request at load. In D, enable linger on the location producer; keep domain outbox produces simple.

---

## 4. Outbox table (already in Phase A)

Add the columns the worker needs:

```sql
ALTER TABLE outbox_events
    ADD COLUMN IF NOT EXISTS topic         VARCHAR(128),
    ADD COLUMN IF NOT EXISTS partition_key VARCHAR(64),
    ADD COLUMN IF NOT EXISTS attempts      INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS last_error    TEXT;

CREATE INDEX idx_outbox_unpublished
    ON outbox_events (created_at)
    WHERE published_at IS NULL;
```

`payload` is the **full envelope** (or envelope minus ids stored as columns — pick one; full envelope in JSONB is simpler).

Writer (unchanged idea, now fills topic + key):

```python
with transaction.atomic():
    order = Order.objects.create(...)
    OutboxEvent.objects.create(
        tenant=order.tenant,
        aggregate_type="order",
        aggregate_id=order.id,
        event_type="OrderCreated",
        topic="fleetiq.orders",
        partition_key=str(order.id),
        payload=envelope(...),
    )
```

If `create()` rolls back, no event. If it commits, the worker **will** publish (at-least-once).

---

## 5. Outbox worker

Separate process: `python manage.py outbox_publish` (or a Celery beat loop). Not in the request thread.

```
LOOP
  BEGIN
    SELECT id FROM outbox_events
      WHERE published_at IS NULL AND attempts < 20
      ORDER BY created_at
      FOR UPDATE SKIP LOCKED
      LIMIT 100
    produce each to Kafka (acks=all)
    SET published_at = now()
  COMMIT
  if produce failed: attempts += 1, last_error = ..., COMMIT, backoff
```

`SKIP LOCKED` = multiple worker replicas without double-publish of the same row **in the same moment**. After a crash mid-produce, the row is still unpublished → publish again → **duplicate on the topic**. That is why consumers must be idempotent. Say this in interviews.

Payload retention: keep published rows 7 days for debug, then delete/archive. This is not Kafka’s source of truth for replay — **Kafka is**. Outbox is a relay.

---

## 6. GPS producer (direct)

After Redis update in ingest (Phase C):

```python
producer.produce(
    topic="fleetiq.vehicle.location",
    key=str(vehicle_id),
    value=envelope(
        event_type="VehicleLocationUpdated",
        aggregate_type="vehicle",
        aggregate_id=vehicle_id,
        payload={ "lat", "lng", "speed_kmh", "heading", "recorded_at", "battery", "fuel_level" },
    ),
)
# fire-and-forget with delivery callback; HTTP already 202
```

If Kafka is down: Redis/map still works; location history (Phase E) has a gap. Optional: overflow list in Redis `kafka:location:buffer` with a max length (backpressure), never unbounded.

Do **not** write a Postgres outbox row per tick.

`VehicleOffline` **does** go through outbox: it is low-volume and must match ops notifications.

---

## 7. Consumers (modules, not 14 services)

```
apps/events/
  envelopes.py
  publisher.py          # outbox worker
  producer_gps.py
  consumers/
    base.py             # deserialize, inbox, DLQ
    notify.py           # log / email stub
    analytics.py        # postgres counters
    location_log.py     # stdout now; Mongo writer in E
```

Run: `python manage.py consume --group fleetiq-notify --topics fleetiq.orders,fleetiq.deliveries,fleetiq.fleet`

| Consumer group | Topics | Handler in D | Becomes |
|---|---|---|---|
| `fleetiq-notify` | orders, deliveries, fleet | log + optional console | Notification service |
| `fleetiq-analytics` | all domain topics | increment `analytics_daily_counts` | warehouse later |
| `fleetiq-location` | `vehicle.location` | no-op or JSONL | MongoDB in E |
| `fleetiq-eta` | `vehicle.location` | refresh `eta:` Redis (optional) | ETA service |
| `fleetiq-dispatch` | `fleetiq.orders` (`OrderCreated`) | log “would dispatch” | Phase G solver |

Same event, **different groups** = each group gets a full copy. That is the Kafka fan-out in your original diagram.

Redis latest is **not** required to be a Kafka consumer in D. Ingest already wrote it. Optional: a rebuild consumer that can reconstruct Redis from the location topic after a Redis flush — worth a command `rebuild_live_state` for interviews.

---

## 8. Idempotency inbox

```sql
CREATE TABLE processed_events (
    consumer_name   VARCHAR(64) NOT NULL,
    event_id        UUID NOT NULL,
    processed_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_name, event_id)
);
```

Handler:

```
if exists (consumer, event_id): ACK and skip
else:
    handle (side effect)
    insert processed_events
    ACK
```

If you crash after side effect and before insert, you **re-handle**. Side effects must themselves be idempotent (upsert analytics row, Mongo `event_id` unique, email with `event_id` as dedupe key). Inbox is necessary, not sufficient.

For location at high QPS, inbox-in-Postgres will hurt. Phase E: Mongo unique index on `event_id`, or Redis `SET NX` with TTL. In D, JSONL/no-op is fine; still **write the inbox code path** on domain consumers.

---

## 9. DLQ, retries, replay

**Retry:** 3 in-process retries with backoff for `ConnectionError`. Do not retry `ValidationError` (poison message).

**DLQ:** after max retries, produce to `fleetiq.dlq` with headers `original_topic`, `original_partition`, `original_offset`, `error`, `consumer_group`. Then ACK the original so the partition does not stall.

**Replay:**

- From Kafka: reset consumer group offsets (domain topics, compact or 7-day retention).
- Poison GPS: skip via DLQ; do not block a vehicle’s partition forever — if one bad JSON blocks `vehicle_id`’s partition, **all later points for that vehicle stall**. Validation must be cheap and skip-to-DLQ.

Retention (local): 24h. Document production: 3–7 days domain, location 24h then Mongo is source of history.

---

## 10. Analytics table (proof a consumer did something)

```sql
CREATE TABLE analytics_daily_counts (
    tenant_id    UUID NOT NULL REFERENCES tenants(id),
    day          DATE NOT NULL,
    event_type   VARCHAR(128) NOT NULL,
    count        INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (tenant_id, day, event_type)
);
```

Handler: `INSERT ... ON CONFLICT DO UPDATE SET count = count + 1` inside the same lock as inbox insert, or keyed by `event_id` in a `analytics_event_ledger` if you need stronger exactly-once-ish semantics.

This is a **projection**. Postgres remains system of record for orders; this table is derived and rebuildable from Kafka.

---

## 11. Local docker

```yaml
# docker-compose: redpanda + console + redis + postgres
redpanda:
  # kafka advertised localhost:19092
console:
  # UI on :8080 — show topics, payloads, consumer lag
```

Seed path to demo:

1. POST create order → row in `outbox_events`
2. Worker marks `published_at`
3. Console shows `fleetiq.orders` / `OrderCreated`
4. `fleetiq-analytics` increments counts
5. `simulate_gps` → Redis map **and** `fleetiq.vehicle.location` stream
6. Kill worker, create order, restart — event still publishes
7. Duplicate consume — counts do not double (inbox)

---

## 12. What not to build in D

- Exactly-once Kafka transactions — explain **why at-least-once + idempotent consumers** is the default.
- Kafka Connect / Debezium CDC — mention as an alternative to handwritten outbox if you are asked; you implemented the textbook outbox so you can explain it line by line.
- One topic per event type × 14 services.
- Using Kafka as the driver of the live map (lag, ops hate it).

---

## 13. What you should be able to explain after D

- Dual-write problem and how outbox + `SKIP LOCKED` worker solves it.
- Why GPS is **not** in the outbox table.
- Why `vehicle_id` is the location partition key (ordering vs hot keys).
- At-least-once, inbox, why handlers must still be idempotent.
- Consumer groups as fan-out vs competing consumers on the same group.
- DLQ so a poison payload does not stall a vehicle’s partition.
- Redis = latest; Kafka = bus; Mongo (next) = history.

---

## 14. Phase D done when

- [x] Create order / assign route / complete delivery write outbox in the same transaction
- [x] `outbox_publish` worker uses `SKIP LOCKED`; crash mid-loop still delivers (duplicate-safe)
- [x] Topics exist; Redpanda console shows envelopes with `tenant_id` + `event_id`
- [x] GPS ingest produces `fleetiq.vehicle.location` keyed by `vehicle_id` without a Postgres outbox row per tick
- [x] `fleetiq-notify` and `fleetiq-analytics` run as separate groups
- [x] Re-consuming the same `event_id` does not double-count
- [x] Poison message lands on `fleetiq.dlq`; other messages continue
- [x] Live map still works if Kafka is stopped (Redis path intact)

Next: **Phase E** — `fleetiq-location` consumer writes MongoDB `vehicle_location_events` (TTL, indexes, `event_id` unique). Redis remains latest; Postgres remains OLTP.
