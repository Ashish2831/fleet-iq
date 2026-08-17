# Phase B — API + Next.js shell

**Goal:** One REST API for writes and resource CRUD, one GraphQL schema on the **same Django process** as the BFF for reads, one Next.js app with route groups that later become microfrontends. Auth carries `tenant_id`. No Kafka, Redis map, or federation yet.

**Depends on:** Phase A models, tenant queryset, Bangalore seed.

**Out of scope for B (still on the roadmap):** Django Channels, Redis live state, Kafka, MongoDB, Elasticsearch, LangGraph, Module Federation, Apollo Federation.

---

## 1. Why REST *and* GraphQL

Companies use both. You will too.

| Surface | Role | Why |
|---|---|---|
| **REST** | Commands: create order, assign route, CRUD drivers/vehicles | Idempotency keys, status codes, file uploads (POD later), easy for the driver app |
| **GraphQL** | Queries: dashboard, nested fleet/order screens | One round-trip for the ops UI; N+1 practice; later federation |

Do **not** mutation-everything through GraphQL in B. Mutations exist in GraphQL as a learning exercise for 2–3 operations (`confirmOrder`, `assignRoute`). The rest stay REST.

```
Next.js (one app, route groups)
        │
        ├── REST   /api/v1/...     writes + lists that pagination tools expect
        └── GraphQL /graphql        dashboard + nested reads
                │
         Django (one process)
                │
           PostgreSQL
```

Phase I turns `/graphql` into a gateway that federates extracted services. The **schema shape does not change**.

---

## 2. Repo layout (monorepo)

```
FleetIQ/
  backend/                      # Django
    config/
      settings/
      urls.py                   # /api/v1/, /graphql, /health
      schema.py                 # Strawberry compose
    apps/
      identity/
      fleet/
      catalog/
      orders/
      shipments/
      routing/
      billing/
      common/
      api/                      # REST routers, permissions, pagination
        rest/
        graphql/                # types, dataloaders, root Query
  apps/web/                     # Next.js App Router (Phase I: this becomes the shell)
    app/
      (auth)/
      (fleet)/                  # later: Fleet MFE
      (dispatch)/               # later: Dispatch MFE
      (orders)/                 # later: Orders MFE
      (analytics)/              # later: Analytics MFE
      (ai)/                     # later: AI MFE (empty until H)
    lib/
      graphql/
      rest/
      auth/
  docs/
```

Route groups now = MFE domains later. That is how you keep microfrontends without building them yet.

---

## 3. Auth and tenancy

### Token

JWT (access + refresh). Claims:

```json
{
  "sub": "<user uuid>",
  "tid": "<tenant uuid>",
  "roles": ["ops_manager"],
  "perms": ["orders.order.create", "fleet.vehicle.read"]
}
```

- `tid` is the only tenant the request may see.
- Never take `tenant_id` from query/body/headers as an override (except a future superuser impersonation that is audited).
- Refresh token in **httpOnly, Secure, SameSite=Lax** cookie. Access token in memory on the Next.js client, or also httpOnly if you BFF all calls through Next route handlers.

For learning both patterns:

1. Browser → Next.js Route Handler (`/api/proxy/...`) attaches cookies and calls Django.
2. Or browser → Django with CORS + cookie. Simpler; use this in B. Switch to BFF proxy when you add GraphQL persisted queries / CSRF discipline.

### Django request context

```python
# common/tenancy.py
class TenantMiddleware:
    def __call__(self, request):
        request.tenant_id = getattr(request.user, "tenant_id", None)
        return self.get_response(request)
```

Managers:

```python
class TenantQuerySet(models.QuerySet):
    def for_tenant(self, tenant_id):
        return self.filter(tenant_id=tenant_id)
```

Every REST view and GraphQL resolver starts with `qs.for_tenant(info.context.tenant_id)`. Tests must include a second tenant and assert 404, not 200 with empty-or-worse leak.

### Permissions

RBAC from Phase A:

| Role | REST / GraphQL |
|---|---|
| `owner` | all |
| `ops_manager` | dashboard, assign, read all ops |
| `dispatcher` | orders, routes, assign |
| `driver` | own route + own deliveries (later mobile) |
| `viewer` | read-only GraphQL |

REST: DRF `DjangoObjectPermissions` or a thin `HasPerm('orders.order.create')`.

GraphQL: same permission functions on fields. Hide `assignRoute` if the user cannot dispatch.

---

## 4. REST API

Use **Django REST Framework**. Interviews expect it; ViewSets + routers + filters are the company default. (Django Ninja is fine as extra credit, not the primary surface.)

### Conventions

| Topic | Rule |
|---|---|
| Prefix | `/api/v1/` |
| IDs | UUID path params |
| Errors | RFC 7807-ish `{ "type", "title", "status", "detail", "errors": [] }` |
| Pagination | cursor (`created_at,id`) for events later; limit/offset OK for admin lists |
| Filtering | `django-filter` (`?status=in_transit&city=Bengaluru`) |
| Idempotency | header `Idempotency-Key` on POST `/orders` (table `idempotency_keys`) |
| Versioning | URL `/v1/` only. Do not invent Accept-header versioning yet |

`idempotency_keys` (add in B, used for Kafka-ish thinking before Kafka):

```sql
CREATE TABLE idempotency_keys (
    id              UUID PRIMARY KEY,
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    key             VARCHAR(128) NOT NULL,
    method          VARCHAR(8) NOT NULL,
    path            VARCHAR(255) NOT NULL,
    request_hash    CHAR(64) NOT NULL,
    response_code   INTEGER,
    response_body   JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, key)
);
```

Same key + different body → **409**. Same key + same body → replay stored response.

### Resource map

| Method | Path | Notes |
|---|---|---|
| POST | `/api/v1/auth/login` | issue JWT |
| POST | `/api/v1/auth/refresh` | cookie |
| GET/PATCH | `/api/v1/me` | |
| GET/POST | `/api/v1/drivers` | |
| GET/PATCH | `/api/v1/drivers/{id}` | |
| GET/POST | `/api/v1/vehicles` | |
| GET/PATCH | `/api/v1/vehicles/{id}` | |
| GET/POST | `/api/v1/warehouses` | |
| GET/POST | `/api/v1/customers` | nested addresses |
| GET/POST | `/api/v1/orders` | atomic: order + items + **outbox** |
| GET | `/api/v1/orders/{id}` | `select_related` customer, warehouse |
| POST | `/api/v1/orders/{id}/confirm` | state machine |
| GET/POST | `/api/v1/shipments` | |
| POST | `/api/v1/shipments/{id}/plan` | attach to existing draft route or create |
| GET/POST | `/api/v1/routes` | |
| POST | `/api/v1/routes/{id}/assign` | driver + vehicle; write outbox `DriverAssigned` row |
| GET | `/api/v1/deliveries` | `?status=delayed` server-defined filter |
| GET | `/api/v1/health` | liveness |
| GET | `/api/v1/ready` | DB ping |

Driver app later (Phase C) gets `POST /api/v1/tracking/locations` — do not build it here.

### Order status machine (enforce in the service layer)

```
created → confirmed → planned → in_transit → partially_delivered → delivered
       ↘ cancelled
```

Illegal transition → **409**, not 400. That distinction shows up in interviews.

### Serializers

- Write serializers: explicit fields, no `fields = '__all__'`.
- Read serializers: nest what the screen needs; do not nest infinite graphs (that is why GraphQL exists).
- `select_related` / `prefetch_related` in `get_queryset()`, not in the serializer.

---

## 5. GraphQL (Strawberry on Django)

One schema. One endpoint `POST /graphql`. GraphiQL in DEBUG only.

Composer:

```
config/schema.py
  Query: IdentityQuery, FleetQuery, OrderQuery, RoutingQuery, DashboardQuery
  Mutation: OrderMutation (confirmOrder), RoutingMutation (assignRoute)
```

Each Django app owns its types (`apps/fleet/graphql.py`). That is the **subunit** Apollo Federation will replace in Phase I (`extend type Query` per service). You learn the boundary now.

### Root query (the original dashboard plus real entities)

```graphql
type Query {
  me: User!

  dashboard: Dashboard!

  driver(id: ID!): Driver
  drivers(status: DriverStatus, hasVehicle: Boolean, first: Int = 20, after: String): DriverConnection!

  vehicle(id: ID!): Vehicle
  vehicles(status: VehicleStatus, first: Int, after: String): VehicleConnection!

  order(id: ID!): Order
  orders(status: OrderStatus, first: Int, after: String): OrderConnection!

  shipment(id: ID!): Shipment
  shipments(status: ShipmentStatus, delayed: Boolean, city: String): ShipmentConnection!

  route(id: ID!): Route
  routes(date: Date, status: RouteStatus): RouteConnection!
}

type Dashboard {
  activeVehicles: Int!
  activeDrivers: Int!
  delayedDeliveries: Int!
  inTransitShipments: Int!
  routes: [DashboardRoute!]!
}

type DashboardRoute {
  id: ID!
  routeNumber: String!
  status: RouteStatus!
  driverName: String
  vehiclePlate: String
  stopCount: Int!
  completedStops: Int!
  eta: DateTime          # Phase B: max(planned_arrival) on remaining stops
}
```

Relay-style connections (`edges/node/cursor`) on lists. Learn cursors once; ES and Kafka UIs reuse the idea.

### Nested types (practice DataLoader)

```graphql
type Order {
  id: ID!
  orderNumber: String!
  status: OrderStatus!
  deadlineAt: DateTime
  customer: Customer!
  warehouse: Warehouse!
  items: [OrderItem!]!
  shipments: [Shipment!]!
}

type Route {
  id: ID!
  status: RouteStatus!
  assignment: RouteAssignment
  stops: [RouteStop!]!
}

type RouteStop {
  id: ID!
  sequence: Int!
  stopType: StopType!
  status: StopStatus!
  address: Address!
  shipment: Shipment
  delivery: Delivery
}
```

If `customer` is resolved with `Customer.objects.get(id=...)` per order in a list, you have N+1. That is the GraphQL lesson.

### DataLoader (required, not optional)

```python
class CustomerByIdLoader(DataLoader):
    async def batch_load_fn(self, keys):
        tenant_id = get_tenant()
        rows = Customer.objects.filter(tenant_id=tenant_id, id__in=keys)
        by_id = {str(c.id): c for c in rows}
        return [by_id.get(k) for k in keys]
```

Loaders live on GraphQL context, one request lifespan. Types to implement in B:

- `CustomerById`, `WarehouseById`, `AddressById`
- `DriverById`, `VehicleById`
- `ItemsByOrderId`, `StopsByRouteId`
- `AssignmentByRouteId`

Prove it: Django `assertNumQueries` on `orders { customer { name } items { sku } }` for 10 orders. Bound queries, not 1+10+10.

### Auth on GraphQL

- HTTP `Authorization: Bearer` or the same cookie as REST.
- Unauthenticated → error on `me` and `dashboard`; do not return a public schema dump of tenant data.
- Introspection off in production.

### Mutations (minimal)

```graphql
type Mutation {
  confirmOrder(id: ID!): Order!
  assignRoute(routeId: ID!, driverId: ID!, vehicleId: ID!): Route!
}
```

Both call the **same service functions** as REST. GraphQL is a transport, not a second business layer.

---

## 6. Next.js shell (not MFEs)

App Router, TypeScript, one package.

| Route group | Routes | Later MFE |
|---|---|---|
| `(auth)` | `/login` | stay in shell |
| `(fleet)` | `/vehicles`, `/drivers` | Fleet MFE |
| `(dispatch)` | `/dispatch`, `/routes` | Dispatch MFE |
| `(orders)` | `/orders`, `/orders/[id]`, `/shipments` | Orders MFE |
| `(analytics)` | `/analytics` placeholder | Analytics MFE |
| `(ai)` | `/ai-assistant` placeholder | AI MFE |

Phase C adds `/live-map` under `(fleet)`.

### Data fetching

- Server Components call GraphQL with the cookie for dashboard, order detail, route detail.
- Client Components only where you need filters/sort interaction — still GraphQL via a small `graphqlClient`.
- REST from the client for POST/PATCH (`createOrder`, `assignRoute`) until you add GraphQL mutations on those screens.

### GraphQL client

`graphql-request` or urql. Generate types with **GraphQL Code Generator** from the Django schema. That is the TypeScript lesson: schema is the contract.

### UI scope for B (do not boil the ocean)

Must exist:

1. Login
2. Dashboard — the four counts + today’s routes table (the original GraphQL example, working)
3. Orders list + order detail (items + shipments)
4. Drivers / vehicles list
5. Route detail — ordered stops

Nice-to-have: create-order form.

Map, live counts via WebSocket, AI chat: later phases.

---

## 7. Cross-cutting API concerns (learn them here)

| Concern | Implementation |
|---|---|
| **N+1** | DRF: `get_queryset` prefetch. GraphQL: DataLoader + `assertNumQueries` |
| **Pagination** | REST limit/offset + GraphQL connections |
| **Filtering** | REST query params. GraphQL args. Same service filters |
| **Validation** | Pydantic-like DRF serializers; GraphQL input types |
| **Errors** | REST status codes. GraphQL `extensions.code` (`NOT_FOUND`, `FORBIDDEN`, `CONFLICT`) |
| **Request ID** | middleware `X-Request-ID`; log it (observability later) |
| **Rate limit** | Django ratelimit or DRF throttle on `/auth/login` and POST `/orders`. Redis-backed throttle is Phase C — in B, in-memory is OK and you **document** the swap |
| **CORS** | allow the Next origin only |
| **OpenAPI** | DRF Spectacular → `/api/v1/schema/` |

---

## 8. Service layer (so REST and GraphQL stay thin)

```
apps/orders/services.py
    create_order(...)      # transaction + items + outbox
    confirm_order(...)

apps/routing/services.py
    create_route_with_stops(...)
    assign_route(...)      # driver+vehicle constraints; outbox DriverAssigned
```

Views and resolvers call services. No business rules in serializers or GraphQL types. Phase G dispatch solver lives behind `assign_route` / a new `propose_assignment`.

---

## 9. What you should be able to explain after B

- Why dashboard is GraphQL and create-order is REST.
- How DataLoader batches `customer` on a list of orders.
- Why tenant comes from the JWT, not the payload.
- How `Idempotency-Key` maps to “at-least-once clients”.
- Why Next.js route groups exist if you are “not doing MFEs yet”.
- How this GraphQL schema becomes federated: `Dashboard` stays a gateway field; `Driver` moves to Fleet subgraph.

---

## 10. Phase B done when

- [ ] `/api/v1/` covers auth, drivers, vehicles, customers, orders, shipments, routes, assign
- [ ] Create order is atomic and writes `outbox_events` (still unpublished)
- [ ] `POST /graphql` serves `dashboard { activeVehicles delayedDeliveries activeDrivers routes { id status eta } }` against seed data
- [ ] DataLoader tests: nested `orders { customer items }` stays O(1) query count vs list size
- [ ] Second tenant cannot read first tenant’s order by UUID (REST 404 and GraphQL null + NOT_FOUND)
- [ ] Next.js: login, dashboard, order detail, route detail
- [ ] OpenAPI published; GraphQL codegen types used in the web app

Next: **Phase C** — GPS ingest, Redis `vehicle:{id}` hash, Django Channels, `/live-map`, replace dashboard polling with a WebSocket tick. GraphQL `dashboard` counts can stay polled at 5s until then.
