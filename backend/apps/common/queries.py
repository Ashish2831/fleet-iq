from django.db.models import Count, Exists, F, OuterRef, Prefetch, Q, Subquery, Window
from django.db.models.functions import RowNumber
from django.utils import timezone

from apps.fleet.models import Driver, FuelTransaction, MaintenanceRecord, Vehicle, VehicleAssignment
from apps.routing.models import Route, RouteStop
from apps.shipments.models import Delivery, Shipment


def routes_for_day(tenant, day):
    return (
        Route.objects.for_tenant(tenant)
        .filter(planned_date=day)
        .select_related(
            "assignment__driver",
            "assignment__vehicle__vehicle_type",
        )
        .prefetch_related(
            Prefetch(
                "stops",
                queryset=RouteStop.objects.select_related("address", "shipment").order_by("sequence"),
            )
        )
    )


def available_drivers_without_vehicle(tenant):
    current_asg = VehicleAssignment.objects.filter(driver_id=OuterRef("pk"), ends_at__isnull=True)
    return (
        Driver.objects.for_tenant(tenant)
        .filter(deleted_at__isnull=True, status=Driver.Status.AVAILABLE)
        .annotate(has_vehicle=Exists(current_asg))
        .filter(has_vehicle=False)
    )


def latest_fuel_cost_per_vehicle(tenant):
    latest = (
        FuelTransaction.objects.filter(vehicle_id=OuterRef("pk"))
        .order_by("-occurred_at")
        .values("cost")[:1]
    )
    return Vehicle.objects.for_tenant(tenant).annotate(latest_fuel_cost=Subquery(latest))


def vehicles_on_in_progress_routes(tenant):
    busy = Route.objects.filter(
        assignment__vehicle_id=OuterRef("pk"),
        status=Route.Status.IN_PROGRESS,
    )
    return Vehicle.objects.for_tenant(tenant).annotate(busy=Exists(busy)).filter(busy=True)


def delivery_counts(tenant, day=None, now=None):
    now = now or timezone.now()
    qs = Delivery.objects.for_tenant(tenant)
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
    return (
        MaintenanceRecord.objects.for_tenant(tenant)
        .annotate(
            rn=Window(
                expression=RowNumber(),
                partition_by=[F("vehicle_id")],
                order_by=F("occurred_at").desc(),
            )
        )
        .filter(rn__lte=n)
    )


def delayed_shipments(tenant, now=None):
    now = now or timezone.now()
    terminal = [Shipment.Status.DELIVERED, Shipment.Status.FAILED, Shipment.Status.CANCELLED]
    return Shipment.objects.for_tenant(tenant).filter(promised_at__lt=now).exclude(status__in=terminal)


def vehicles_by_device_id(tenant, device_id: str):
    return Vehicle.objects.for_tenant(tenant).filter(metadata__device_id=device_id)
