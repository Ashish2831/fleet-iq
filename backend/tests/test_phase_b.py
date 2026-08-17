from rest_framework.test import APIClient

from apps.identity.models import Role, Tenant, User, UserRole
from apps.orders.models import Order
from apps.catalog.models import Address, Customer, Warehouse
from apps.orders.services import create_order


def _login(client, email="ops@acme-logistics.example", tenant="acme-logistics", password="password"):
    res = client.post(
        "/api/v1/auth/login",
        {"email": email, "password": password, "tenant": tenant},
        format="json",
    )
    assert res.status_code == 200, res.content
    return res.data["access"]


def test_login_and_me(db):
    from django.core.management import call_command

    call_command("seed_bangalore", reset=True)
    client = APIClient()
    token = _login(client)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    me = client.get("/api/v1/me")
    assert me.status_code == 200
    assert me.data["tenant_slug"] == "acme-logistics"


def test_rest_does_not_leak_across_tenants(db):
    from django.core.management import call_command
    from django.contrib.auth.hashers import make_password

    call_command("seed_bangalore", reset=True)
    beta = Tenant.objects.get(slug="beta-freight")
    user = User.objects.create(
        tenant=beta,
        email="ops@beta.example",
        full_name="Beta Ops",
        hashed_password=make_password("password"),
    )
    role = Role.objects.create(tenant=beta, name="ops_manager")
    UserRole.objects.create(user=user, role=role)
    acme_order = Order.objects.for_tenant(Tenant.objects.get(slug="acme-logistics")).first()
    client = APIClient()
    token = _login(client, email="ops@beta.example", tenant="beta-freight")
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    res = client.get(f"/api/v1/orders/{acme_order.id}/")
    assert res.status_code == 404


def test_create_order_idempotent(db):
    from django.core.management import call_command

    call_command("seed_bangalore", reset=True)
    tenant = Tenant.objects.get(slug="acme-logistics")
    customer = Customer.objects.for_tenant(tenant).first()
    warehouse = Warehouse.objects.for_tenant(tenant).first()
    client = APIClient()
    token = _login(client)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    payload = {
        "customer_id": str(customer.id),
        "warehouse_id": str(warehouse.id),
        "order_number": "IDEM-1",
        "items": [{"sku": "Z", "quantity": "1", "weight_kg": "2"}],
    }
    headers = {"HTTP_IDEMPOTENCY_KEY": "k-1"}
    a = client.post("/api/v1/orders/", payload, format="json", **headers)
    b = client.post("/api/v1/orders/", payload, format="json", **headers)
    assert a.status_code == 201
    assert b.status_code == 201
    assert a.data["id"] == b.data["id"]
    payload2 = {**payload, "order_number": "IDEM-2"}
    c = client.post("/api/v1/orders/", payload2, format="json", **headers)
    assert c.status_code == 409


def test_confirm_illegal_transition_is_409(db):
    from django.core.management import call_command

    call_command("seed_bangalore", reset=True)
    tenant = Tenant.objects.get(slug="acme-logistics")
    order = Order.objects.for_tenant(tenant).filter(status="confirmed").first()
    client = APIClient()
    token = _login(client)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    res = client.post(f"/api/v1/orders/{order.id}/confirm/")
    assert res.status_code == 409
    assert res.data["code"] == "CONFLICT"


def test_graphql_dashboard_and_tenant_isolation(db):
    from django.core.management import call_command
    from django.contrib.auth.hashers import make_password

    call_command("seed_bangalore", reset=True)
    acme = Tenant.objects.get(slug="acme-logistics")
    order = Order.objects.for_tenant(acme).first()
    beta = Tenant.objects.get(slug="beta-freight")
    user = User.objects.create(
        tenant=beta,
        email="ops@beta.example",
        full_name="Beta Ops",
        hashed_password=make_password("password"),
    )
    role = Role.objects.create(tenant=beta, name="ops_manager")
    UserRole.objects.create(user=user, role=role)
    client = APIClient()
    acme_token = _login(client)
    query = """
      query($id: ID!) {
        dashboard { activeVehicles delayedDeliveries activeDrivers routes { id status eta } }
        order(id: $id) { id orderNumber }
      }
    """
    res = client.post(
        "/graphql",
        {"query": query, "variables": {"id": str(order.id)}},
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {acme_token}",
    )
    assert res.status_code == 200, res.content
    body = res.json()
    assert "errors" not in body, body
    assert "activeVehicles" in body["data"]["dashboard"]
    assert body["data"]["order"]["id"] == str(order.id)

    beta_token = _login(client, email="ops@beta.example", tenant="beta-freight")
    leak = client.post(
        "/graphql",
        {"query": "query($id: ID!) { order(id: $id) { id } }", "variables": {"id": str(order.id)}},
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {beta_token}",
    )
    assert leak.json()["data"]["order"] is None


def test_graphql_dataloader_query_count(db):
    from django.core.management import call_command
    from django.test.utils import CaptureQueriesContext
    from django.db import connection

    call_command("seed_bangalore", reset=True)
    client = APIClient()
    token = _login(client)
    query = """
      query {
        orders(first: 10) {
          orderNumber
          customer { name }
          items { sku }
        }
      }
    """
    # Warm auth / contenttypes
    client.post("/graphql", {"query": "{ me { email } }"}, format="json", HTTP_AUTHORIZATION=f"Bearer {token}")
    with CaptureQueriesContext(connection) as ctx:
        res = client.post("/graphql", {"query": query}, format="json", HTTP_AUTHORIZATION=f"Bearer {token}")
    assert res.status_code == 200
    assert "errors" not in res.json(), res.json()
    orders = res.json()["data"]["orders"]
    assert len(orders) == 10
    # 1 user + 1 orders + 1 customers + 1 items  (not 1+10+10)
    assert len(ctx.captured_queries) < 12, [q["sql"][:80] for q in ctx.captured_queries]
