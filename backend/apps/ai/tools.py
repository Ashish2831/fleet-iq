from __future__ import annotations

from collections import Counter
from datetime import timedelta

from django.core.exceptions import ObjectDoesNotExist
from django.utils import timezone

from apps.ai.context import ToolContext
from apps.ai.policies import AGENT_TOOLS, MAX_TOOL_CALLS, WRITE_TOOLS
from apps.common.errors import Forbidden, NotFound
from apps.common.queries import delayed_shipments, delivery_counts
from apps.common.repositories import (
    DispatchProposalRepository,
    DriverRepository,
    ShipmentRepository,
    VehicleRepository,
)
from apps.common.sanitize import sanitize_text
from apps.dispatch.services import propose
from apps.events.outbox import enqueue
from apps.fleet.models import MaintenanceRecord
from apps.search.query import search_drivers, search_knowledge, search_shipments
from apps.shipments.models import Shipment
from apps.telemetry.queries import vehicle_track
from apps.tracking.services import live_for_vehicle


class ToolLoop(RuntimeError):
    pass


def call_tool(ctx: ToolContext, agent: str, name: str, node: str, **kwargs):
    allowed = AGENT_TOOLS.get(agent, set())
    if name not in allowed:
        raise Forbidden(f"Agent {agent} cannot call {name}")
    ctx.calls += 1
    if ctx.calls > MAX_TOOL_CALLS:
        raise ToolLoop("max tool calls exceeded")
    # Sanitize free-text tool args before execution
    for key in ("q", "number", "reason", "area", "city", "status"):
        if key in kwargs and kwargs[key] is not None:
            kwargs[key] = sanitize_text(kwargs[key], max_len=500)
    result = TOOLS[name](ctx, **kwargs)
    ctx.log(node, name, kwargs, result)
    return result


def _shipments(ctx: ToolContext):
    return ShipmentRepository(ctx.tenant).qs()


def get_shipment(ctx: ToolContext, id=None, number=None) -> dict:
    from apps.ai.remote import fetch_shipment

    remote = fetch_shipment(ctx, id=id, number=number)
    if remote is not None:
        return {
            "id": str(remote.get("id") or ""),
            "shipment_number": remote.get("shipment_number") or remote.get("number") or number,
            "status": remote.get("status"),
            "promised_at": remote.get("promised_at") or remote.get("promisedAt"),
            "city": remote.get("city") or (remote.get("delivery_address") or {}).get("city"),
            "address": remote.get("address") or (remote.get("delivery_address") or {}).get("line1"),
            "warehouse_code": remote.get("warehouse_code"),
            "delayed": remote.get("delayed"),
            "vehicle_id": remote.get("vehicle_id"),
            "order_id": remote.get("order_id"),
        }
    repo = ShipmentRepository(ctx.tenant)
    ship = repo.get(id) if id else None
    if ship is None and number:
        ship = repo.by_number(number)
    if ship is None:
        raise NotFound("Shipment not found")
    vehicle_id = None
    delivery = ship.deliveries.select_related("route_stop__route").first()
    if delivery:
        try:
            vehicle_id = str(delivery.route_stop.route.assignment.vehicle_id)
        except (AttributeError, ObjectDoesNotExist):
            vehicle_id = None
    order_id = None
    item = ship.shipment_items.select_related("order_item__order").first()
    if item:
        order_id = str(item.order_item.order_id)
    terminal = {Shipment.Status.DELIVERED, Shipment.Status.FAILED, Shipment.Status.CANCELLED}
    delayed = bool(ship.promised_at and ship.promised_at < timezone.now() and ship.status not in terminal)
    return {
        "id": str(ship.id),
        "shipment_number": ship.shipment_number,
        "status": ship.status,
        "promised_at": ship.promised_at.isoformat() if ship.promised_at else None,
        "city": ship.delivery_address.city,
        "address": ship.delivery_address.line1,
        "warehouse_code": ship.warehouse.code,
        "delayed": delayed,
        "vehicle_id": vehicle_id,
        "order_id": order_id,
    }


def tool_search_shipments(ctx: ToolContext, q="", delayed=None, city=None, status=None) -> dict:
    return search_shipments(
        tenant_id=ctx.tenant.id, q=q, delayed=delayed, city=city, status=status, size=25
    )


def get_delivery_metrics(ctx: ToolContext, city=None) -> dict:
    counts = delivery_counts(ctx.tenant)
    delayed = delayed_shipments(ctx.tenant)
    if city:
        delayed = delayed.filter(delivery_address__city__iexact=city)
    cities = Counter(delayed.values_list("delivery_address__city", flat=True))
    delayed_count = delayed.count() if city else (counts.get("delayed") or delayed.count())
    return {
        "delayed_count": delayed_count,
        "total": counts.get("total") or 0,
        "failed": counts.get("failed") or 0,
        "cities": dict(cities),
    }


def get_vehicle_live(ctx: ToolContext, vehicle_id: str) -> dict:
    if not VehicleRepository(ctx.tenant).exists(id=vehicle_id):
        raise NotFound("Vehicle not found")
    return live_for_vehicle(ctx.tenant, str(vehicle_id)) or {"status": "offline"}


def get_vehicle_track(ctx: ToolContext, vehicle_id: str) -> dict:
    if not VehicleRepository(ctx.tenant).exists(id=vehicle_id):
        raise NotFound("Vehicle not found")
    end = timezone.now()
    start = end - timedelta(hours=1)
    points = vehicle_track(
        tenant_id=ctx.tenant.id, vehicle_id=vehicle_id, start=start, end=end, source="raw"
    )
    safe = []
    for p in points[-20:]:
        row = dict(p)
        if hasattr(row.get("recorded_at"), "isoformat"):
            row["recorded_at"] = row["recorded_at"].isoformat()
        safe.append(row)
    return {"count": len(points), "points": safe}


def get_dispatch_proposal(ctx: ToolContext, order_id: str) -> dict:
    p = (
        DispatchProposalRepository(ctx.tenant)
        .qs()
        .select_related("order")
        .filter(order_id=order_id)
        .order_by("-created_at")
        .first()
    )
    if not p:
        raise NotFound("Proposal not found")
    return {
        "id": str(p.id),
        "order_id": str(p.order_id),
        "status": p.status,
        "score": float(p.score) if p.score is not None else None,
        "chosen": p.chosen,
        "alternatives": p.alternatives,
        "explanation": p.explanation,
        "hard_pass": p.hard_pass,
    }


def get_driver(ctx: ToolContext, id: str) -> dict:
    d = DriverRepository(ctx.tenant).get(id)
    if not d:
        raise NotFound("Driver not found")
    return {
        "id": str(d.id),
        "full_name": d.full_name,
        "status": d.status,
        "skills": list(d.skills or []),
        "rating": float(d.rating) if d.rating is not None else None,
    }


def tool_search_drivers(ctx: ToolContext, q="", skills=None, available=None) -> dict:
    return search_drivers(tenant_id=ctx.tenant.id, q=q, skills=skills, available=available, size=15)


def tool_search_knowledge(ctx: ToolContext, q: str, doc_type=None) -> dict:
    return search_knowledge(tenant_id=ctx.tenant.id, q=q, doc_type=doc_type, size=5)


def get_traffic(ctx: ToolContext, area: str = "") -> dict:
    return {"area": area or "Bengaluru", "factor": 1.35, "source": "stub"}


def propose_reassignment(ctx: ToolContext, shipment_ids=None, reason="") -> dict:
    qs = _shipments(ctx)
    ids = list(shipment_ids or [])
    qs = qs.filter(id__in=ids) if ids else delayed_shipments(ctx.tenant)
    ship = qs.first()
    if not ship:
        raise NotFound("No shipment to reassign")
    item = ship.shipment_items.select_related("order_item__order").first()
    if not item:
        raise NotFound("Shipment has no order")
    proposal = propose(tenant=ctx.tenant, order_id=item.order_item.order_id)
    return {
        "proposal_id": str(proposal.id),
        "order_id": str(proposal.order_id),
        "status": proposal.status,
        "reason": reason,
        "applied": False,
    }


def propose_reoptimization(ctx: ToolContext, route_id: str, reason="") -> dict:
    enqueue(
        tenant=ctx.tenant,
        event_type="RouteReoptimizationRequested",
        aggregate_type="route",
        aggregate_id=route_id,
        payload={"route_id": str(route_id), "reason": reason, "requested_by": str(ctx.user.id)},
        partition_key=str(route_id),
    )
    return {"enqueued": True, "route_id": str(route_id), "applied": False}


def open_maintenance_ticket(ctx: ToolContext, vehicle_id: str, reason="") -> dict:
    vehicle = VehicleRepository(ctx.tenant).get(vehicle_id)
    if not vehicle:
        raise NotFound("Vehicle not found")
    notes = sanitize_text(reason or "Opened by maintenance agent", max_len=500)
    rec = MaintenanceRecord.objects.create(
        tenant=ctx.tenant,
        vehicle=vehicle,
        kind="inspection",
        occurred_at=timezone.now(),
        notes=notes,
    )
    enqueue(
        tenant=ctx.tenant,
        event_type="VehicleMaintenanceDue",
        aggregate_type="vehicle",
        aggregate_id=vehicle.id,
        payload={"vehicle_id": str(vehicle.id), "record_id": str(rec.id), "reason": notes},
        partition_key=str(vehicle.id),
    )
    return {"ticket_id": str(rec.id), "vehicle_id": str(vehicle.id), "applied": False}


TOOLS = {
    "get_shipment": get_shipment,
    "search_shipments": tool_search_shipments,
    "get_delivery_metrics": get_delivery_metrics,
    "get_vehicle_live": get_vehicle_live,
    "get_vehicle_track": get_vehicle_track,
    "get_dispatch_proposal": get_dispatch_proposal,
    "get_driver": get_driver,
    "search_drivers": tool_search_drivers,
    "search_knowledge": tool_search_knowledge,
    "get_traffic": get_traffic,
    "propose_reassignment": propose_reassignment,
    "propose_reoptimization": propose_reoptimization,
    "open_maintenance_ticket": open_maintenance_ticket,
}

assert WRITE_TOOLS <= set(TOOLS)
