from django.db import models
from django.db.models import Q

from apps.common.models import TenantModel, status_constraint


class Shipment(TenantModel):
    class Status(models.TextChoices):
        PLANNED = "planned"
        READY = "ready"
        IN_TRANSIT = "in_transit"
        DELIVERED = "delivered"
        FAILED = "failed"
        CANCELLED = "cancelled"

    shipment_number = models.CharField(max_length=64)
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.PLANNED)
    warehouse = models.ForeignKey(
        "catalog.Warehouse", on_delete=models.PROTECT, related_name="shipments"
    )
    delivery_address = models.ForeignKey(
        "catalog.Address", on_delete=models.PROTECT, related_name="shipments"
    )
    total_weight_kg = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    promised_at = models.DateTimeField(null=True, blank=True)
    items = models.ManyToManyField(
        "orders.OrderItem", through="ShipmentItem", related_name="shipments"
    )

    class Meta:
        db_table = "shipments"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "shipment_number"], name="uq_shipments_tenant_number"
            ),
            status_constraint(
                "status",
                ("planned", "ready", "in_transit", "delivered", "failed", "cancelled"),
                "shipment_status_valid",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "status"], name="idx_shipments_tenant_status"),
        ]


class ShipmentItem(TenantModel):
    updated_at = None
    shipment = models.ForeignKey(Shipment, on_delete=models.CASCADE, related_name="shipment_items")
    order_item = models.ForeignKey(
        "orders.OrderItem", on_delete=models.CASCADE, related_name="shipment_items"
    )
    quantity = models.DecimalField(max_digits=12, decimal_places=3)

    class Meta:
        db_table = "shipment_items"
        constraints = [
            models.UniqueConstraint(
                fields=["shipment", "order_item"], name="uq_shipment_item"
            )
        ]


class Delivery(TenantModel):
    class Status(models.TextChoices):
        PENDING = "pending"
        IN_TRANSIT = "in_transit"
        COMPLETED = "completed"
        FAILED = "failed"

    shipment = models.ForeignKey(Shipment, on_delete=models.CASCADE, related_name="deliveries")
    route_stop = models.OneToOneField(
        "routing.RouteStop", on_delete=models.CASCADE, related_name="delivery"
    )
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.PENDING)
    failure_reason = models.CharField(max_length=128, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "deliveries"
        constraints = [
            status_constraint("status", ("pending", "in_transit", "completed", "failed"), "delivery_status_valid")
        ]
        indexes = [
            models.Index(fields=["tenant", "status"], name="idx_deliveries_tenant_status"),
        ]
