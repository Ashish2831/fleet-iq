from django.db import models
from django.db.models import Q

from apps.common.models import TenantModel, status_constraint


class Order(TenantModel):
    class Status(models.TextChoices):
        CREATED = "created"
        CONFIRMED = "confirmed"
        PLANNED = "planned"
        IN_TRANSIT = "in_transit"
        PARTIALLY_DELIVERED = "partially_delivered"
        DELIVERED = "delivered"
        CANCELLED = "cancelled"

    order_number = models.CharField(max_length=64)
    customer = models.ForeignKey(
        "catalog.Customer", on_delete=models.PROTECT, related_name="orders"
    )
    warehouse = models.ForeignKey(
        "catalog.Warehouse", on_delete=models.PROTECT, related_name="orders"
    )
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.CREATED)
    priority = models.SmallIntegerField(default=0)
    deadline_at = models.DateTimeField(null=True, blank=True)
    total_weight_kg = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        db_table = "orders"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "order_number"], name="uq_orders_tenant_number"
            ),
            status_constraint(
                "status",
                ("created", "confirmed", "planned", "in_transit", "partially_delivered", "delivered", "cancelled"),
                "order_status_valid",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "status"], name="idx_orders_tenant_status"),
            models.Index(
                fields=["tenant", "deadline_at"],
                name="idx_orders_deadline",
                condition=~Q(status__in=["delivered", "cancelled"]),
            ),
        ]


class OrderItem(TenantModel):
    updated_at = None
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    sku = models.CharField(max_length=64)
    description = models.CharField(max_length=255, blank=True)
    quantity = models.DecimalField(max_digits=12, decimal_places=3)
    weight_kg = models.DecimalField(max_digits=10, decimal_places=3)
    volume_m3 = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    temperature_min = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    temperature_max = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "order_items"
