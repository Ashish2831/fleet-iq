from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

from apps.common.repositories import DailyEventCountRepository


def tenant_kpis(tenant, day=None) -> dict:
    """Yesterday's event projections. delayedDeliveries stays Core SQL."""
    day = day or (timezone.localdate() - timedelta(days=1))
    rows = DailyEventCountRepository(tenant).for_day(day)
    by_type = {r.event_type: r.count for r in rows}
    completed = by_type.get("DeliveryCompleted", 0)
    failed = by_type.get("DeliveryFailed", 0)
    started = by_type.get("DeliveryStarted", 0)
    denom = completed + failed
    sla = (completed / denom) if denom else None
    if sla is None and started:
        sla = completed / started if started else None
    return {
        "day": day.isoformat(),
        "orders_yesterday": by_type.get("OrderCreated", 0) + by_type.get("OrderConfirmed", 0),
        "deliveries_completed": completed,
        "deliveries_failed": failed,
        "sla_yesterday": round(sla, 4) if sla is not None else None,
        "by_type": by_type,
    }
