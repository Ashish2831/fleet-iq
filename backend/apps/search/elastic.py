from __future__ import annotations

"""Elasticsearch 8 adapter. Tests use MemorySearchStore; this is the local/prod backend.

Mappings: keyword filters, text BM25, dense_vector knn. GPS Hz does not belong here.
"""

from elasticsearch import Elasticsearch

from apps.search.text import EMBED_DIMS, embed


class ElasticSearchStore:
    def __init__(self, url: str):
        self.client = Elasticsearch(url, request_timeout=5)

    def ensure(self) -> None:
        if not self.client.indices.exists(index="shipments"):
            self.client.indices.create(
                index="shipments",
                mappings={
                    "properties": {
                        "tenant_id": {"type": "keyword"},
                        "shipment_id": {"type": "keyword"},
                        "shipment_number": {"type": "keyword"},
                        "status": {"type": "keyword"},
                        "delayed": {"type": "boolean"},
                        "promised_at": {"type": "date"},
                        "customer_name": {"type": "text", "fields": {"raw": {"type": "keyword"}}},
                        "driver_name": {"type": "text", "fields": {"raw": {"type": "keyword"}}},
                        "driver_id": {"type": "keyword"},
                        "warehouse_code": {"type": "keyword"},
                        "city": {"type": "keyword"},
                        "state": {"type": "keyword"},
                        "address_text": {"type": "text"},
                        "location": {"type": "geo_point"},
                        "weight_kg": {"type": "float"},
                        "search_all": {"type": "text"},
                    }
                },
            )
        if not self.client.indices.exists(index="drivers"):
            self.client.indices.create(
                index="drivers",
                mappings={
                    "properties": {
                        "tenant_id": {"type": "keyword"},
                        "driver_id": {"type": "keyword"},
                        "full_name": {"type": "text", "fields": {"raw": {"type": "keyword"}}},
                        "status": {"type": "keyword"},
                        "skills": {"type": "keyword"},
                        "rating": {"type": "float"},
                        "vehicle_types": {"type": "keyword"},
                        "has_vehicle": {"type": "boolean"},
                        "location": {"type": "geo_point"},
                        "search_all": {"type": "text"},
                    }
                },
            )
        if not self.client.indices.exists(index="knowledge"):
            self.client.indices.create(
                index="knowledge",
                mappings={
                    "properties": {
                        "tenant_id": {"type": "keyword"},
                        "chunk_id": {"type": "keyword"},
                        "doc_id": {"type": "keyword"},
                        "source": {"type": "keyword"},
                        "title": {"type": "text"},
                        "heading": {"type": "text"},
                        "page": {"type": "integer"},
                        "text": {"type": "text"},
                        "embedding": {
                            "type": "dense_vector",
                            "dims": EMBED_DIMS,
                            "index": True,
                            "similarity": "cosine",
                        },
                        "doc_type": {"type": "keyword"},
                    }
                },
            )

    def upsert_shipment(self, doc: dict) -> None:
        self.client.index(index="shipments", id=f"{doc['tenant_id']}:{doc['shipment_id']}", document=doc)

    def upsert_driver(self, doc: dict) -> None:
        self.client.index(index="drivers", id=f"{doc['tenant_id']}:{doc['driver_id']}", document=doc)

    def upsert_knowledge(self, doc: dict) -> None:
        self.client.index(index="knowledge", id=f"{doc['tenant_id']}:{doc['chunk_id']}", document=doc)

    def delete_shipment(self, tenant_id, shipment_id) -> None:
        self.client.delete(index="shipments", id=f"{tenant_id}:{shipment_id}", ignore_status=[404])

    def search_shipments(self, *, tenant_id, q="", delayed=None, city=None, status=None, size=25) -> dict:
        filt = [{"term": {"tenant_id": str(tenant_id)}}]
        if delayed is not None:
            filt.append({"term": {"delayed": delayed}})
        if city:
            filt.append({"term": {"city": city}})
        if status:
            filt.append({"term": {"status": status}})
        query = {"bool": {"filter": filt}}
        if q.strip():
            query["bool"]["must"] = [{"match": {"search_all": q}}]
        resp = self.client.search(
            index="shipments",
            query=query,
            aggregations={
                "by_warehouse": {"terms": {"field": "warehouse_code"}},
                "by_status": {"terms": {"field": "status"}},
            },
            size=size,
        )
        hits = []
        for h in resp["hits"]["hits"]:
            src = h["_source"]
            hits.append({"id": src.get("shipment_id"), "score": h["_score"], **src})
        aggs = resp.get("aggregations") or {}
        return {
            "hits": hits,
            "total": resp["hits"]["total"]["value"] if isinstance(resp["hits"]["total"], dict) else resp["hits"]["total"],
            "facets": {
                "by_warehouse": {b["key"]: b["doc_count"] for b in aggs.get("by_warehouse", {}).get("buckets", [])},
                "by_status": {b["key"]: b["doc_count"] for b in aggs.get("by_status", {}).get("buckets", [])},
            },
        }

    def search_drivers(self, *, tenant_id, q="", skills=None, available=None, lat=None, lng=None, radius_km=None, size=25) -> dict:
        filt = [{"term": {"tenant_id": str(tenant_id)}}]
        if available:
            filt.append({"term": {"status": "available"}})
        if skills:
            for s in skills:
                filt.append({"term": {"skills": s}})
        if lat is not None and lng is not None and radius_km:
            filt.append({"geo_distance": {"distance": f"{radius_km}km", "location": {"lat": lat, "lon": lng}}})
        query = {"bool": {"filter": filt}}
        if q.strip():
            query["bool"]["must"] = [{"match": {"search_all": q}}]
        resp = self.client.search(index="drivers", query=query, sort=[{"rating": "desc"}], size=size)
        hits = [{"id": h["_source"].get("driver_id"), "score": h["_score"], **h["_source"]} for h in resp["hits"]["hits"]]
        return {"hits": hits, "total": len(hits)}

    def search_knowledge(self, *, tenant_id, q, doc_type=None, size=5) -> dict:
        from apps.search.memory import MemorySearchStore

        # Reuse RRF+rerank by pulling candidate sets then fusing in Python.
        filt = [{"term": {"tenant_id": str(tenant_id)}}]
        if doc_type:
            filt.append({"term": {"doc_type": doc_type}})
        bm25 = self.client.search(
            index="knowledge",
            query={"bool": {"filter": filt, "must": [{"match": {"text": q}}]}},
            size=50,
        )
        knn = self.client.search(
            index="knowledge",
            knn={"field": "embedding", "query_vector": embed(q), "k": 50, "num_candidates": 100, "filter": {"bool": {"filter": filt}}},
            size=50,
        )
        tmp = MemorySearchStore()
        for h in list(bm25["hits"]["hits"]) + list(knn["hits"]["hits"]):
            tmp.upsert_knowledge(h["_source"])
        return tmp.search_knowledge(tenant_id=str(tenant_id), q=q, doc_type=doc_type, size=size)
