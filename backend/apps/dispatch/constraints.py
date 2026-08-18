from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

from apps.fleet.models import Driver, Vehicle, VehicleAssignment
from apps.routing.models import Route
from apps.telemetry.geo import haversine_m


def required_skills(order) -> set[str]:
    skills = set()
    for item in order.items.all():
        if item.temperature_min is not None or item.temperature_max is not None:
            skills.add("reefer")
    return skills


def order_weight_kg(order) -> float:
    return float(order.total_weight_kg or 0)


def current_assignment(driver: Driver) -> VehicleAssignment | None:
    return (
        VehicleAssignment.objects.select_related("vehicle", "vehicle__vehicle_type")
        .filter(driver=driver, ends_at__isnull=True)
        .first()
    )


def hard_check(*, order, driver: Driver, vehicle: Vehicle, dest, now=None) -> list[str]:
    """Return reject reasons. Empty list = pass."""
    now = now or timezone.now()
    reasons = []
    if driver.tenant_id != order.tenant_id or vehicle.tenant_id != order.tenant_id:
        reasons.append("cross_tenant")
    if driver.deleted_at is not None:
        reasons.append("driver_deleted")
    if vehicle.deleted_at is not None:
        reasons.append("vehicle_deleted")
    if vehicle.status in (Vehicle.Status.MAINTENANCE, Vehicle.Status.RETIRED):
        reasons.append("vehicle_unavailable")
    if driver.status == Driver.Status.INACTIVE:
        reasons.append("driver_inactive")
    vtype = vehicle.vehicle_type
    weight = order_weight_kg(order)
    if float(vtype.max_weight_kg) < weight:
        reasons.append("over_weight")
    need = required_skills(order)
    have = {s.lower() for s in (driver.skills or [])} | {s.lower() for s in (vtype.requires_skills or [])}
    missing = need - have
    if missing:
        reasons.append("missing_skills:" + ",".join(sorted(missing)))
    if order.deadline_at:
        eta_min = estimate_eta_min(vehicle, dest)
        if timezone.now() + timedelta(minutes=eta_min) > order.deadline_at:
            reasons.append("deadline_infeasible")
    return reasons


def estimate_eta_min(vehicle, dest, origin=None) -> float:
    if dest is None or dest.lat is None:
        return 20.0
    lat1, lng1 = origin if origin else _origin(vehicle)
    if lat1 is None:
        return 25.0
    km = haversine_m(lat1, lng1, dest.lat, dest.lng) / 1000.0
    traffic = traffic_factor()
    return (km / 22.0) * 60.0 * traffic  # 22 km/h city


def traffic_factor() -> float:
    hour = timezone.localtime().hour
    if 8 <= hour <= 10 or 17 <= hour <= 20:
        return 1.35
    return 1.0


def _origin(vehicle) -> tuple[float | None, float | None]:
    from apps.tracking.services import live_for_vehicle

    live = live_for_vehicle(vehicle.tenant, str(vehicle.id))
    if live and live.get("lat") is not None:
        return live["lat"], live["lng"]
    asg = VehicleAssignment.objects.filter(vehicle=vehicle, ends_at__isnull=True).select_related("driver").first()
    if asg and asg.driver.home_lat is not None:
        return asg.driver.home_lat, asg.driver.home_lng
    return None, None


def leftover_kg(vehicle: Vehicle, order) -> float:
    return float(vehicle.vehicle_type.max_weight_kg) - order_weight_kg(order)


def insertion_cost_km(*, vehicle, dest, route: Route | None) -> float:
    origin = _origin(vehicle)
    if dest is None or dest.lat is None or origin[0] is None:
        return 8.0
    if route is None:
        return haversine_m(origin[0], origin[1], dest.lat, dest.lng) / 1000.0
    last = route.stops.order_by("sequence").last()
    if last and last.address.lat is not None:
        extra = haversine_m(last.address.lat, last.address.lng, dest.lat, dest.lng) / 1000.0
        return extra
    return haversine_m(origin[0], origin[1], dest.lat, dest.lng) / 1000.0
