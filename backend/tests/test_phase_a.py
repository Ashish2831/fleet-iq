from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.common.queries import (
    available_drivers_without_vehicle,
    delayed_shipments,
    delivery_counts,
    last_n_maintenance_per_vehicle,
    latest_fuel_cost_per_vehicle,
    routes_for_day,
    vehicles_by_device_id,
    vehicles_on_in_progress_routes,
)
from apps.common.repositories import (
    AddressRepository,
    CustomerRepository,
    FuelTransactionRepository,
    MaintenanceRecordRepository,
    TenantRepository,
    VehicleAssignmentRepository,
    WarehouseRepository,
)
from apps.orders.services import create_order
from apps.routing.models import Route
from apps.routing.services import create_route_with_stops
from apps.shipments.models import Delivery, Shipment
from apps.shipments.services import create_shipment
from helpers import deliveries, drivers, orders, outbox, vehicle_types, vehicles


@pytest.fixture
def tenants(db):
    a = TenantRepository().create(name="Acme", slug="acme-test")
    b = TenantRepository().create(name="Beta", slug="beta-test")
    return a, b


def _warehouse(tenant, suffix="1"):
    addr = AddressRepository(tenant).create(line1="Hub", city="Bengaluru", lat=12.97, lng=77.59)
    return WarehouseRepository(tenant).create(code=f"WH{suffix}", name="Hub", address=addr)


def _customer(tenant, name="Cust"):
    addr = AddressRepository(tenant).create(line1=name, city="Bengaluru", lat=12.93, lng=77.62)
    customer = CustomerRepository(tenant).create(name=name)
    return customer, addr


def _vehicle_stack(tenant, plate="KA01XX0001"):
    vtype = vehicle_types(tenant).create(name=f"van-{plate}", max_weight_kg=Decimal("1000"))
    driver = drivers(tenant).create(employee_code=plate, full_name="Driver " + plate)
    vehicle = vehicles(tenant).create(
        vehicle_type=vtype,
        plate_number=plate,
        metadata={"device_id": f"IMEI-{plate}"},
    )
    return driver, vehicle


@pytest.mark.django_db
def test_for_tenant_does_not_leak_orders(tenants):
    a, b = tenants
    ca, _ = _customer(a, "A Co")
    cb, addrb = _customer(b, "B Co")
    wa = _warehouse(a, "A")
    wb = _warehouse(b, "B")
    create_order(
        tenant=a,
        customer=ca,
        warehouse=wa,
        order_number="A-1",
        items=[{"sku": "S", "quantity": 1, "weight_kg": 1}],
    )
    create_order(
        tenant=b,
        customer=cb,
        warehouse=wb,
        order_number="B-1",
        items=[{"sku": "S", "quantity": 1, "weight_kg": 1}],
    )
    leaked = orders(a).qs().filter(order_number="B-1")
    assert leaked.count() == 0
    assert orders(a).count() == 1
    assert orders(b).count() == 1


@pytest.mark.django_db
def test_create_order_writes_outbox_atomically(tenants):
    a, _ = tenants
    customer, _ = _customer(a)
    warehouse = _warehouse(a)
    order = create_order(
        tenant=a,
        customer=customer,
        warehouse=warehouse,
        order_number="ACM-1",
        items=[{"sku": "COLD", "quantity": 2, "weight_kg": 5, "temperature_min": 2, "temperature_max": 8}],
    )
    events = outbox(a).tenant_qs()
    assert events.count() == 1
    ev = events.get()
    assert ev.event_type == "OrderCreated"
    assert ev.aggregate_id == order.id
    assert ev.published_at is None
    assert order.items.count() == 1


@pytest.mark.django_db
def test_order_shipment_route_delivery_lifecycle(tenants):
    a, _ = tenants
    customer, dest = _customer(a)
    warehouse = _warehouse(a)
    driver, vehicle = _vehicle_stack(a)
    VehicleAssignmentRepository(a).create(driver=driver, vehicle=vehicle, starts_at=timezone.now())
    order = create_order(
        tenant=a,
        customer=customer,
        warehouse=warehouse,
        order_number="ACM-2",
        items=[{"sku": "X", "quantity": 1, "weight_kg": 12}],
    )
    item = order.items.get()
    shipment = create_shipment(
        tenant=a,
        warehouse=warehouse,
        delivery_address=dest,
        shipment_number="SHP-1",
        order_item_quantities=[(item, item.quantity)],
        promised_at=timezone.now() + timedelta(hours=4),
    )
    route = create_route_with_stops(
        tenant=a,
        route_number="RT-1",
        planned_date=timezone.localdate(),
        driver=driver,
        vehicle=vehicle,
        stops=[
            {
                "stop_type": "depot",
                "sequence": 1,
                "address": warehouse.address,
                "warehouse": warehouse,
            },
            {
                "stop_type": "pickup",
                "sequence": 2,
                "address": warehouse.address,
                "shipment": shipment,
            },
            {
                "stop_type": "dropoff",
                "sequence": 3,
                "address": dest,
                "shipment": shipment,
            },
        ],
    )
    assert route.stops.count() == 3
    assert deliveries(a).qs().filter(shipment=shipment).count() == 1
    assert route.assignment.driver_id == driver.id
    loaded = routes_for_day(a, timezone.localdate())
    assert loaded.get().assignment.vehicle_id == vehicle.id
    assert list(loaded.get().stops.all())[0].stop_type == "depot"


@pytest.mark.django_db
def test_orm_exists_window_json_and_delay_queries(tenants):
    a, _ = tenants
    now = timezone.now()
    warehouse = _warehouse(a)
    customer, dest = _customer(a)
    d1, v1 = _vehicle_stack(a, "KA01AA0001")
    d2, v2 = _vehicle_stack(a, "KA01AA0002")
    VehicleAssignmentRepository(a).create(driver=d1, vehicle=v1, starts_at=now)
    FuelTransactionRepository(a).create(
        vehicle=v1, occurred_at=now - timedelta(days=1), liters=10, cost=Decimal("100")
    )
    FuelTransactionRepository(a).create(
        vehicle=v1, occurred_at=now, liters=12, cost=Decimal("150")
    )
    for i in range(4):
        MaintenanceRecordRepository(a).create(
            vehicle=v1,
            kind="service",
            occurred_at=now - timedelta(days=i),
        )
    bare = available_drivers_without_vehicle(a)
    assert d2 in list(bare)
    assert d1 not in list(bare)

    fuel = latest_fuel_cost_per_vehicle(a).get(pk=v1.pk)
    assert fuel.latest_fuel_cost == Decimal("150")

    maint = last_n_maintenance_per_vehicle(a, 3)
    assert maint.filter(vehicle=v1).count() == 3

    assert vehicles_by_device_id(a, "IMEI-KA01AA0001").get().id == v1.id

    order = create_order(
        tenant=a,
        customer=customer,
        warehouse=warehouse,
        order_number="DLY-1",
        items=[{"sku": "Y", "quantity": 1, "weight_kg": 1}],
    )
    shipment = create_shipment(
        tenant=a,
        warehouse=warehouse,
        delivery_address=dest,
        shipment_number="SHP-DLY",
        order_item_quantities=[(order.items.get(), Decimal("1"))],
        promised_at=now - timedelta(hours=2),
        status=Shipment.Status.IN_TRANSIT,
    )
    create_route_with_stops(
        tenant=a,
        route_number="RT-DLY",
        planned_date=timezone.localdate(),
        driver=d1,
        vehicle=v1,
        status=Route.Status.IN_PROGRESS,
        stops=[
            {
                "stop_type": "depot",
                "sequence": 1,
                "address": warehouse.address,
                "warehouse": warehouse,
            },
            {
                "stop_type": "pickup",
                "sequence": 2,
                "address": warehouse.address,
                "shipment": shipment,
            },
            {
                "stop_type": "dropoff",
                "sequence": 3,
                "address": dest,
                "shipment": shipment,
                "delivery_status": Delivery.Status.IN_TRANSIT,
            },
        ],
    )
    assert delayed_shipments(a).filter(pk=shipment.pk).exists()
    assert vehicles_on_in_progress_routes(a).filter(pk=v1.pk).exists()
    counts = delivery_counts(a, day=timezone.localdate(), now=now)
    assert counts["total"] == 1
    assert counts["delayed"] == 1
