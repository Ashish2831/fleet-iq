from datetime import timedelta

from django.contrib.auth.hashers import make_password
from django.core.management import call_command
from django.utils import timezone
from rest_framework.test import APIClient

from apps.ai.context import ToolContext
from apps.ai.models import AiRun
from apps.ai.tools import get_delivery_metrics
from apps.common.models import OutboxEvent
from apps.dispatch.models import DispatchProposal
from apps.dispatch.services import propose
from apps.fleet.models import Vehicle
from apps.identity.models import Role, Tenant, User, UserRole
from apps.search.indexer import reindex_tenant
from apps.shipments.models import Shipment
from apps.telemetry.store import get_store
from apps.tracking.redis_state import write_live


def _login(client, email="ops@acme-logistics.example", tenant="acme-logistics", password="password"):
    res = client.post(
        "/api/v1/auth/login",
        {"email": email, "password": password, "tenant": tenant},
        format="json",
    )
    assert res.status_code == 200, res.content
    return res.data["access"]


def _seed():
    call_command("seed_bangalore", reset=True)
    tenant = Tenant.objects.get(slug="acme-logistics")
    reindex_tenant(tenant)
    return tenant


def _auth(client, **kwargs):
    token = _login(client, **kwargs)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


def _vehicle_for_shipment(ship: Shipment):
    delivery = ship.deliveries.select_related("route_stop__route__assignment").first()
    if not delivery:
        return None
    try:
        return delivery.route_stop.route.assignment.vehicle
    except Exception:
        return None


def test_operations_delayed_today_matches_metrics(db, memory_search):
    tenant = _seed()
    user = User.objects.for_tenant(tenant).get(email="ops@acme-logistics.example")
    expected = get_delivery_metrics(ToolContext(tenant=tenant, user=user))
    client = _auth(APIClient())
    res = client.post(
        "/api/v1/ai/runs",
        {"agent": "operations", "input": "Why are deliveries delayed today?"},
        format="json",
    )
    assert res.status_code == 201, res.content
    assert res.data["output"]["delayed_count"] == expected["delayed_count"]
    assert res.data["trace"]
    assert AiRun.objects.for_tenant(tenant).count() == 1


def test_shipment_answer_uses_live_track_and_sop(db, memory_search, memory_telemetry, fake_redis):
    tenant = _seed()
    ship = Shipment.objects.for_tenant(tenant).filter(shipment_number="SHP-2001").first()
    assert ship is not None
    vehicle = _vehicle_for_shipment(ship) or Vehicle.objects.for_tenant(tenant).first()
    write_live(
        tenant,
        str(vehicle.id),
        {
            "lat": 12.97,
            "lng": 77.75,
            "speed": 8,
            "heading": 90,
            "status": "delayed",
            "recorded_at": timezone.now().isoformat(),
        },
    )
    store = get_store()
    store.claim_event("h-gps-1")
    store.insert_raw(
        [
            {
                "event_id": "h-gps-1",
                "recorded_at": timezone.now() - timedelta(minutes=2),
                "meta": {"tenant_id": str(tenant.id), "vehicle_id": str(vehicle.id)},
                "loc": {"type": "Point", "coordinates": [77.75, 12.97]},
                "speed_kmh": 8,
            }
        ]
    )
    client = _auth(APIClient())
    res = client.post(
        "/api/v1/ai/runs",
        {"agent": "operations", "input": "Why is shipment SHP-2001 delayed?"},
        format="json",
    )
    assert res.status_code == 201, res.content
    tools = [t.get("tool") for t in res.data["trace"]]
    assert "get_shipment" in tools
    assert "get_vehicle_live" in tools or "get_vehicle_track" in tools
    blob = str(res.data["output"]).lower()
    assert "late" in blob or "sop" in blob or "policy" in blob or res.data["output"].get("sources")


def test_dispatch_explain_does_not_call_solver(db, memory_search, monkeypatch):
    tenant = _seed()
    from apps.orders.models import Order

    order = Order.objects.for_tenant(tenant).first()
    proposal = propose(tenant=tenant, order_id=order.id)
    called = {"n": 0}

    def boom(*a, **k):
        called["n"] += 1
        raise AssertionError("solver must not run")

    monkeypatch.setattr("apps.dispatch.solver.solve_insertion", boom)
    client = _auth(APIClient())
    res = client.post(
        "/api/v1/ai/runs",
        {
            "agent": "dispatch_explain",
            "input": f"Why was this driver chosen for order {order.order_number}?",
        },
        format="json",
    )
    assert res.status_code == 201, res.content
    assert called["n"] == 0
    assert str(proposal.id) in str(res.data["output"].get("proposal_id") or res.data["output"])


def test_propose_reassignment_is_hitl(db, memory_search):
    tenant = _seed()
    before = DispatchProposal.objects.for_tenant(tenant).filter(status=DispatchProposal.Status.APPLIED).count()
    client = _auth(APIClient())
    res = client.post(
        "/api/v1/ai/runs",
        {"agent": "operations", "input": "Why are deliveries delayed today? Propose a reassignment."},
        format="json",
    )
    assert res.status_code == 201, res.content
    pid = res.data["proposal_id"] or res.data["output"].get("proposal_id")
    assert pid
    proposal = DispatchProposal.objects.for_tenant(tenant).get(id=pid)
    assert proposal.status == DispatchProposal.Status.PENDING
    after = DispatchProposal.objects.for_tenant(tenant).filter(status=DispatchProposal.Status.APPLIED).count()
    assert after == before
    assert res.data["status"] == AiRun.Status.WAITING_APPROVAL


def test_maintenance_emits_outbox(db, memory_search):
    tenant = _seed()
    client = _auth(APIClient())
    res = client.post(
        "/api/v1/ai/runs",
        {"agent": "maintenance", "input": "Engine warning on a vehicle, open a ticket."},
        format="json",
    )
    assert res.status_code == 201, res.content
    assert OutboxEvent.objects.for_tenant(tenant).filter(event_type="VehicleMaintenanceDue").exists()


def test_route_risk_enqueues_reoptimization(db, memory_search):
    tenant = _seed()
    client = _auth(APIClient())
    res = client.post(
        "/api/v1/ai/runs",
        {"agent": "route_risk", "input": "Which routes look risky? Reoptimize if needed."},
        format="json",
    )
    assert res.status_code == 201, res.content
    assert OutboxEvent.objects.for_tenant(tenant).filter(event_type="RouteReoptimizationRequested").exists()


def test_tenant_b_cannot_see_tenant_a_shipment(db, memory_search):
    tenant = _seed()
    beta = Tenant.objects.get(slug="beta-freight")
    user = User.objects.create(
        tenant=beta,
        email="ops@beta.example",
        full_name="Beta Ops",
        hashed_password=make_password("password"),
    )
    role = Role.objects.create(tenant=beta, name="ops_manager")
    UserRole.objects.create(user=user, role=role)
    client = _auth(APIClient(), email="ops@beta.example", tenant="beta-freight")
    res = client.post(
        "/api/v1/ai/runs",
        {"agent": "operations", "input": "Why is shipment SHP-2001 delayed?"},
        format="json",
    )
    assert res.status_code == 201, res.content
    summary = (res.data["output"] or {}).get("summary") or ""
    assert "not found" in summary.lower() or "no shipment" in summary.lower()
    tools = [t.get("tool") for t in res.data["trace"]]
    assert "get_vehicle_live" not in tools


def test_graphql_start_ai_run(db, memory_search):
    _seed()
    client = APIClient()
    token = _login(client)
    query = """
      mutation {
        startAiRun(agent: "operations", input: "Why are deliveries delayed today?") {
          id status agent output
        }
      }
    """
    res = client.post("/graphql", {"query": query}, format="json", HTTP_AUTHORIZATION=f"Bearer {token}")
    body = res.json()
    assert "errors" not in body, body
    assert body["data"]["startAiRun"]["output"]["delayed_count"] is not None
