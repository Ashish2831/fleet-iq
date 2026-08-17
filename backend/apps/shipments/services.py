from decimal import Decimal

from django.db import transaction

from apps.shipments.models import Shipment, ShipmentItem


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
