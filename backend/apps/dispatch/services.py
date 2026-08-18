from __future__ import annotations

import uuid
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.common.errors import Conflict, NotFound
from apps.dispatch.models import DispatchProposal
from apps.dispatch.solver import solve_insertion
from apps.events.outbox import enqueue
from apps.fleet.models import Driver, Vehicle
from apps.orders.models import Order
from apps.routing.models import Route
from apps.routing.services import assign_route, create_route_with_stops
from apps.shipments.models import Shipment
from apps.tracking import redis_state as rs


def propose(*, tenant, order_id) -> DispatchProposal:
    order = Order.objects.for_tenant(tenant).filter(id=order_id).first()
    if not order:
        raise NotFound("Order not found")
    return build_proposal(tenant=tenant, order=order)


def existing_pending(tenant, order_id) -> DispatchProposal | None:
    return (
        DispatchProposal.objects.for_tenant(tenant)
        .filter(order_id=order_id, status=DispatchProposal.Status.PENDING)
        .first()
    )


def build_proposal(*, tenant, order: Order) -> DispatchProposal:
    pending = existing_pending(tenant, order.id)
    if pending:
        return pending
    result = solve_insertion(order)
    chosen = result["chosen"] or {}
    status = (
        DispatchProposal.Status.FAILED
        if not result["hard_pass"]
        else DispatchProposal.Status.PENDING
    )
    try:
        return DispatchProposal.objects.create(
            tenant=tenant,
            order=order,
            status=status,
            chosen=chosen,
            alternatives=result["alternatives"],
            hard_pass=result["hard_pass"],
            score=Decimal(str(result["score"])) if result["score"] is not None else None,
            explanation={"rejects": result["rejects"], "features": chosen.get("features") or {}},
            policy={
                "weights": (chosen.get("weights") or {}),
                "auto_gap": 15,
                "auto_max_priority": 1,
            },
            graph_run_id=str(uuid.uuid4())[:16],
        )
    except IntegrityError:
        found = existing_pending(tenant, order.id)
        if found:
            return found
        raise


def should_auto(proposal: DispatchProposal, order: Order) -> bool:
    if not proposal.hard_pass or not proposal.chosen:
        return False
    policy = proposal.policy or {}
    if order.priority > int(policy.get("auto_max_priority", 1)):
        return False
    alts = proposal.alternatives or []
    if not alts:
        return True
    gap = float(proposal.score or 0)  # cost of winner
    second = float(alts[0].get("cost") or gap)
    return (second - gap) >= float(policy.get("auto_gap", 15))


def apply_proposal(proposal: DispatchProposal, *, actor=None) -> DispatchProposal:
    if proposal.status == DispatchProposal.Status.APPLIED:
        raise Conflict("Proposal already applied")
    if proposal.status not in (
        DispatchProposal.Status.PENDING,
        DispatchProposal.Status.APPROVED,
    ):
        raise Conflict(f"Cannot apply proposal in status {proposal.status}")
    order = Order.objects.get(pk=proposal.order_id)
    chosen = proposal.chosen or {}
    if not chosen.get("driver_id") or not chosen.get("vehicle_id"):
        proposal.status = DispatchProposal.Status.FAILED
        proposal.save(update_fields=["status", "updated_at"])
        raise Conflict("No feasible assignment")
    driver = Driver.objects.for_tenant(proposal.tenant).get(pk=chosen["driver_id"])
    vehicle = Vehicle.objects.for_tenant(proposal.tenant).get(pk=chosen["vehicle_id"])
    dest = None
    ship = (
        Shipment.objects.for_tenant(proposal.tenant)
        .filter(shipment_items__order_item__order=order)
        .select_related("delivery_address", "warehouse")
        .first()
    )
    if ship:
        dest = ship.delivery_address
    from apps.dispatch.constraints import hard_check

    reasons = hard_check(order=order, driver=driver, vehicle=vehicle, dest=dest)
    if reasons:
        proposal.status = DispatchProposal.Status.FAILED
        proposal.explanation = {**(proposal.explanation or {}), "apply_rejects": reasons}
        proposal.save(update_fields=["status", "explanation", "updated_at"])
        raise Conflict("Hard constraints failed on apply: " + ",".join(reasons))
    with transaction.atomic():
        return _apply_locked(proposal, order, driver, vehicle, chosen, actor)


def _apply_locked(proposal, order, driver, vehicle, chosen, actor):
    route_id = chosen.get("route_id")
    if route_id:
        assign_route(
            tenant=proposal.tenant,
            route_id=route_id,
            driver_id=driver.id,
            vehicle_id=vehicle.id,
        )
        route = Route.objects.get(pk=route_id)
    else:
        warehouse = order.warehouse
        stops = [
            {
                "stop_type": "depot",
                "sequence": 1,
                "address": warehouse.address,
                "warehouse": warehouse,
            }
        ]
        seq = 2
        ships = (
            Shipment.objects.for_tenant(proposal.tenant)
            .filter(shipment_items__order_item__order=order)
            .select_related("delivery_address", "warehouse")
            .distinct()
        )
        for ship in ships:
            stops.append(
                {
                    "stop_type": "pickup",
                    "sequence": seq,
                    "address": warehouse.address,
                    "shipment": ship,
                    "warehouse": warehouse,
                }
            )
            seq += 1
            stops.append(
                {
                    "stop_type": "dropoff",
                    "sequence": seq,
                    "address": ship.delivery_address,
                    "shipment": ship,
                }
            )
            seq += 1
        route = create_route_with_stops(
            tenant=proposal.tenant,
            route_number=f"DSP-{order.order_number}",
            planned_date=timezone.localdate(),
            driver=driver,
            vehicle=vehicle,
            stops=stops or [
                {
                    "stop_type": "depot",
                    "sequence": 1,
                    "address": warehouse.address,
                    "warehouse": warehouse,
                }
            ],
        )
    order.status = Order.Status.PLANNED
    order.save(update_fields=["status", "updated_at"])
    enqueue(
        tenant=proposal.tenant,
        event_type="OrderAssigned",
        aggregate_type="order",
        aggregate_id=order.id,
        payload={
            "order_id": str(order.id),
            "driver_id": str(driver.id),
            "vehicle_id": str(vehicle.id),
            "route_id": str(route.id),
            "proposal_id": str(proposal.id),
        },
        partition_key=str(order.id),
    )
    proposal.status = DispatchProposal.Status.APPLIED
    proposal.decided_at = timezone.now()
    proposal.decided_by = actor
    proposal.save(update_fields=["status", "decided_at", "decided_by", "updated_at"])
    return proposal


@transaction.atomic
def approve(*, tenant, proposal_id, actor=None) -> DispatchProposal:
    proposal = (
        DispatchProposal.objects.select_for_update()
        .for_tenant(tenant)
        .filter(id=proposal_id)
        .first()
    )
    if not proposal:
        raise NotFound("Proposal not found")
    if proposal.status == DispatchProposal.Status.APPLIED:
        raise Conflict("Proposal already applied")
    proposal.status = DispatchProposal.Status.APPROVED
    proposal.decided_by = actor
    proposal.decided_at = timezone.now()
    proposal.save(update_fields=["status", "decided_by", "decided_at", "updated_at"])
    return apply_proposal(proposal, actor=actor)


def reject(*, tenant, proposal_id, actor=None) -> DispatchProposal:
    proposal = (
        DispatchProposal.objects.select_for_update()
        .for_tenant(tenant)
        .filter(id=proposal_id)
        .first()
    )
    if not proposal:
        raise NotFound("Proposal not found")
    if proposal.status not in (DispatchProposal.Status.PENDING, DispatchProposal.Status.APPROVED):
        raise Conflict(f"Cannot reject {proposal.status}")
    proposal.status = DispatchProposal.Status.REJECTED
    proposal.decided_by = actor
    proposal.decided_at = timezone.now()
    proposal.save(update_fields=["status", "decided_by", "decided_at", "updated_at"])
    return proposal
