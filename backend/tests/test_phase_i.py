from datetime import timedelta

from django.contrib.auth.hashers import make_password
from django.core.management import call_command
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.api.authentication import user_from_access
from apps.api.federation import execute_federated
from apps.api.graphql.loaders import Loaders
from apps.catalog.models import Customer, Warehouse
from apps.dispatch.models import DispatchProposal
from apps.dispatch.services import propose
from apps.events.models import DailyEventCount
from apps.identity.models import Role, Tenant, User, UserRole
from apps.orders.models import Order
from config.schema import GraphQLContext


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
    return Tenant.objects.get(slug="acme-logistics")


def _auth(**kwargs):
    client = APIClient()
    token = _login(client, **kwargs)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client, token


@override_settings(ROOT_URLCONF="config.urls_core")
def test_core_accepts_orders_without_tracking_routes(db):
    tenant = _seed()
    customer = Customer.objects.for_tenant(tenant).first()
    warehouse = Warehouse.objects.for_tenant(tenant).first()
    client, _ = _auth()
    missing = client.post(
        "/api/v1/tracking/locations",
        {
            "vehicle_id": "00000000-0000-0000-0000-000000000001",
            "recorded_at": "2026-01-01T00:00:00Z",
            "lat": 12.9,
            "lng": 77.6,
            "event_id": "x",
        },
        format="json",
    )
    assert missing.status_code == 404
    res = client.post(
        "/api/v1/orders/",
        {
            "customer_id": str(customer.id),
            "warehouse_id": str(warehouse.id),
            "order_number": "I-CORE-1",
            "items": [{"sku": "Z", "quantity": "1", "weight_kg": "2"}],
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY="i-core-1",
    )
    assert res.status_code == 201, res.content
    assert res.data["order_number"] == "I-CORE-1"


@override_settings(ROOT_URLCONF="config.urls_tracking")
def test_tracking_service_jwt_and_live_snapshot(db, fake_redis):
    _seed()
    client, _ = _auth()
    health = client.get("/health")
    assert health.json()["role"] == "tracking"
    snap = client.get("/api/v1/tracking/vehicles")
    assert snap.status_code == 200
    assert "vehicles" in snap.data or "counts" in snap.data
    assert client.get("/api/v1/orders/").status_code == 404
    jwks = client.get("/api/v1/auth/jwks")
    assert jwks.status_code == 200
    assert jwks.data["keys"][0]["kid"]


@override_settings(ROOT_URLCONF="config.urls_analytics")
def test_analytics_kpis_are_tenant_scoped(db):
    tenant = _seed()
    yesterday = timezone.localdate() - timedelta(days=1)
    DailyEventCount.objects.create(tenant=tenant, day=yesterday, event_type="OrderCreated", count=4)
    client, _ = _auth()
    res = client.get("/api/v1/analytics/kpis")
    assert res.status_code == 200, res.content
    assert res.data["orders_yesterday"] == 4
    beta = Tenant.objects.get(slug="beta-freight")
    user = User.objects.create(
        tenant=beta,
        email="ops@beta.example",
        full_name="Beta Ops",
        hashed_password=make_password("password"),
    )
    role = Role.objects.create(tenant=beta, name="ops_manager")
    UserRole.objects.create(user=user, role=role)
    other, _ = _auth(email="ops@beta.example", tenant="beta-freight")
    empty = other.get("/api/v1/analytics/kpis")
    assert empty.status_code == 200
    assert empty.data["orders_yesterday"] == 0


@override_settings(ROOT_URLCONF="config.urls_ai")
def test_ai_service_owns_runs(db, memory_search):
    _seed()
    client, _ = _auth()
    res = client.post(
        "/api/v1/ai/runs",
        {"agent": "operations", "input": "Why are deliveries delayed today?"},
        format="json",
    )
    assert res.status_code == 201, res.content
    assert client.get("/api/v1/orders/").status_code == 404


def test_gateway_composes_dashboard(db, fake_redis):
    _seed()
    _, token = _auth()
    user = user_from_access(token)
    ctx = GraphQLContext(request=None, user=user, tenant=user.tenant, loaders=Loaders(user.tenant))
    result = execute_federated(
        """
        query {
          dashboard {
            delayedDeliveries
            activeVehicles
            slaYesterday
            ordersYesterday
            liveCounts { active delayed }
          }
        }
        """,
        {},
        ctx,
    )
    assert result.get("data"), result
    dash = result["data"]["dashboard"]
    assert "delayedDeliveries" in dash
    assert "liveCounts" in dash


def test_jwks_published_on_monolith(db):
    client = APIClient()
    res = client.get("/api/v1/auth/jwks")
    assert res.status_code == 200
    assert res.data["keys"][0]["kty"] == "oct"


def test_health_reports_phase_i(db):
    client = APIClient()
    res = client.get("/health")
    assert res.json()["phase"] == "I"


def test_mfe_remotes_exist():
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    assert (root / "apps/web-fleet/app/live-map/page.tsx").exists()
    assert (root / "apps/web-orders/app/orders/page.tsx").exists()
    assert (root / "packages/auth/index.ts").exists()
    cfg = (root / "apps/web/next.config.ts").read_text()
    assert "FLEET_MFE_ORIGIN" in cfg
    assert "ORDERS_MFE_ORIGIN" in cfg


def test_dispatch_proposal_still_core(db, memory_search):
    tenant = _seed()
    order = Order.objects.for_tenant(tenant).first()
    proposal = propose(tenant=tenant, order_id=order.id)
    assert proposal.status == DispatchProposal.Status.PENDING
    client, _ = _auth()
    res = client.get("/api/v1/dispatch/proposals/")
    assert res.status_code == 200
    rows = res.data.get("results") if isinstance(res.data, dict) else res.data
    assert any(str(proposal.id) == str(row["id"]) for row in rows)
