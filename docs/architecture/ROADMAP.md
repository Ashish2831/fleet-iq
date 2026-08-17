# Roadmap — all technologies retained

Each phase adds a real FleetIQ capability. Nothing from the original stack is cancelled.

```
A  Domain + Postgres + Django ORM
B  REST, then GraphQL BFF on the same Django process
C  Redis + Django Channels + live fleet map
D  Transactional outbox + Kafka
E  MongoDB telemetry from Kafka
F  Elasticsearch (ops search + hybrid RAG)
G  Dispatch engine (solver) + LangGraph approval workflow
H  AI platform (Operations Agent, RAG, tools)
I  Service extraction + GraphQL federation + Next.js microfrontends
```

---

## North-star (target)

```
                    Next.js Shell
                    Microfrontends
                           │
                    GraphQL Gateway
                           │
     ┌─────────────┬───────┴────────┬──────────────┐
     ▼             ▼                ▼              ▼
 Identity      Order            Fleet         Dispatch
 Tenant        Shipment         Driver        Route
               Delivery         Vehicle       Tracking
     │             │                │              │
     └─────────────┴───────┬────────┴──────────────┘
                           │
                      PostgreSQL
                    (system of record)
                           │
                       Outbox
                           │
                         Kafka
                           │
          ┌────────────────┼────────────────┐
          ▼                ▼                ▼
      Tracking         Analytics       Notification
      MongoDB          Postgres        (email/push)
      Redis live       ClickHouse later
      WebSockets
                           │
                    Elasticsearch
                    (search + RAG)
                           │
                      AI Platform
                   LangGraph + LangChain
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
          RAG Engine   Route Agent  Operations Agent
```

That is the destination. Phases A–I are specified. After I the stack matches this diagram: same product, extra process boundaries. Extract Tracking, AI, and Analytics first; the other original service names stay modular monolith packages until they earn a process.

---

## Phase map

| Phase | You implement | Concepts you learn | Still in the plan, not built yet |
|---|---|---|---|
| **A** Foundation | Tenants, users, drivers, vehicles, warehouses, customers, orders, shipments, routes, deliveries | Django ORM, joins, indexes, transactions, constraints, multi-tenancy | Everything below |
| **B** API | REST, then one GraphQL schema (`dashboard`, fleet, orders) | GraphQL schema, resolvers, DataLoader / N+1 | Federation, MFEs |
| **C** Live map | GPS ingest API → Redis latest state → Channels | Redis hashes, pub/sub, WebSockets, rate limits | Kafka fan-out |
| **D** Events | `outbox_events` + worker → Kafka | Outbox, partitions (`vehicle_id`), consumers, idempotency, DLQ | Extra services |
| **E** Telemetry | Kafka → MongoDB `vehicle_location_events` | High-volume writes, TTL, aggregation, time-series | Sharding at 1M events/s (discussion + config, not a live cluster) |
| **F** Search | Index shipments/drivers + SOP docs | BM25, mappings, vector fields, hybrid search | Production cluster ops |
| **G** Dispatch | Scoring / OR-Tools + optional human approval | Constraint optimization, locks, Kafka `OrderCreated` | LLM does not compute VRP |
| **H** AI | LangGraph Operations Agent + RAG + tools | Tool calling, HITL, citations | Auto-execute mutations |
| **I** Distribution | Extract Tracking, AI, Analytics; federate GraphQL; Fleet/Dispatch/Orders/AI MFEs | Service boundaries, Module Federation, independent deploys | — |

---

## Interview line (use after Phase D+)

> Postgres is the system of record. Dispatch is a deterministic optimizer with a LangGraph human-approval loop around it. Kafka plus transactional outbox decouples writes from side effects. Redis holds latest vehicle state for the map. MongoDB stores high-volume GPS documents. Elasticsearch is operational search and hybrid RAG. GraphQL is the BFF; federation and microfrontends come after service extraction.

---

## Kafka events (introduced in D, consumed across later phases)

| Event | Producer | Early consumers |
|---|---|---|
| `OrderCreated` | Order | Dispatch, Analytics, Notification |
| `OrderAssigned` | Dispatch | Tracking, Notification |
| `DriverAssigned` | Dispatch | Fleet, Notification |
| `VehicleLocationUpdated` | Tracking ingest | MongoDB writer, Redis, ETA |
| `RouteCreated` / `RouteUpdated` | Route | Analytics, AI |
| `DeliveryStarted` / `Completed` / `Failed` | Delivery | Analytics, Notification, AI |
| `VehicleOffline` | Tracking | Ops, Notification |
| `VehicleMaintenanceDue` | Fleet | Notification, Maintenance Agent |
| `PaymentCompleted` | Payments | Analytics |

---

## Non-negotiable rules across all phases

1. **`tenant_id` on every tenant-owned row, Kafka event, Redis key, WebSocket room, ES document, Mongo document.**
2. **Dispatch assignment is deterministic.** LangGraph orchestrates tools and approval; it does not invent capacity math.
3. **Extract a service only when a module already exists and has a scale or runtime reason.** Phase I, not Phase A.
