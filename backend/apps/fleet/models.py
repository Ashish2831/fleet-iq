from django.contrib.postgres.fields import ArrayField
from django.contrib.postgres.indexes import GinIndex
from django.db import models
from django.db.models import Q

from apps.common.models import TenantModel, status_constraint


class VehicleType(TenantModel):
    name = models.CharField(max_length=64)
    max_weight_kg = models.DecimalField(max_digits=10, decimal_places=2)
    max_volume_m3 = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True)
    requires_skills = ArrayField(models.TextField(), default=list, blank=True)

    class Meta:
        db_table = "vehicle_types"
        constraints = [
            models.UniqueConstraint(fields=["tenant", "name"], name="uq_vehicle_types_tenant_name")
        ]


class Driver(TenantModel):
    class Status(models.TextChoices):
        AVAILABLE = "available"
        ON_TRIP = "on_trip"
        OFF_DUTY = "off_duty"
        INACTIVE = "inactive"

    user = models.ForeignKey(
        "identity.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="drivers",
    )
    employee_code = models.CharField(max_length=64)
    full_name = models.CharField(max_length=255)
    phone = models.CharField(max_length=32, blank=True)
    skills = ArrayField(models.TextField(), default=list, blank=True)
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.AVAILABLE)
    home_lat = models.FloatField(null=True, blank=True)
    home_lng = models.FloatField(null=True, blank=True)
    rating = models.DecimalField(max_digits=3, decimal_places=2, null=True, blank=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "drivers"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "employee_code"], name="uq_drivers_tenant_code"
            ),
            status_constraint("status", ("available", "on_trip", "off_duty", "inactive"), "driver_status_valid"),
        ]
        indexes = [
            models.Index(
                fields=["tenant", "status"],
                name="idx_drivers_tenant_status",
                condition=Q(deleted_at__isnull=True),
            )
        ]


class Vehicle(TenantModel):
    class Status(models.TextChoices):
        ACTIVE = "active"
        IN_USE = "in_use"
        MAINTENANCE = "maintenance"
        RETIRED = "retired"

    vehicle_type = models.ForeignKey(
        VehicleType, on_delete=models.PROTECT, related_name="vehicles"
    )
    plate_number = models.CharField(max_length=32)
    make = models.CharField(max_length=64, blank=True)
    model = models.CharField(max_length=64, blank=True)
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.ACTIVE)
    current_odometer_km = models.DecimalField(
        max_digits=12, decimal_places=1, null=True, blank=True
    )
    metadata = models.JSONField(default=dict, blank=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "vehicles"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "plate_number"], name="uq_vehicles_tenant_plate"
            ),
            status_constraint("status", ("active", "in_use", "maintenance", "retired"), "vehicle_status_valid"),
        ]
        indexes = [
            models.Index(
                fields=["tenant", "status"],
                name="idx_vehicles_tenant_status",
                condition=Q(deleted_at__isnull=True),
            ),
            GinIndex(fields=["metadata"], name="idx_vehicles_metadata"),
        ]


class VehicleAssignment(TenantModel):
    updated_at = None
    driver = models.ForeignKey(Driver, on_delete=models.CASCADE, related_name="assignments")
    vehicle = models.ForeignKey(Vehicle, on_delete=models.CASCADE, related_name="assignments")
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "vehicle_assignments"
        constraints = [
            models.CheckConstraint(
                condition=Q(ends_at__isnull=True) | Q(ends_at__gt=models.F("starts_at")),
                name="va_ends_after_start",
            ),
            models.UniqueConstraint(
                fields=["vehicle"],
                condition=Q(ends_at__isnull=True),
                name="uq_va_vehicle_current",
            ),
            models.UniqueConstraint(
                fields=["driver"],
                condition=Q(ends_at__isnull=True),
                name="uq_va_driver_current",
            ),
        ]
        indexes = [
            models.Index(fields=["driver", "starts_at"], name="idx_va_driver"),
            models.Index(fields=["vehicle", "starts_at"], name="idx_va_vehicle"),
        ]


class MaintenanceRecord(TenantModel):
    updated_at = None
    vehicle = models.ForeignKey(
        Vehicle, on_delete=models.CASCADE, related_name="maintenance_records"
    )
    kind = models.CharField(max_length=64)
    occurred_at = models.DateTimeField()
    odometer_km = models.DecimalField(max_digits=12, decimal_places=1, null=True, blank=True)
    cost = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        db_table = "maintenance_records"
        indexes = [
            models.Index(fields=["vehicle", "-occurred_at"], name="idx_maint_vehicle"),
        ]


class FuelTransaction(TenantModel):
    updated_at = None
    vehicle = models.ForeignKey(
        Vehicle, on_delete=models.CASCADE, related_name="fuel_transactions"
    )
    driver = models.ForeignKey(
        Driver, on_delete=models.SET_NULL, null=True, blank=True, related_name="fuel_transactions"
    )
    occurred_at = models.DateTimeField()
    liters = models.DecimalField(max_digits=10, decimal_places=2)
    cost = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    odometer_km = models.DecimalField(max_digits=12, decimal_places=1, null=True, blank=True)

    class Meta:
        db_table = "fuel_transactions"
        indexes = [
            models.Index(fields=["vehicle", "-occurred_at"], name="idx_fuel_vehicle"),
        ]
