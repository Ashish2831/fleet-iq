# Domain model

Corrected from the original tree. Route is not a child of Delivery. Driver is not 1:1 with Vehicle.

```
Tenant
├── User
│     └── roles / permissions
├── Driver
├── Vehicle
│     └── VehicleType
├── VehicleAssignment          # driver ↔ vehicle, time-bounded
├── Warehouse
├── Customer
│     └── Address
├── Order                      # commercial intent
│     └── OrderItem
├── Shipment                   # physical movement unit
│     └── ShipmentItem         # order_items ↔ shipments (M:N)
├── Route                      # execution plan
│     └── RouteStop            # ordered pickup | dropoff | depot
│           └── Delivery       # outcome of a dropoff stop
├── RouteAssignment            # driver + vehicle + route
├── Payment / Invoice
├── MaintenanceRecord
└── FuelTransaction
```

Later (still in the north star, not Phase A tables): `shifts`, `zones`, `proof_of_delivery`, `incidents`, `sla_policies`, `rate_cards`. `outbox_events` is created in Phase A; the publisher is Phase D. `idempotency_keys` is added in Phase B.

---

## Cardinalities

| Relationship | Cardinality | Notes |
|---|---|---|
| Tenant → almost everything | 1:N | Every row is tenant-scoped |
| User ↔ Role | M:N | `user_roles` |
| Role ↔ Permission | M:N | `role_permissions` |
| Driver ↔ Vehicle | M:N | via `vehicle_assignments` (`starts_at`, `ends_at`) |
| Customer → Address | 1:N | Billing + delivery addresses |
| Order → OrderItem | 1:N | |
| Order ↔ Shipment | M:N | Split shipments **and** consolidation via `shipment_items` |
| Route → RouteStop | 1:N | `sequence` is unique per route |
| RouteStop → Shipment | N:1 | Pickup stop + dropoff stop can share one shipment |
| Delivery → RouteStop | 1:1 | Only dropoff stops get a delivery |
| Route → Driver, Vehicle | via `route_assignments` | One active assignment per route |

---

## Lifecycle (vertical slice you will demo later)

```
Order (created, confirmed)
  → Shipment (planned, ready)
    → Route + RouteStops (draft → assigned → in_progress)
      → RouteAssignment (driver + vehicle)
        → Delivery (pending → in_transit → completed | failed)
```

GPS and AI sit on this graph. They do not redefine it.
