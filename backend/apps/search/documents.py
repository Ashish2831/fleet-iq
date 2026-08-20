from __future__ import annotations

from datetime import datetime, timezone

from django.utils import timezone as dj_tz

from apps.common.queries import delayed_shipments
from apps.common.repositories import ShipmentRepository, VehicleAssignmentRepository
from apps.fleet.models import Driver
from apps.shipments.models import Shipment


def shipment_document(shipment: Shipment) -> dict:
    addr = shipment.delivery_address
    warehouse = shipment.warehouse
    customer = ""
    item = shipment.shipment_items.select_related("order_item__order__customer").first()
    if item:
        customer = item.order_item.order.customer.name
    driver_name = ""
    driver_id = None
    delivery = shipment.deliveries.select_related("route_stop__route__assignment__driver").first()
    if delivery and hasattr(delivery.route_stop.route, "assignment"):
        asg = delivery.route_stop.route.assignment
        driver_name = asg.driver.full_name
        driver_id = str(asg.driver_id)
    now = dj_tz.now()
    terminal = {Shipment.Status.DELIVERED, Shipment.Status.FAILED, Shipment.Status.CANCELLED}
    delayed = bool(
        shipment.promised_at
        and shipment.promised_at < now
        and shipment.status not in terminal
    )
    search_all = " ".join(
        filter(
            None,
            [
                shipment.shipment_number,
                customer,
                driver_name,
                warehouse.code,
                warehouse.name,
                addr.line1,
                addr.city,
                addr.state,
            ],
        )
    )
    loc = None
    if addr.lat is not None and addr.lng is not None:
        loc = {"lat": addr.lat, "lon": addr.lng}
    return {
        "tenant_id": str(shipment.tenant_id),
        "shipment_id": str(shipment.id),
        "shipment_number": shipment.shipment_number,
        "status": shipment.status,
        "delayed": delayed,
        "promised_at": shipment.promised_at.isoformat() if shipment.promised_at else None,
        "customer_name": customer,
        "driver_name": driver_name,
        "driver_id": driver_id,
        "warehouse_code": warehouse.code,
        "city": addr.city,
        "state": addr.state,
        "address_text": f"{addr.line1} {addr.city}",
        "location": loc,
        "weight_kg": float(shipment.total_weight_kg or 0),
        "search_all": search_all,
        "projected_at": datetime.now(timezone.utc).isoformat(),
    }


def driver_document(driver: Driver, *, lat=None, lng=None) -> dict:
    asg_repo = VehicleAssignmentRepository(driver.tenant)
    active = asg_repo.qs().filter(driver=driver, ends_at__isnull=True)
    has_vehicle = active.exists()
    if lat is None:
        lat, lng = driver.home_lat, driver.home_lng
        asg = active.select_related("vehicle").first()
        if asg:
            try:
                from apps.tracking.services import live_for_vehicle

                live = live_for_vehicle(driver.tenant, str(asg.vehicle_id))
                if live and live.get("lat") is not None:
                    lat, lng = live["lat"], live["lng"]
            except Exception:
                pass
    loc = None
    if lat is not None and lng is not None:
        loc = {"lat": float(lat), "lon": float(lng)}
    vtypes = []
    if has_vehicle:
        vtypes = list(active.values_list("vehicle__vehicle_type__name", flat=True))
    search_all = " ".join(filter(None, [driver.full_name, driver.employee_code, *list(driver.skills or [])]))
    return {
        "tenant_id": str(driver.tenant_id),
        "driver_id": str(driver.id),
        "full_name": driver.full_name,
        "status": driver.status,
        "skills": list(driver.skills or []),
        "rating": float(driver.rating) if driver.rating is not None else None,
        "vehicle_types": vtypes,
        "has_vehicle": has_vehicle,
        "location": loc,
        "search_all": search_all,
        "projected_at": datetime.now(timezone.utc).isoformat(),
    }


def shipments_for_route(route_id) -> list[Shipment]:
    return ShipmentRepository.by_route_id(route_id)


def shipments_for_order(order_id) -> list[Shipment]:
    return ShipmentRepository.by_order_id(order_id)


def is_delayed_shipment(shipment: Shipment) -> bool:
    return delayed_shipments(shipment.tenant).filter(pk=shipment.pk).exists()
