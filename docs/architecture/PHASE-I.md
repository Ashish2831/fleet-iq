# Phase I — Distribution (services, federation, microfrontends)

**Goal:** The **same product** (dashboard, live map, dispatch HITL, ops agent) now runs with the process boundaries from the original diagram. You extract services that already have a scale or runtime reason. GraphQL **federation** replaces the single Strawberry schema. Next.js **route groups become remotes**. You are not starting 14 empty Django repos.

**Depends on:** A–H running as a modular monolith. If the vertical slice is not demoable, do not start I.

**This phase completes the north-star diagram.** After I, implementation work is operating, hardening, and filling remaining original services when they earn a process.

---

## 1. Extract because of a reason, not because of a slide

| Extract now | Reason | What leaves the monolith |
|---|---|---|
| **Tracking** | GPS ingest + WS fan-out + Redis/Mongo writers saturate Django request workers | `apps/tracking`, location consumer, Channels, `simulate_gps` |
| **AI** | LLM latency, API keys, long graphs, GPU/thread pool must not share Gunicorn workers with `POST /orders` | `apps/ai`, LangGraph workers, RAG generate |
| **Analytics** | Heavy aggregates / future ClickHouse must not lock OLTP | `analytics_daily_counts` consumer + read API; optional warehouse |

| Extract when load/team exists | Reason | Until then |
|---|---|---|
| **Notification** | Email/SMS provider, retries, templates | Keep `fleetiq-notify` consumer in repo, own process first |
| **Search / RAG index** | ES cluster + embed jobs | Stay in monolith `fleetiq-search` + F indexers |
| **Dispatch solver** | 30s OR-Tools waves | Own worker process **before** own service |
| **Document service** | Large PDF pipeline | Fold into AI or stay indexer job |

| Stay modular monolith | Why not a service in I |
|---|---|
| Identity + tenants | Auth is the shared kernel; JWT issuer stays one place |
| Order, shipment, delivery | Same transactions, same outbox |
| Fleet, driver, vehicle | Same Postgres; Driver vs Fleet split is org-chart, not scale |
| Routing + dispatch **apply** | `assign_route` is the single writer; G already isolated the solver |
| Pricing / billing stubs | No volume |

That maps to the original **14 names**: they remain **bounded contexts**. I promotes three (plus Notification as a worker) to **network services**. The rest stay packages until a real split criterion appears. Interviewers prefer this over “I copied 14 boilerplates.”

---

## 2. Runtime after I

```
                    Next.js Shell  :3000
                    ├── Fleet MFE
                    ├── Dispatch MFE
                    ├── Orders MFE
                    ├── Analytics MFE
                    └── AI MFE
                           │
                    GraphQL Gateway  :4000
                    (Apollo Router / Hive Gateway)
                           │
         ┌─────────┬───────┼────────┬─────────┬──────────┐
         ▼         ▼       ▼        ▼         ▼          ▼
     Core API   Tracking  AI    Analytics  Search*   Notify*
     Django     Django    Fast   Django    (job)     worker
     :8000      :8001     :8002  :8003
     Postgres   Redis     tools    counts
     orders     Mongo     ES RAG   Kafka
     fleet      WS        LangGraph
     dispatch
                           │
                         Kafka
```

`*` Search can stay a consumer next to Core until ES ops hurt. Notify is a consumer with an HTTP interface only if the shell must “send test email”.

**Core API** is the remaining monolith: identity, catalog, orders, shipments, routing, dispatch apply, proposal approve.

Contracts **do not change**: `POST /api/v1/tracking/locations` still exists; it is now served by Tracking. GraphQL `vehicle.live` and `vehicle.track` resolve in the Tracking subgraph. `dashboard` is composed at the gateway.

---

## 3. How to extract (one service at a time)

Do not extract three on the same weekend.

For Tracking (template for the others):

1. **API freeze** — OpenAPI + GraphQL types for live/track/WS already in C/E.
2. **Move code** — `apps/tracking` + location consumer + Channels to `services/tracking`.
3. **Data** — Redis and Mongo already isolated; Tracking **owns** those. Postgres `vehicles.last_seen_*` either stays Core (Core writes via events) or Tracking calls Core REST (avoid). Prefer: **Kafka `VehicleLocationUpdated` is enough**; drop Core colocate updates.
4. **Auth** — validate the **same JWT** (issuer Core Identity). Tracking trusts `tid` / `sub` / `perms`. No Tracking user table.
5. **Call Core** when ingest must check `vehicle_assignment`: REST `GET /internal/vehicles/{id}/assignment` with mTLS or signed internal token — **or** cache assignment snapshots from `DriverAssigned` Kafka. Prefer Kafka snapshot so Tracking does not depend on Core availability for every ping.
6. **Cut WS** — browsers hit Tracking `:8001/ws/fleet` (or gateway upgrades). Shell config `NEXT_PUBLIC_TRACKING_WS`.
7. **Delete** the old module from Core only after traffic is gone.

AI extraction: gateway + graphs + workers. Tools become **HTTP/GraphQL clients** to Core, Tracking, Search. Tenant still from JWT. `ai_runs` table can move with AI (its own Postgres) or stay Core; **prefer AI’s Postgres** so LLM dumps do not sit on OLTP.

Analytics extraction: consume Kafka, write projections, expose `dashboard` fields (`delayedDeliveries` can remain Core SQL **or** move — pick one owner to avoid two counts). Gateway `dashboard` is a **Core resolver that fans out** or a dedicated Dashboard subgraph. Simplest: Core still owns `dashboard { activeVehicles delayedDeliveries }` but `activeVehicles` delegates via federation `@requires` / another subgraph.

---

## 4. GraphQL federation

Phase B already split types **per app**. I turns those into subgraphs.

| Subgraph | Types it owns |
|---|---|
| `core` | `Order`, `Shipment`, `Route`, `Driver` (master data), `Customer`, `Mutation.assignRoute`, `DispatchProposal` |
| `tracking` | `VehicleLive`, `TrackPoint`, `extend type Vehicle { live, track }`, `LiveCounts` |
| `analytics` | `extend type Dashboard { costKpis, slaYesterday }` |
| `ai` | `AiRun`, `Mutation.startAiRun` |
| `search` | `searchShipments`, `searchKnowledge` (or keep on Core until extracted) |

Gateway composes. `dashboard` in the original query:

```graphql
query {
  dashboard {
    activeVehicles      # tracking liveCounts or Core+Redis
    delayedDeliveries   # core SQL or analytics
    activeDrivers
    routes { id status eta }
  }
}
```

`Vehicle` is defined in Core; Tracking `extend type Vehicle @key(fields: "id") { live: VehicleLive }`. That is the federation lesson Phase B prepared.

**Entities must key on `id` + gateway must pass tenant through context** (header `Authorization` forwarded to every subgraph). Subgraphs still `for_tenant(tid)` — federation does not replace tenancy.

Internal traffic: Gateway → subgraphs. Next.js should **not** call five subgraph URLs; only the gateway (plus WS to Tracking, plus REST commands to Core if you keep REST writes).

Apollo Router / GraphQL Hive / Cosmo all fine. Strawberry supports federation directives. Document **one** choice and stick to it.

---

## 5. Next.js microfrontends

Phase B route groups **are** the remotes:

| Remote | Routes | Owns UI for |
|---|---|---|
| `shell` | login, chrome, nav | auth cookie, layout, JWT refresh |
| `fleet` | `/live-map`, `/vehicles`, `/drivers` | map, WS to Tracking |
| `dispatch` | `/dispatch`, `/routes` | proposals, HITL |
| `orders` | `/orders`, `/shipments`, `/deliveries` | GraphQL Core |
| `analytics` | `/analytics`, `/performance`, `/costs` | Analytics subgraph |
| `ai` | `/ai-assistant`, `/agents`, `/knowledge` | AI subgraph |

**Module Federation** (or `module-federation/nextjs` / native Federation plugin) loads remotes at runtime. Shared: `react`, auth client, GraphQL client (gateway URL), design tokens.

Rules:

- Remotes **do not** import each other’s pages. They go through the gateway or the shell event bus (`CustomEvent` / tiny Zustand in shell).
- Auth: shell owns cookies; remotes call `getToken()` from a shared package `@fleetiq/auth`.
- Independent deploy: Fleet MFE can ship a map fix without rebuilding Orders.
- Locally: shell + two remotes is enough to prove federation; stubs for the rest. You still **have** five remotes in the repo (`apps/web-fleet`, …) even if some are thin.

This is org architecture: one person does not need MFEs to ship. You implement them because they were in the curriculum and the folder structure was designed for it in B.

---

## 6. Identity in a distributed system

- Core issues JWT (access + refresh).
- Audience `fleetiq`; each service validates signature (JWKS from Core).
- Internal service-to-service: `Authorization: Bearer` user token **propagated**, plus `X-Request-ID` / `X-Correlation-ID`.
- Optional: service tokens for Kafka consumers (no user). Consumers already used inbox + `tenant_id` on the event.

RBAC: `perms` in JWT as in B. Services enforce locally. Do not invent a second permission DB in Tracking.

---

## 7. Observability (without I, distributed debugging is fiction)

- OpenTelemetry traces: Gateway → Core → Kafka produce → Tracking consumer (context in payload `correlation_id`).
- Structured logs with `tenant_id`, `request_id`, `vehicle_id`.
- Consumer lag metrics (D), AI run duration (H), WS connections (C).
- Health: `/health` liveness, `/ready` dependencies (Postgres / Redis / Kafka).

You do not need Datadog. You need enough to say “the map is fine, the agent is slow, Core is fine.”

---

## 8. Original 14-service checklist (none cancelled)

| # | Name | Phase I status |
|---|---|---|
| 1 | Identity | Core module (JWT issuer) |
| 2 | Tenant | Core (same DB as identity) |
| 3 | Order | Core |
| 4 | Shipment | Core |
| 5 | Fleet | Core (vehicles/types/maintenance/fuel) |
| 6 | Driver | Core (not split from fleet until a team exists) |
| 7 | Dispatch | Core apply + G worker; extract solver only if CPU demands |
| 8 | Route | Core |
| 9 | Tracking | **Service** |
| 10 | Pricing | Core stub |
| 11 | Notification | **Worker** (HTTP later) |
| 12 | Analytics | **Service** |
| 13 | AI | **Service** |
| 14 | Document/RAG | Indexer + ES; HTTP next to AI or Core until embed scale |

---

## 9. What you should be able to explain after I

- Bounded context vs process: “Driver service” is a module until it needs a separate SLO.
- Why Tracking and AI were first (ingest/WS vs LLM runtime).
- Federation `@key` on `Vehicle` and why the browser still has one GraphQL URL.
- Why MFEs share auth but not databases.
- Failure: Tracking down → orders still create; map stale; agent `get_vehicle_live` errors honestly.
- Dual-write still forbidden: Core outbox, not “Core HTTP + Tracking HTTP in one controller.”

---

## 10. Phase I done when

- [x] Tracking process owns GPS, Redis latest, Mongo history, `/ws/fleet`
- [x] AI process owns `/ai/runs` and talks to Core/Tracking/ES via network tools
- [x] Analytics process serves KPI fields; Kafka still the input
- [x] Apollo/Hive gateway composes subgraphs; original `dashboard { … }` still works
- [x] Next.js shell loads ≥2 remotes (Fleet + Orders or Fleet + AI)
- [x] JWT JWKS validation on every service; tenant leak tests still pass
- [x] Core without Tracking still accepts `POST /orders`
- [x] Compose file: postgres, redis, redpanda, mongo, es, core, tracking, ai, gateway, shell

---

## Architecture series complete

Docs A–I are the build bible. **Next work is not more slides** — it is Phase A in code: Django project, schema migrations, tenant queryset, Bangalore seed.

Suggested implementation order stays the roadmap: **A → B → C → demo map → D → E → F → G → H → I.** Skipping to I with empty services teaches Docker Compose, not FleetIQ.
