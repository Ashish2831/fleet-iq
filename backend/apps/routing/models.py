from django.db import models
from django.db.models import Q

from apps.common.models import TenantModel, status_constraint


class Route(TenantModel):
    class Status(models.TextChoices):
        DRAFT = "draft"
        ASSIGNED = "assigned"
        IN_PROGRESS = "in_progress"
        COMPLETED = "completed"
        CANCELLED = "cancelled"

    route_number = models.CharField(max_length=64)
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.DRAFT)
    planned_date = models.DateField()
    planned_distance_km = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )
    planned_duration_min = models.IntegerField(null=True, blank=True)

    class Meta:
        db_table = "routes"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "route_number"], name="uq_routes_tenant_number"
            ),
            status_constraint(
                "status",
                ("draft", "assigned", "in_progress", "completed", "cancelled"),
                "route_status_valid",
            ),
        ]
        indexes = [models.Index(fields=["tenant", "planned_date"], name="idx_routes_tenant_date")]


class RouteAssignment(TenantModel):
    updated_at = None
    route = models.OneToOneField(Route, on_delete=models.CASCADE, related_name="assignment")
    driver = models.ForeignKey(
        "fleet.Driver", on_delete=models.PROTECT, related_name="route_assignments"
    )
    vehicle = models.ForeignKey(
        "fleet.Vehicle", on_delete=models.PROTECT, related_name="route_assignments"
    )
    assigned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "route_assignments"


class RouteStop(TenantModel):
    class StopType(models.TextChoices):
        DEPOT = "depot"
        PICKUP = "pickup"
        DROPOFF = "dropoff"

    class Status(models.TextChoices):
        PENDING = "pending"
        ARRIVED = "arrived"
        COMPLETED = "completed"
        SKIPPED = "skipped"
        FAILED = "failed"

    route = models.ForeignKey(Route, on_delete=models.CASCADE, related_name="stops")
    shipment = models.ForeignKey(
        "shipments.Shipment",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="stops",
    )
    warehouse = models.ForeignKey(
        "catalog.Warehouse",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="route_stops",
    )
    stop_type = models.CharField(max_length=16, choices=StopType.choices)
    sequence = models.IntegerField()
    address = models.ForeignKey(
        "catalog.Address", on_delete=models.PROTECT, related_name="route_stops"
    )
    planned_arrival = models.DateTimeField(null=True, blank=True)
    actual_arrival = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.PENDING)

    class Meta:
        db_table = "route_stops"
        constraints = [
            models.UniqueConstraint(fields=["route", "sequence"], name="uq_stops_route_seq"),
            status_constraint(
                "status",
                ("pending", "arrived", "completed", "skipped", "failed"),
                "route_stop_status_valid",
            ),
            models.CheckConstraint(
                condition=Q(stop_type__in=["depot", "pickup", "dropoff"]),
                name="route_stop_type_valid",
            ),
            models.CheckConstraint(
                condition=(
                    Q(stop_type="depot", warehouse__isnull=False, shipment__isnull=True)
                    | Q(stop_type__in=["pickup", "dropoff"], shipment__isnull=False)
                ),
                name="route_stop_type_refs",
            ),
        ]
        indexes = [
            models.Index(fields=["route", "sequence"], name="idx_stops_route"),
            models.Index(fields=["shipment"], name="idx_stops_shipment"),
        ]
