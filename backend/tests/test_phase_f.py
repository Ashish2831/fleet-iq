from django.contrib.auth.hashers import make_password
from django.core.management import call_command
from rest_framework.test import APIClient

from apps.events.consumers import consume_once
from apps.events.outbox import publish_batch
from apps.fleet.models import Driver
from apps.identity.models import Role, Tenant, User, UserRole
from apps.orders.models import Order
from apps.orders.services import create_order
from apps.catalog.models import Customer, Warehouse
from apps.search.indexer import reindex_tenant
from apps.search.store import get_search
from apps.shipments.models import Delivery, Shipment
from apps.shipments.services import complete_delivery


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


def test_search_delayed_whitefield(db, memory_search):
    tenant = _seed()
    client = APIClient()
    token = _login(client)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    res = client.get("/api/v1/search/shipments", {"q": "Whitefield", "delayed": "true", "city": "Bengaluru"})
    assert res.status_code == 200, res.content
    assert res.data["total"] >= 1
    blob = str(res.data["hits"]).lower()
    assert "whitefield" in blob
    assert res.data["facets"]["by_warehouse"]


def test_search_drivers_reefer_geo(db, memory_search):
    tenant = _seed()
    driver = Driver.objects.for_tenant(tenant).filter(skills__contains=["reefer"]).first()
    assert driver is not None
    client = APIClient()
    token = _login(client)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    res = client.get(
        "/api/v1/search/drivers",
        {
            "skills": "reefer",
            "available": "true",
            "lat": driver.home_lat,
            "lng": driver.home_lng,
            "radius_km": 5,
        },
    )
    assert res.status_code == 200, res.content
    ids = [h["driver_id"] for h in res.data["hits"]]
    assert str(driver.id) in ids


def test_knowledge_hybrid_and_tenant_isolation(db, memory_search):
    tenant = _seed()
    store = get_search()
    store.upsert_knowledge(
        {
            "tenant_id": str(tenant.id),
            "chunk_id": "acme-only-1",
            "doc_id": "contract-acme",
            "source": "contract-acme.md",
            "title": "Acme pricing contract",
            "heading": "Confidential rates",
            "page": 1,
            "text": "Acme exclusive lane rate for Whitefield BioLabs is confidential.",
            "embedding": __import__("apps.search.text", fromlist=["embed"]).embed(
                "Acme exclusive lane rate for Whitefield BioLabs is confidential."
            ),
            "doc_type": "contract",
        }
    )
    client = APIClient()
    token = _login(client)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    res = client.post(
        "/api/v1/search/knowledge",
        {"q": "temperature-sensitive cargo exceeds the limit"},
        format="json",
    )
    assert res.status_code == 200, res.content
    assert res.data["hits"]
    assert any("source" in h and h["text"] for h in res.data["hits"])
    assert any("temperature" in (h.get("source") or "") or "temperature" in (h.get("text") or "").lower() for h in res.data["hits"])

    contract = client.post("/api/v1/search/knowledge", {"q": "exclusive lane rate BioLabs"}, format="json")
    assert any(h["id"] == "acme-only-1" or h.get("source") == "contract-acme.md" for h in contract.data["hits"])

    beta = Tenant.objects.get(slug="beta-freight")
    user = User.objects.create(
        tenant=beta, email="ops@beta.example", full_name="Beta Ops", hashed_password=make_password("password")
    )
    role = Role.objects.create(tenant=beta, name="ops_manager")
    UserRole.objects.create(user=user, role=role)
    beta_token = _login(client, email="ops@beta.example", tenant="beta-freight")
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {beta_token}")
    leak = client.post("/api/v1/search/knowledge", {"q": "exclusive lane rate BioLabs"}, format="json")
    assert leak.status_code == 200
    assert not any("acme-only" in str(h) or "contract-acme" in str(h.get("source")) for h in leak.data["hits"])
    ships = client.get("/api/v1/search/shipments", {"q": "Whitefield"})
    assert ships.data["total"] == 0


def test_order_create_unaffected_when_search_down(db, memory_search, monkeypatch):
    tenant = _seed()
    customer = Customer.objects.for_tenant(tenant).first()
    warehouse = Warehouse.objects.for_tenant(tenant).first()

    def boom(*a, **k):
        raise RuntimeError("elasticsearch down")

    monkeypatch.setattr("apps.search.indexer.index_shipment", boom)
    order = create_order(
        tenant=tenant,
        customer=customer,
        warehouse=warehouse,
        order_number="F-NO-ES",
        items=[{"sku": "X", "quantity": 1, "weight_kg": 1}],
    )
    assert order.id
    client = APIClient()
    token = _login(client)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    # list still SQL
    res = client.get("/api/v1/orders/")
    assert res.status_code == 200


def test_kafka_search_consumer_upserts(db, memory_bus, memory_search):
    tenant = _seed()
    delivery = Delivery.objects.for_tenant(tenant).filter(status=Delivery.Status.IN_TRANSIT).first()
    complete_delivery(tenant=tenant, delivery_id=delivery.id)
    publish_batch(bus=memory_bus, limit=100)
    consume_once("fleetiq-search", bus=memory_bus, max_records=100)
    store = get_search()
    doc = store.shipments.get(f"{tenant.id}:{delivery.shipment_id}")
    assert doc is not None
    assert doc["status"] == "delivered"


def test_graphql_search_shipments(db, memory_search):
    _seed()
    client = APIClient()
    token = _login(client)
    query = """
      query {
        searchShipments(q: "Whitefield", delayed: true, city: "Bengaluru") {
          total
          hits { shipmentNumber city delayed }
          facetsWarehouse
        }
      }
    """
    res = client.post("/graphql", {"query": query}, format="json", HTTP_AUTHORIZATION=f"Bearer {token}")
    body = res.json()
    assert "errors" not in body, body
    assert body["data"]["searchShipments"]["total"] >= 1
