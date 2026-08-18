from __future__ import annotations

from django.utils import timezone

from apps.fleet.models import Driver
from apps.search.chunk import chunk_markdown, load_sops
from apps.search.documents import driver_document, shipment_document, shipments_for_order, shipments_for_route
from apps.search.store import get_search
from apps.search.text import embed
from apps.shipments.models import Shipment


def index_shipment(shipment: Shipment) -> None:
    get_search().upsert_shipment(shipment_document(shipment))


def index_driver(driver: Driver) -> None:
    get_search().upsert_driver(driver_document(driver))


def reindex_tenant(tenant) -> dict:
    store = get_search()
    ships = Shipment.objects.for_tenant(tenant).select_related("delivery_address", "warehouse")
    n_s = 0
    for s in ships:
        store.upsert_shipment(shipment_document(s))
        n_s += 1
    n_d = 0
    for d in Driver.objects.for_tenant(tenant).filter(deleted_at__isnull=True):
        store.upsert_driver(driver_document(d))
        n_d += 1
    n_k = index_knowledge(tenant)
    return {"shipments": n_s, "drivers": n_d, "knowledge": n_k}


def index_knowledge(tenant) -> int:
    store = get_search()
    n = 0
    for doc in load_sops():
        for i, chunk in enumerate(chunk_markdown(doc["text"])):
            chunk_id = f"{doc['doc_id']}:{i}"
            text = chunk["text"]
            store.upsert_knowledge(
                {
                    "tenant_id": str(tenant.id),
                    "chunk_id": chunk_id,
                    "doc_id": doc["doc_id"],
                    "source": doc["source"],
                    "title": doc["title"],
                    "heading": chunk["heading"],
                    "page": i + 1,
                    "text": text,
                    "embedding": embed(f"{chunk['heading']} {text}"),
                    "doc_type": doc["doc_type"],
                }
            )
            n += 1
    return n


def apply_search_event(env: dict) -> None:
    """Last-write-wins upsert from Kafka. No inbox table."""
    from apps.identity.models import Tenant

    tenant = Tenant.objects.filter(id=env.get("tenant_id")).first()
    if tenant is None:
        return
    payload = env.get("payload") or {}
    event = env.get("event_type")
    if payload.get("shipment_id"):
        s = Shipment.objects.for_tenant(tenant).filter(id=payload["shipment_id"]).first()
        if s:
            index_shipment(s)
        elif event in ("ShipmentCancelled", "DeliveryFailed"):
            get_search().delete_shipment(tenant.id, payload["shipment_id"])
    if payload.get("route_id"):
        for s in shipments_for_route(payload["route_id"]):
            if str(s.tenant_id) == str(tenant.id):
                index_shipment(s)
    if payload.get("order_id"):
        for s in shipments_for_order(payload["order_id"]):
            if str(s.tenant_id) == str(tenant.id):
                index_shipment(s)
    if payload.get("driver_id"):
        d = Driver.objects.for_tenant(tenant).filter(id=payload["driver_id"]).first()
        if d:
            index_driver(d)
    if event in ("DriverAssigned",) and payload.get("driver_id"):
        d = Driver.objects.for_tenant(tenant).filter(id=payload["driver_id"]).first()
        if d:
            index_driver(d)


def refresh_delayed_flags(tenant) -> int:
    """Recompute delayed from Postgres promised_at. Call on a 60s beat or reindex."""
    now = timezone.now()
    n = 0
    for s in Shipment.objects.for_tenant(tenant).select_related("delivery_address", "warehouse"):
        index_shipment(s)
        n += 1
    return n
