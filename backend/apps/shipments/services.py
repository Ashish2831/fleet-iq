from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.common.errors import Conflict, NotFound
from apps.events.outbox import enqueue
from apps.shipments.models import Delivery, Shipment, ShipmentItem


@transaction.atomic
def create_shipment(
    *,
    tenant,
    warehouse,
    delivery_address,
    shipment_number: str,
    order_item_quantities: list[tuple],
    promised_at=None,
    status: str = Shipment.Status.PLANNED,
) -> Shipment:
    """order_item_quantities: list of (OrderItem, quantity)."""
    total = sum((Decimal(str(oi.weight_kg)) * Decimal(str(qty)) for oi, qty in order_item_quantities), Decimal("0"))
    shipment = Shipment.objects.create(
        tenant=tenant,
        warehouse=warehouse,
        delivery_address=delivery_address,
        shipment_number=shipment_number,
        promised_at=promised_at,
        status=status,
        total_weight_kg=total,
    )
    ShipmentItem.objects.bulk_create(
        [
            ShipmentItem(
                tenant=tenant,
                shipment=shipment,
                order_item=order_item,
                quantity=qty,
            )
            for order_item, qty in order_item_quantities
        ]
    )
    return shipment


@transaction.atomic
def complete_delivery(*, tenant, delivery_id, failed: bool = False, reason: str = "") -> Delivery:
    delivery = (
        Delivery.objects.select_for_update()
        .select_related("shipment")
        .for_tenant(tenant)
        .filter(id=delivery_id)
        .first()
    )
    if not delivery:
        raise NotFound("Delivery not found")
    if delivery.status in (Delivery.Status.COMPLETED, Delivery.Status.FAILED):
        raise Conflict(f"Delivery already {delivery.status}")
    if failed:
        delivery.status = Delivery.Status.FAILED
        delivery.failure_reason = reason
        event_type = "DeliveryFailed"
        shipment_status = Shipment.Status.FAILED
    else:
        delivery.status = Delivery.Status.COMPLETED
        delivery.completed_at = timezone.now()
        event_type = "DeliveryCompleted"
        shipment_status = Shipment.Status.DELIVERED
    delivery.save()
    shipment = delivery.shipment
    shipment.status = shipment_status
    shipment.save(update_fields=["status", "updated_at"])
    enqueue(
        tenant=tenant,
        event_type=event_type,
        aggregate_type="shipment",
        aggregate_id=shipment.id,
        payload={
            "delivery_id": str(delivery.id),
            "shipment_id": str(shipment.id),
            "status": delivery.status,
            "reason": reason,
        },
        partition_key=str(shipment.id),
    )
    return delivery
