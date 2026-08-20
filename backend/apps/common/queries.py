from django.db.models import Count, Exists, F, OuterRef, Prefetch, Q, Subquery, Window
from django.db.models.functions import RowNumber
from django.utils import timezone

from apps.common.repositories import (
    DeliveryRepository,
    DriverRepository,
    FuelTransactionRepository,
    MaintenanceRecordRepository,
    RouteRepository,
    RouteStopRepository,
    ShipmentRepository,
    VehicleAssignmentRepository,
    VehicleRepository,
)
from apps.common.sanitize import sanitize_text
from apps.fleet.models import Driver
from apps.routing.models import Route
from apps.shipments.models import Delivery, Shipment


def routes_for_day(tenant, day):
    return (
        RouteRepository(tenant)
        .tenant_qs()
        .filter(planned_date=day)
        .select_related(
            "assignment__driver",
            "assignment__vehicle__vehicle_type",
        )
        .prefetch_related(
            Prefetch(
                "stops",
                queryset=RouteStopRepository.prefetch_ordered(),
            )
        )
    )


def available_drivers_without_vehicle(tenant):
    current_asg = VehicleAssignmentRepository.active_for_driver_subquery()
    return (
        DriverRepository(tenant)
        .qs()
        .filter(status=Driver.Status.AVAILABLE)
        .annotate(has_vehicle=Exists(current_asg))
        .filter(has_vehicle=False)
    )


def latest_fuel_cost_per_vehicle(tenant):
    latest = FuelTransactionRepository.subquery_latest_cost()
    return VehicleRepository(tenant).tenant_qs().annotate(latest_fuel_cost=Subquery(latest))


def vehicles_on_in_progress_routes(tenant):
    busy = RouteRepository(tenant).tenant_qs().filter(
        assignment__vehicle_id=OuterRef("pk"),
        status=Route.Status.IN_PROGRESS,
    )
    return VehicleRepository(tenant).tenant_qs().annotate(busy=Exists(busy)).filter(busy=True)


def delivery_counts(tenant, day=None, now=None):
    now = now or timezone.now()
    qs = DeliveryRepository(tenant).tenant_qs()
    if day is not None:
        qs = qs.filter(created_at__date=day)
    return qs.aggregate(
        total=Count("id"),
        delayed=Count(
            "id",
            filter=Q(status=Delivery.Status.IN_TRANSIT, shipment__promised_at__lt=now),
        ),
        failed=Count("id", filter=Q(status=Delivery.Status.FAILED)),
    )


def last_n_maintenance_per_vehicle(tenant, n=3):
    rn = Window(
        expression=RowNumber(),
        partition_by=[F("vehicle_id")],
        order_by=F("occurred_at").desc(),
    )
    return MaintenanceRecordRepository(tenant).ranked_per_vehicle(n=n, annotate_rn=rn)


def delayed_shipments(tenant, now=None):
    now = now or timezone.now()
    terminal = [Shipment.Status.DELIVERED, Shipment.Status.FAILED, Shipment.Status.CANCELLED]
    return (
        ShipmentRepository(tenant)
        .tenant_qs()
        .filter(promised_at__lt=now)
        .exclude(status__in=terminal)
    )


def delayed_vehicle_ids(tenant, now=None) -> set[str]:
    """Vehicles currently on an in-progress route that still has a delayed shipment."""
    ship_ids = delayed_shipments(tenant, now=now).values("id")
    ids = (
        RouteRepository(tenant)
        .tenant_qs()
        .filter(status=Route.Status.IN_PROGRESS, stops__shipment_id__in=ship_ids)
        .values_list("assignment__vehicle_id", flat=True)
        .distinct()
    )
    return {str(vid) for vid in ids if vid}


def vehicles_by_device_id(tenant, device_id: str):
    return VehicleRepository(tenant).tenant_qs().filter(
        metadata__device_id=sanitize_text(device_id, max_len=128)
    )
