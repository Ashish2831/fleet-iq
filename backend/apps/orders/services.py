from decimal import Decimal

from django.db import transaction

from apps.common.errors import Conflict, NotFound
from apps.common.repositories import OrderItemRepository, OrderRepository
from apps.common.sanitize import sanitize_text
from apps.events.outbox import enqueue
from apps.orders.models import Order, OrderItem

ALLOWED = {
    Order.Status.CREATED: {Order.Status.CONFIRMED, Order.Status.CANCELLED},
    Order.Status.CONFIRMED: {Order.Status.PLANNED, Order.Status.CANCELLED},
    Order.Status.PLANNED: {Order.Status.IN_TRANSIT, Order.Status.CANCELLED},
    Order.Status.IN_TRANSIT: {
        Order.Status.PARTIALLY_DELIVERED,
        Order.Status.DELIVERED,
        Order.Status.CANCELLED,
    },
    Order.Status.PARTIALLY_DELIVERED: {Order.Status.DELIVERED, Order.Status.CANCELLED},
}


def _transition(order: Order, new_status: str) -> Order:
    allowed = ALLOWED.get(order.status, set())
    if new_status not in allowed:
        raise Conflict(f"Cannot transition order from {order.status} to {new_status}")
    order.status = new_status
    order.save(update_fields=["status", "updated_at"])
    return order


@transaction.atomic
def confirm_order(*, tenant, order_id) -> Order:
    order = OrderRepository(tenant).for_update(order_id)
    if not order:
        raise NotFound("Order not found")
    order = _transition(order, Order.Status.CONFIRMED)
    enqueue(
        tenant=tenant,
        event_type="OrderConfirmed",
        aggregate_type="order",
        aggregate_id=order.id,
        payload={"order_id": str(order.id), "order_number": order.order_number, "status": order.status},
        partition_key=str(order.id),
    )
    return order


@transaction.atomic
def create_order(
    *,
    tenant,
    customer,
    warehouse,
    order_number: str,
    items: list[dict],
    deadline_at=None,
    priority: int = 0,
    notes: str = "",
    status: str = Order.Status.CREATED,
) -> Order:
    total = sum((Decimal(str(i["weight_kg"])) * Decimal(str(i["quantity"])) for i in items), Decimal("0"))
    repo = OrderRepository(tenant)
    order = repo.create(
        customer=customer,
        warehouse=warehouse,
        order_number=sanitize_text(order_number, max_len=64),
        deadline_at=deadline_at,
        priority=priority,
        notes=sanitize_text(notes, max_len=4000),
        status=status,
        total_weight_kg=total,
    )
    OrderItemRepository(tenant).bulk_create(
        [
            OrderItem(
                tenant=tenant,
                order=order,
                sku=sanitize_text(item["sku"], max_len=64),
                description=sanitize_text(item.get("description", ""), max_len=255),
                quantity=item["quantity"],
                weight_kg=item["weight_kg"],
                volume_m3=item.get("volume_m3"),
                temperature_min=item.get("temperature_min"),
                temperature_max=item.get("temperature_max"),
                metadata=item.get("metadata") or {},
            )
            for item in items
        ]
    )
    enqueue(
        tenant=tenant,
        event_type="OrderCreated",
        aggregate_type="order",
        aggregate_id=order.id,
        payload={
            "order_id": str(order.id),
            "order_number": order.order_number,
            "tenant_id": str(tenant.id),
        },
        partition_key=str(order.id),
    )
    return order
