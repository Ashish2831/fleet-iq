# Phase A — Foundation

**Goal:** One Django project, one PostgreSQL database, modular apps, a correct domain, and enough ORM surface that later phases (Kafka, Redis, Mongo, ES, GraphQL, agents) plug in without a rewrite.

**Out of scope for A (still on the roadmap):** Kafka, MongoDB, Elasticsearch, GraphQL, WebSockets, LangGraph, microfrontends, service extraction.

---

## 1. Django project layout

One deployable. Apps are **module boundaries**, not microservices yet.

```
fleetiq/
  config/                 # settings, urls, asgi, celery later
  apps/
    identity/             # tenants, users, roles, permissions
    fleet/                # drivers, vehicles, assignments, maintenance, fuel
    catalog/              # warehouses, customers, addresses
    orders/               # orders, order_items
    shipments/            # shipments, shipment_items, deliveries
    routing/              # routes, route_stops, route_assignments
    billing/              # payments, invoices (stubs OK in A)
    common/               # TenantModel, timestamps, enums
```

Next.js comes in Phase B. Do not start MFEs here.

---

## 2. Conventions

| Rule | Why |
|---|---|
| `uuid` primary keys | Stable public IDs for GraphQL, Kafka, ES later |
| `tenant` FK on every tenant-owned table | Isolation; WS rooms and Redis keys will reuse this |
| `created_at` / `updated_at` | Audit + event payloads |
| Check constraints for enums | DB is source of truth, not just Python |
| Soft-delete (`deleted_at`) on drivers, vehicles, customers | History for analytics/RAG later |
| Never query without a tenant filter | Default manager / `TenantQuerySet` |

---

## 3. Canonical Postgres schema

### 3.1 Identity

```sql
CREATE TABLE tenants (
    id              UUID PRIMARY KEY,
    name            VARCHAR(255) NOT NULL,
    slug            VARCHAR(80) NOT NULL UNIQUE,
    status          VARCHAR(32) NOT NULL DEFAULT 'active'
                    CHECK (status IN ('active', 'suspended', 'trial')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE users (
    id              UUID PRIMARY KEY,
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    email           VARCHAR(255) NOT NULL,
    full_name       VARCHAR(255) NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    is_active       BOOLEAN NOT NULL DEFAULT true,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, email)
);
CREATE INDEX idx_users_tenant ON users(tenant_id);

CREATE TABLE roles (
    id          UUID PRIMARY KEY,
    tenant_id   UUID NOT NULL REFERENCES tenants(id),
    name        VARCHAR(64) NOT NULL,
    UNIQUE (tenant_id, name)
);

CREATE TABLE permissions (
    id          UUID PRIMARY KEY,
    codename    VARCHAR(128) NOT NULL UNIQUE,  -- e.g. fleet.vehicle.assign
    description TEXT
);

CREATE TABLE role_permissions (
    role_id         UUID NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    permission_id   UUID NOT NULL REFERENCES permissions(id) ON DELETE CASCADE,
    PRIMARY KEY (role_id, permission_id)
);

CREATE TABLE user_roles (
    user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role_id     UUID NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    PRIMARY KEY (user_id, role_id)
);
```

Phase A roles to seed: `owner`, `ops_manager`, `dispatcher`, `driver` (driver app user), `viewer`.

---

### 3.2 Fleet

```sql
CREATE TABLE vehicle_types (
    id              UUID PRIMARY KEY,
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    name            VARCHAR(64) NOT NULL,          -- van, reefer, bike
    max_weight_kg   NUMERIC(10,2) NOT NULL,
    max_volume_m3   NUMERIC(10,3),
    requires_skills TEXT[] DEFAULT '{}',
    UNIQUE (tenant_id, name)
);

CREATE TABLE drivers (
    id              UUID PRIMARY KEY,
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    user_id         UUID REFERENCES users(id),     -- nullable until app login exists
    employee_code   VARCHAR(64) NOT NULL,
    full_name       VARCHAR(255) NOT NULL,
    phone           VARCHAR(32),
    skills          TEXT[] NOT NULL DEFAULT '{}',  -- hazardous, reefer, heavy
    status          VARCHAR(32) NOT NULL DEFAULT 'available'
                    CHECK (status IN ('available', 'on_trip', 'off_duty', 'inactive')),
    home_lat        DOUBLE PRECISION,
    home_lng        DOUBLE PRECISION,
    rating          NUMERIC(3,2),
    deleted_at      TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, employee_code)
);
CREATE INDEX idx_drivers_tenant_status ON drivers(tenant_id, status)
    WHERE deleted_at IS NULL;

CREATE TABLE vehicles (
    id              UUID PRIMARY KEY,
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    vehicle_type_id UUID NOT NULL REFERENCES vehicle_types(id),
    plate_number    VARCHAR(32) NOT NULL,
    make            VARCHAR(64),
    model           VARCHAR(64),
    status          VARCHAR(32) NOT NULL DEFAULT 'active'
                    CHECK (status IN ('active', 'in_use', 'maintenance', 'retired')),
    current_odometer_km NUMERIC(12,1),
    metadata        JSONB NOT NULL DEFAULT '{}',   -- sensors, telematics device id
    deleted_at      TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, plate_number)
);
CREATE INDEX idx_vehicles_tenant_status ON vehicles(tenant_id, status)
    WHERE deleted_at IS NULL;
CREATE INDEX idx_vehicles_metadata ON vehicles USING GIN (metadata);

CREATE TABLE vehicle_assignments (
    id              UUID PRIMARY KEY,
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    driver_id       UUID NOT NULL REFERENCES drivers(id),
    vehicle_id      UUID NOT NULL REFERENCES vehicles(id),
    starts_at       TIMESTAMPTZ NOT NULL,
    ends_at         TIMESTAMPTZ,                   -- NULL = current
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (ends_at IS NULL OR ends_at > starts_at)
);
CREATE INDEX idx_va_driver ON vehicle_assignments(driver_id, starts_at);
CREATE INDEX idx_va_vehicle ON vehicle_assignments(vehicle_id, starts_at);
CREATE UNIQUE INDEX uq_va_vehicle_current
    ON vehicle_assignments(vehicle_id) WHERE ends_at IS NULL;
CREATE UNIQUE INDEX uq_va_driver_current
    ON vehicle_assignments(driver_id) WHERE ends_at IS NULL;

CREATE TABLE maintenance_records (
    id              UUID PRIMARY KEY,
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    vehicle_id      UUID NOT NULL REFERENCES vehicles(id),
    kind            VARCHAR(64) NOT NULL,          -- service, repair, inspection
    occurred_at     TIMESTAMPTZ NOT NULL,
    odometer_km     NUMERIC(12,1),
    cost            NUMERIC(12,2),
    notes           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_maint_vehicle ON maintenance_records(vehicle_id, occurred_at DESC);

CREATE TABLE fuel_transactions (
    id              UUID PRIMARY KEY,
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    vehicle_id      UUID NOT NULL REFERENCES vehicles(id),
    driver_id       UUID REFERENCES drivers(id),
    occurred_at     TIMESTAMPTZ NOT NULL,
    liters          NUMERIC(10,2) NOT NULL,
    cost            NUMERIC(12,2),
    odometer_km     NUMERIC(12,1),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_fuel_vehicle ON fuel_transactions(vehicle_id, occurred_at DESC);
```

---

### 3.3 Catalog (warehouses, customers)

```sql
CREATE TABLE addresses (
    id              UUID PRIMARY KEY,
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    line1           VARCHAR(255) NOT NULL,
    line2           VARCHAR(255),
    city            VARCHAR(128) NOT NULL,
    state           VARCHAR(128),
    postal_code     VARCHAR(32),
    country         CHAR(2) NOT NULL DEFAULT 'IN',
    lat             DOUBLE PRECISION,
    lng             DOUBLE PRECISION,
    geohash         VARCHAR(16),                   -- later: geo queries before ES
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_addresses_tenant_city ON addresses(tenant_id, city);

CREATE TABLE warehouses (
    id              UUID PRIMARY KEY,
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    code            VARCHAR(32) NOT NULL,
    name            VARCHAR(255) NOT NULL,
    address_id      UUID NOT NULL REFERENCES addresses(id),
    status          VARCHAR(32) NOT NULL DEFAULT 'active',
    UNIQUE (tenant_id, code)
);

CREATE TABLE customers (
    id              UUID PRIMARY KEY,
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    name            VARCHAR(255) NOT NULL,
    email           VARCHAR(255),
    phone           VARCHAR(32),
    deleted_at      TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_customers_tenant_name ON customers(tenant_id, name);

CREATE TABLE customer_addresses (
    id              UUID PRIMARY KEY,
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    customer_id     UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    address_id      UUID NOT NULL REFERENCES addresses(id),
    label           VARCHAR(32) NOT NULL DEFAULT 'delivery',  -- billing, delivery
    is_default      BOOLEAN NOT NULL DEFAULT false
);
```

---

### 3.4 Orders and shipments

```sql
CREATE TABLE orders (
    id              UUID PRIMARY KEY,
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    order_number    VARCHAR(64) NOT NULL,
    customer_id     UUID NOT NULL REFERENCES customers(id),
    warehouse_id    UUID NOT NULL REFERENCES warehouses(id),
    status          VARCHAR(32) NOT NULL DEFAULT 'created'
                    CHECK (status IN (
                        'created', 'confirmed', 'planned',
                        'in_transit', 'partially_delivered',
                        'delivered', 'cancelled'
                    )),
    priority        SMALLINT NOT NULL DEFAULT 0,
    deadline_at     TIMESTAMPTZ,
    total_weight_kg NUMERIC(10,2),
    notes           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, order_number)
);
CREATE INDEX idx_orders_tenant_status ON orders(tenant_id, status);
CREATE INDEX idx_orders_deadline ON orders(tenant_id, deadline_at)
    WHERE status NOT IN ('delivered', 'cancelled');

CREATE TABLE order_items (
    id              UUID PRIMARY KEY,
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    order_id        UUID NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    sku             VARCHAR(64) NOT NULL,
    description     VARCHAR(255),
    quantity        NUMERIC(12,3) NOT NULL,
    weight_kg       NUMERIC(10,3) NOT NULL,
    volume_m3       NUMERIC(10,4),
    temperature_min NUMERIC(5,2),
    temperature_max NUMERIC(5,2),
    metadata        JSONB NOT NULL DEFAULT '{}'
);

CREATE TABLE shipments (
    id              UUID PRIMARY KEY,
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    shipment_number VARCHAR(64) NOT NULL,
    status          VARCHAR(32) NOT NULL DEFAULT 'planned'
                    CHECK (status IN (
                        'planned', 'ready', 'in_transit',
                        'delivered', 'failed', 'cancelled'
                    )),
    warehouse_id    UUID NOT NULL REFERENCES warehouses(id),
    delivery_address_id UUID NOT NULL REFERENCES addresses(id),
    total_weight_kg NUMERIC(10,2),
    promised_at     TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, shipment_number)
);
CREATE INDEX idx_shipments_tenant_status ON shipments(tenant_id, status);

CREATE TABLE shipment_items (
    id              UUID PRIMARY KEY,
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    shipment_id     UUID NOT NULL REFERENCES shipments(id) ON DELETE CASCADE,
    order_item_id   UUID NOT NULL REFERENCES order_items(id),
    quantity        NUMERIC(12,3) NOT NULL,
    UNIQUE (shipment_id, order_item_id)
);
```

---

### 3.5 Routing and deliveries

```sql
CREATE TABLE routes (
    id              UUID PRIMARY KEY,
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    route_number    VARCHAR(64) NOT NULL,
    status          VARCHAR(32) NOT NULL DEFAULT 'draft'
                    CHECK (status IN (
                        'draft', 'assigned', 'in_progress',
                        'completed', 'cancelled'
                    )),
    planned_date    DATE NOT NULL,
    planned_distance_km NUMERIC(10,2),
    planned_duration_min INTEGER,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, route_number)
);
CREATE INDEX idx_routes_tenant_date ON routes(tenant_id, planned_date);

CREATE TABLE route_assignments (
    id              UUID PRIMARY KEY,
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    route_id        UUID NOT NULL REFERENCES routes(id),
    driver_id       UUID NOT NULL REFERENCES drivers(id),
    vehicle_id      UUID NOT NULL REFERENCES vehicles(id),
    assigned_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (route_id)          -- one active plan per route in Phase A
);

CREATE TABLE route_stops (
    id              UUID PRIMARY KEY,
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    route_id        UUID NOT NULL REFERENCES routes(id) ON DELETE CASCADE,
    shipment_id     UUID REFERENCES shipments(id),
    warehouse_id    UUID REFERENCES warehouses(id),
    stop_type       VARCHAR(16) NOT NULL
                    CHECK (stop_type IN ('depot', 'pickup', 'dropoff')),
    sequence        INTEGER NOT NULL,
    address_id      UUID NOT NULL REFERENCES addresses(id),
    planned_arrival TIMESTAMPTZ,
    actual_arrival  TIMESTAMPTZ,
    status          VARCHAR(32) NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'arrived', 'completed', 'skipped', 'failed')),
    UNIQUE (route_id, sequence),
    CHECK (
        (stop_type = 'depot'  AND warehouse_id IS NOT NULL AND shipment_id IS NULL) OR
        (stop_type IN ('pickup', 'dropoff') AND shipment_id IS NOT NULL)
    )
);
CREATE INDEX idx_stops_route ON route_stops(route_id, sequence);
CREATE INDEX idx_stops_shipment ON route_stops(shipment_id);

CREATE TABLE deliveries (
    id              UUID PRIMARY KEY,
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    shipment_id     UUID NOT NULL REFERENCES shipments(id),
    route_stop_id   UUID NOT NULL UNIQUE REFERENCES route_stops(id),
    status          VARCHAR(32) NOT NULL DEFAULT 'pending'
                    CHECK (status IN (
                        'pending', 'in_transit', 'completed', 'failed'
                    )),
    failure_reason  VARCHAR(128),
    completed_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_deliveries_tenant_status ON deliveries(tenant_id, status);
```

A delivery exists **only** for `dropoff` stops. Create it when the stop is created, or when the route is assigned — pick one in code and keep it consistent.

---

### 3.6 Billing (stub tables, real later)

```sql
CREATE TABLE invoices (
    id              UUID PRIMARY KEY,
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    customer_id     UUID NOT NULL REFERENCES customers(id),
    invoice_number  VARCHAR(64) NOT NULL,
    amount          NUMERIC(12,2) NOT NULL,
    status          VARCHAR(32) NOT NULL DEFAULT 'draft',
    UNIQUE (tenant_id, invoice_number)
);

CREATE TABLE payments (
    id              UUID PRIMARY KEY,
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    invoice_id      UUID NOT NULL REFERENCES invoices(id),
    amount          NUMERIC(12,2) NOT NULL,
    status          VARCHAR(32) NOT NULL DEFAULT 'pending',
    paid_at         TIMESTAMPTZ
);
```

---

### 3.7 Hook for Phase D (create the table now, no worker yet)

```sql
CREATE TABLE outbox_events (
    id              UUID PRIMARY KEY,
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    aggregate_type  VARCHAR(64) NOT NULL,          -- order, shipment, route
    aggregate_id    UUID NOT NULL,
    event_type      VARCHAR(128) NOT NULL,         -- OrderCreated
    payload         JSONB NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    published_at    TIMESTAMPTZ
);
CREATE INDEX idx_outbox_unpublished
    ON outbox_events(created_at)
    WHERE published_at IS NULL;
```

Insert into `outbox_events` in the same transaction as `orders`. Do **not** publish Kafka in Phase A. Phase D adds the worker.

---

## 4. Django model sketch (patterns, not a dump)

```python
class TenantModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey("identity.Tenant", on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
```

Every concrete model inherits this (except `Tenant`, `Permission`).

Use Postgres-specific fields where they earn their keep:

| Field | Use on |
|---|---|
| `ArrayField` | `Driver.skills`, `VehicleType.requires_skills` |
| `JSONField` | `Vehicle.metadata`, `OrderItem.metadata`, `OutboxEvent.payload` |
| `DecimalField` | money, weight, liters |
| `DateTimeField` | deadlines, GPS later (Phase C+) |

---

## 5. ORM practice map

Do these as management commands or pytest against seeded Bangalore data. Each maps to an interview talking point.

### Joins and relation loading

| Practice | Query |
|---|---|
| `select_related` | Route → assignment → driver, vehicle, vehicle_type |
| `prefetch_related` | Order → items; Route → stops → shipment |
| Nested prefetch | `Prefetch("stops", queryset=RouteStop.objects.select_related("address", "shipment"))` |

```python
Route.objects.filter(tenant=tenant, planned_date=day).select_related(
    "assignment__driver",
    "assignment__vehicle__vehicle_type",
).prefetch_related(
    Prefetch(
        "stops",
        queryset=RouteStop.objects.select_related("address", "shipment").order_by("sequence"),
    )
)
```

### Existence and subqueries

| Practice | Question |
|---|---|
| `Exists` / `OuterRef` | Drivers with no current `vehicle_assignment` (`ends_at IS NULL`) |
| `Subquery` | Latest fuel cost per vehicle |
| `exclude(id__in=...)` vs `Exists` | Vehicles already assigned to an in-progress route |

```python
current_asg = VehicleAssignment.objects.filter(
    driver_id=OuterRef("pk"),
    ends_at__isnull=True,
)
Driver.objects.filter(tenant=tenant, deleted_at__isnull=True).annotate(
    has_vehicle=Exists(current_asg)
).filter(has_vehicle=False, status="available")
```

### Aggregation and window functions

| Practice | Question |
|---|---|
| `Count`, `Sum` | Deliveries today by status (dashboard seed for GraphQL later) |
| `Case` / `When` | Delayed = promised_at < now() AND status not terminal |
| `Window` + `RowNumber` | Last 3 maintenance records per vehicle |
| CTE via `with_cte` (django-cte) or RawSQL | Recursive? Not needed. Use CTE for “routes whose any stop city = Whitefield” |

```python
from django.db.models import Count, Q, Case, When, IntegerField

Delivery.objects.filter(tenant=tenant, created_at__date=today).aggregate(
    total=Count("id"),
    delayed=Count("id", filter=Q(status="in_transit", shipment__promised_at__lt=now)),
    failed=Count("id", filter=Q(status="failed")),
)
```

```python
from django.db.models import F, Window
from django.db.models.functions import RowNumber

MaintenanceRecord.objects.annotate(
    rn=Window(expression=RowNumber(), partition_by=[F("vehicle_id")], order_by=F("occurred_at").desc())
).filter(rn__lte=3)
```

### Constraints, transactions, JSON

| Practice | Where |
|---|---|
| `transaction.atomic` | Create order + items + outbox row |
| `select_for_update` | Later dispatch lock; practice on `orders` when confirming |
| `JSONField` contains | `vehicles.filter(metadata__device_id="IMEI-...")` |
| Unique partial indexes | Current vehicle assignment (one open `ends_at`) |
| CheckConstraint | Route stop type vs shipment/warehouse FKs |

Order creation (this is the Phase D hook):

```python
with transaction.atomic():
    order = Order.objects.create(...)
    OrderItem.objects.bulk_create(items)
    OutboxEvent.objects.create(
        tenant=order.tenant,
        aggregate_type="order",
        aggregate_id=order.id,
        event_type="OrderCreated",
        payload={"order_id": str(order.id), "order_number": order.order_number},
    )
```

Worker comes in Phase D. The **pattern** is learned in A.

---

## 6. Seed data (make later phases easy)

One tenant: `acme-logistics`, city Bangalore.

- 2 warehouses (Peenya, Whitefield depot)
- 8 customers with addresses (Whitefield, Koramangala, Indiranagar, …)
- 12 drivers, 10 vehicles (mix of van / reefer / bike)
- 20 orders, some split into 2 shipments
- 4 routes with 5–8 stops each
- A handful of delayed deliveries (`promised_at` in the past, status `in_transit`)

That seed is what the live map, ES query “delayed in Bangalore”, and Operations Agent will all reuse.

---

## 7. Phase A done when

- [ ] `apps/` exist; models migrate cleanly
- [ ] Tenant queryset cannot leak another tenant’s orders
- [ ] You can create Order → Shipment(s) → Route → Stops → Delivery in one service layer
- [ ] Outbox row is written in the same transaction as the order
- [ ] The ORM queries in §5 exist as tests and you can explain each one
- [ ] Seed command loads Bangalore demo data

Next: **Phase B** — Django Ninja or DRF for REST, then a single Strawberry GraphQL schema on the same process (`dashboard`, `orders`, `fleet`). One Next.js app (no MFEs yet) consuming GraphQL.
