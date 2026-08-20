from datetime import timedelta
from decimal import Decimal

from django.utils import timezone
from rest_framework.test import APIClient

from apps.dispatch.models import DispatchProposal
from apps.dispatch.services import apply_proposal, approve, propose
from apps.dispatch.solver import solve_wave
from apps.events.consumers import consume_once
from apps.events.outbox import publish_batch
from apps.fleet.models import Vehicle
from apps.orders.services import confirm_order, create_order
from apps.shipments.services import create_shipment
from helpers import (
    acme_tenant,
    drivers,
    first_customer,
    first_warehouse,
    login,
    proposals,
    seed_bangalore,
    vehicle_types,
    vehicles,
)


def _seed():
    seed_bangalore()
    return acme_tenant()


def _new_order(tenant, *, weight=40, temp=False, number="G-1"):
    customer = first_customer(tenant)
    warehouse = first_warehouse(tenant)
    item = {"sku": "X", "quantity": 1, "weight_kg": weight}
    if temp:
        item["temperature_min"] = 2
        item["temperature_max"] = 8
    order = create_order(
        tenant=tenant,
        customer=customer,
        warehouse=warehouse,
        order_number=number,
        items=[item],
        deadline_at=timezone.now() + timedelta(hours=8),
    )
    oi = order.items.get()
    addr = customer.addresses.first() or warehouse.address
    create_shipment(
        tenant=tenant,
        warehouse=warehouse,
        delivery_address=addr,
        shipment_number=f"SHP-{number}",
        order_item_quantities=[(oi, oi.quantity)],
        promised_at=timezone.now() + timedelta(hours=6),
    )
    return confirm_order(tenant=tenant, order_id=order.id)


def test_propose_has_top_alternatives(db, memory_search):
    tenant = _seed()
    order = _new_order(tenant, number="G-TOP")
    proposal = propose(tenant=tenant, order_id=order.id)
    assert proposal.hard_pass is True
    assert proposal.chosen.get("driver_id")
    assert len(proposal.alternatives) <= 2
    assert "distance_km" in (proposal.chosen.get("features") or {})


def test_hard_reject_over_weight(db, memory_search):
    tenant = _seed()
    bike = vehicle_types(tenant).create(name="bike-g", max_weight_kg=Decimal("30"))
    vehicles(tenant).tenant_qs().update(vehicle_type=bike)
    order = _new_order(tenant, weight=500, number="G-HEAVY")
    proposal = propose(tenant=tenant, order_id=order.id)
    assert proposal.hard_pass is False
    assert any("over_weight" in str(r) for r in (proposal.explanation or {}).get("rejects") or [])


def test_hard_reject_missing_reefer(db, memory_search):
    tenant = _seed()
    drivers(tenant).tenant_qs().update(skills=[])
    order = _new_order(tenant, temp=True, number="G-COLD")
    proposal = propose(tenant=tenant, order_id=order.id)
    rejects = str((proposal.explanation or {}).get("rejects") or [])
    assert "missing_skills" in rejects or proposal.hard_pass is False


def test_approve_applies_route_and_second_approve_409(db, memory_search):
    tenant = _seed()
    order = _new_order(tenant, number="G-APPR")
    proposal = propose(tenant=tenant, order_id=order.id)
    assert proposal.status == DispatchProposal.Status.PENDING
    applied = approve(tenant=tenant, proposal_id=proposal.id)
    assert applied.status == DispatchProposal.Status.APPLIED
    assert applied.chosen.get("driver_id")
    order.refresh_from_db()
    assert order.status == order.Status.PLANNED
    try:
        approve(tenant=tenant, proposal_id=proposal.id)
        assert False, "expected conflict"
    except Exception as exc:
        assert "already" in str(exc).lower() or "applied" in str(exc).lower()


def test_kafka_replay_does_not_double_propose(db, memory_bus, memory_search):
    tenant = _seed()
    order = _new_order(tenant, number="G-KAFKA")
    publish_batch(bus=memory_bus, limit=200)
    consume_once("fleetiq-dispatch", bus=memory_bus, max_records=200)
    consume_once("fleetiq-dispatch", bus=memory_bus, max_records=200)
    n = proposals(tenant).tenant_qs().filter(order=order).count()
    assert n == 1


def test_apply_fails_if_vehicle_goes_maintenance(db, memory_search):
    tenant = _seed()
    order = _new_order(tenant, number="G-MAINT")
    proposal = propose(tenant=tenant, order_id=order.id)
    vid = proposal.chosen["vehicle_id"]
    vehicles(tenant).tenant_qs().filter(id=vid).update(status=Vehicle.Status.MAINTENANCE)
    try:
        apply_proposal(proposal)
        assert False, "expected conflict"
    except Exception:
        proposal.refresh_from_db()
        assert proposal.status == DispatchProposal.Status.FAILED


def test_wave_solver_respects_capacity():
    matrix = [
        [0, 1, 2, 3],
        [1, 0, 1, 2],
        [2, 1, 0, 1],
        [3, 2, 1, 0],
    ]
    result = solve_wave(matrix, demands=[0, 10, 10, 10], capacities=[25, 25])
    assert result["unassigned"] == []
    assert all(load <= 25 for load in result["loads"])


def test_rest_dispatch_queue(db, memory_search):
    tenant = _seed()
    order = _new_order(tenant, number="G-REST")
    propose(tenant=tenant, order_id=order.id)
    client = APIClient()
    token = login(client)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    res = client.get("/api/v1/dispatch/proposals/", {"status": "pending"})
    assert res.status_code == 200
    assert res.data["count"] >= 1 or len(res.data.get("results") or res.data) >= 1
