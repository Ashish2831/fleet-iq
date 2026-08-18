from datetime import datetime, timezone

from django.core.management import call_command
from rest_framework.test import APIClient

from apps.common.models import OutboxEvent
from apps.events.bus import get_bus
from apps.events.consumers import consume_once
from apps.events.models import DailyEventCount, ProcessedEvent
from apps.events.outbox import publish_batch
from apps.events.topics import DLQ, LOCATION, ORDERS
from apps.identity.models import Tenant
from apps.orders.models import Order
from apps.orders.services import confirm_order, create_order
from apps.routing.models import Route
from apps.routing.services import assign_route
from apps.shipments.models import Delivery
from apps.shipments.services import complete_delivery
from apps.catalog.models import Customer, Warehouse
from apps.fleet.models import Driver, Vehicle


def _login(client, email="ops@acme-logistics.example", tenant="acme-logistics", password="password"):
    res = client.post(
        "/api/v1/auth/login",
        {"email": email, "password": password, "tenant": tenant},
        format="json",
    )
    assert res.status_code == 200, res.content
    return res.data["access"]


def _seed():
    call_command("seed_bangalore", reset=True)
    return Tenant.objects.get(slug="acme-logistics")


def _gps_payload(vehicle, **overrides):
    body = {
        "vehicle_id": str(vehicle.id),
        "event_id": "evt-d-1",
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "lat": 12.9716,
        "lng": 77.5946,
        "speed_kmh": 28,
        "heading": 90,
    }
    body.update(overrides)
    return body


def test_domain_writes_unpublished_outbox(db):
    tenant = _seed()
    customer = Customer.objects.for_tenant(tenant).first()
    warehouse = Warehouse.objects.for_tenant(tenant).first()
    order = create_order(
        tenant=tenant,
        customer=customer,
        warehouse=warehouse,
        order_number="D-OUTBOX-1",
        items=[{"sku": "X", "quantity": 1, "weight_kg": 1}],
    )
    row = OutboxEvent.objects.for_tenant(tenant).get(event_type="OrderCreated", aggregate_id=order.id)
    assert row.published_at is None
    assert row.topic == ORDERS
    assert row.payload["event_id"] == str(row.id)
    assert row.payload["tenant_id"] == str(tenant.id)

    confirm_order(tenant=tenant, order_id=order.id)
    confirmed = OutboxEvent.objects.for_tenant(tenant).get(event_type="OrderConfirmed", aggregate_id=order.id)
    assert confirmed.published_at is None

    route = Route.objects.for_tenant(tenant).first()
    assign_route(
        tenant=tenant,
        route_id=route.id,
        driver_id=route.assignment.driver_id,
        vehicle_id=route.assignment.vehicle_id,
    )
    assigned = OutboxEvent.objects.for_tenant(tenant).filter(event_type="DriverAssigned", aggregate_id=route.id)
    assert assigned.exists()

    delivery = Delivery.objects.for_tenant(tenant).exclude(status__in=["completed", "failed"]).first()
    complete_delivery(tenant=tenant, delivery_id=delivery.id)
    done = OutboxEvent.objects.for_tenant(tenant).get(event_type="DeliveryCompleted")
    assert done.partition_key == str(delivery.shipment_id)


def test_outbox_publisher_skip_locked_and_retry(db, memory_bus):
    tenant = _seed()
    customer = Customer.objects.for_tenant(tenant).first()
    warehouse = Warehouse.objects.for_tenant(tenant).first()
    first_order = create_order(
        tenant=tenant,
        customer=customer,
        warehouse=warehouse,
        order_number="D-PUB-1",
        items=[{"sku": "X", "quantity": 1, "weight_kg": 1}],
    )
    second_order = create_order(
        tenant=tenant,
        customer=customer,
        warehouse=warehouse,
        order_number="D-PUB-2",
        items=[{"sku": "Y", "quantity": 1, "weight_kg": 1}],
    )
    unpublished = list(
        OutboxEvent.objects.for_tenant(tenant).filter(event_type="OrderCreated", published_at__isnull=True)
    )
    assert len(unpublished) >= 2

    calls = {"n": 0}
    real_produce = memory_bus.produce

    def flaky(topic, key, value, headers=None):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("broker blip")
        return real_produce(topic, key, value, headers=headers)

    memory_bus.produce = flaky
    first = publish_batch(limit=10, bus=memory_bus)
    assert first["published"] >= 1
    assert first["failed"] >= 1
    still = OutboxEvent.objects.filter(published_at__isnull=True, event_type="OrderCreated")
    assert still.exists()
    memory_bus.produce = real_produce
    second = publish_batch(limit=100, bus=memory_bus)
    assert second["failed"] == 0
    ours = OutboxEvent.objects.filter(
        event_type="OrderCreated",
        aggregate_id__in=[first_order.id, second_order.id],
    )
    assert ours.filter(published_at__isnull=True).count() == 0
    assert any(r.value.get("event_type") == "OrderCreated" for r in memory_bus.records(ORDERS))


def test_gps_direct_produce_skips_outbox(db, memory_bus):
    tenant = _seed()
    vehicle = Vehicle.objects.for_tenant(tenant).first()
    before = OutboxEvent.objects.count()
    client = APIClient()
    token = _login(client)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    res = client.post("/api/v1/tracking/locations", _gps_payload(vehicle), format="json")
    assert res.status_code == 202, res.content
    assert OutboxEvent.objects.count() == before
    loc = memory_bus.records(LOCATION)
    assert loc
    assert loc[-1].key == str(vehicle.id)
    assert loc[-1].value["event_type"] == "VehicleLocationUpdated"
    assert loc[-1].value["tenant_id"] == str(tenant.id)


def test_gps_still_202_when_kafka_fails(db, memory_bus):
    tenant = _seed()
    vehicle = Vehicle.objects.for_tenant(tenant).first()
    client = APIClient()
    token = _login(client)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    def boom(*args, **kwargs):
        raise RuntimeError("kafka down")

    memory_bus.produce = boom
    res = client.post(
        "/api/v1/tracking/locations",
        _gps_payload(vehicle, event_id="evt-kafka-down"),
        format="json",
    )
    assert res.status_code == 202, res.content
    from apps.tracking import redis_state as rs

    pin = rs.get_redis().hgetall(rs.vehicle_key(tenant, vehicle.id))
    assert pin.get("lat")


def test_two_consumer_groups_and_inbox_dedupe(db, memory_bus):
    tenant = _seed()
    customer = Customer.objects.for_tenant(tenant).first()
    warehouse = Warehouse.objects.for_tenant(tenant).first()
    create_order(
        tenant=tenant,
        customer=customer,
        warehouse=warehouse,
        order_number="D-FANOUT",
        items=[{"sku": "Z", "quantity": 1, "weight_kg": 1}],
    )
    publish_batch(bus=memory_bus)
    n = consume_once("fleetiq-notify", bus=memory_bus)
    a = consume_once("fleetiq-analytics", bus=memory_bus)
    assert n["ok"] >= 1
    assert a["ok"] >= 1
    assert ProcessedEvent.objects.filter(consumer_name="fleetiq-notify").exists()
    assert ProcessedEvent.objects.filter(consumer_name="fleetiq-analytics").exists()
    count = DailyEventCount.objects.get(tenant=tenant, event_type="OrderCreated").count
    memory_bus.reset_group("fleetiq-analytics")
    again = consume_once("fleetiq-analytics", bus=memory_bus)
    assert again["skipped"] >= 1
    assert DailyEventCount.objects.get(tenant=tenant, event_type="OrderCreated").count == count


def test_poison_message_goes_to_dlq(db, memory_bus):
    memory_bus.produce(ORDERS, "poison", {"not": "an envelope"})
    result = consume_once("fleetiq-analytics", bus=memory_bus)
    assert result["dlq"] >= 1
    dlq = memory_bus.records(DLQ)
    assert dlq
    tenant = _seed()
    customer = Customer.objects.for_tenant(tenant).first()
    warehouse = Warehouse.objects.for_tenant(tenant).first()
    create_order(
        tenant=tenant,
        customer=customer,
        warehouse=warehouse,
        order_number="D-AFTER-POISON",
        items=[{"sku": "Q", "quantity": 1, "weight_kg": 1}],
    )
    publish_batch(bus=memory_bus)
    ok = consume_once("fleetiq-analytics", bus=memory_bus)
    assert ok["ok"] >= 1
    assert DailyEventCount.objects.filter(event_type="OrderCreated").exists()
