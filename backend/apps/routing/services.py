import uuid

from django.db import transaction

from apps.common.errors import Conflict, NotFound
from apps.events.outbox import enqueue
from apps.fleet.models import Driver, Vehicle
from apps.routing.models import Route, RouteAssignment, RouteStop
from apps.shipments.models import Delivery
from apps.tracking import redis_state as rs


@transaction.atomic
def create_route_with_stops(
    *,
    tenant,
    route_number: str,
    planned_date,
    stops: list[dict],
    driver=None,
    vehicle=None,
    status: str | None = None,
) -> Route:
    """
    stops: dicts with stop_type, sequence, address, and
    warehouse (depot) or shipment (pickup/dropoff).
    A Delivery is created for every dropoff stop.
    """
    if status is None:
        status = Route.Status.ASSIGNED if driver and vehicle else Route.Status.DRAFT
    route = Route.objects.create(
        tenant=tenant,
        route_number=route_number,
        planned_date=planned_date,
        status=status,
    )
    if driver and vehicle:
        RouteAssignment.objects.create(
            tenant=tenant, route=route, driver=driver, vehicle=vehicle
        )
    created_stops = []
    for spec in stops:
        stop = RouteStop.objects.create(
            tenant=tenant,
            route=route,
            stop_type=spec["stop_type"],
            sequence=spec["sequence"],
            address=spec["address"],
            warehouse=spec.get("warehouse"),
            shipment=spec.get("shipment"),
            planned_arrival=spec.get("planned_arrival"),
            actual_arrival=spec.get("actual_arrival"),
            status=spec.get("status", RouteStop.Status.PENDING),
        )
        created_stops.append(stop)
        if stop.stop_type == RouteStop.StopType.DROPOFF:
            shipment = spec["shipment"]
            delivery_status = spec.get("delivery_status", Delivery.Status.PENDING)
            Delivery.objects.create(
                tenant=tenant,
                shipment=shipment,
                route_stop=stop,
                status=delivery_status,
                completed_at=spec.get("delivery_completed_at"),
            )
            if delivery_status == Delivery.Status.IN_TRANSIT:
                shipment.status = shipment.Status.IN_TRANSIT
                shipment.save(update_fields=["status", "updated_at"])
    enqueue(
        tenant=tenant,
        event_type="RouteCreated",
        aggregate_type="route",
        aggregate_id=route.id,
        payload={
            "route_id": str(route.id),
            "route_number": route.route_number,
            "status": route.status,
            "stop_count": len(created_stops),
        },
        partition_key=str(route.id),
    )
    return route


def assign_route(*, tenant, route_id, driver_id, vehicle_id) -> Route:
    token = str(uuid.uuid4())
    lock_key = rs.route_lock_key(tenant, route_id)
    got = rs.acquire(lock_key, token)
    if got is False:
        raise Conflict("Route is being assigned")
    try:
        return _assign_route_locked(tenant=tenant, route_id=route_id, driver_id=driver_id, vehicle_id=vehicle_id)
    finally:
        if got is True:
            rs.release(lock_key, token)


@transaction.atomic
def _assign_route_locked(*, tenant, route_id, driver_id, vehicle_id) -> Route:
    route = Route.objects.select_for_update().for_tenant(tenant).filter(id=route_id).first()
    if not route:
        raise NotFound("Route not found")
    driver = Driver.objects.for_tenant(tenant).filter(id=driver_id, deleted_at__isnull=True).first()
    vehicle = Vehicle.objects.for_tenant(tenant).filter(id=vehicle_id, deleted_at__isnull=True).first()
    if not driver or not vehicle:
        raise NotFound("Driver or vehicle not found")
    if vehicle.status == Vehicle.Status.MAINTENANCE:
        raise Conflict("Vehicle is in maintenance")
    assignment, _created = RouteAssignment.objects.update_or_create(
        route=route,
        defaults={"tenant": tenant, "driver": driver, "vehicle": vehicle},
    )
    if route.status == Route.Status.DRAFT:
        route.status = Route.Status.ASSIGNED
        route.save(update_fields=["status", "updated_at"])
    enqueue(
        tenant=tenant,
        event_type="DriverAssigned",
        aggregate_type="route",
        aggregate_id=route.id,
        payload={
            "route_id": str(route.id),
            "driver_id": str(driver.id),
            "vehicle_id": str(vehicle.id),
            "assignment_id": str(assignment.id),
        },
        partition_key=str(route.id),
    )
    return route
