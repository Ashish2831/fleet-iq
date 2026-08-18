from __future__ import annotations

from collections import defaultdict

from apps.search.text import cosine, embed, rrf, tokenize
from apps.telemetry.geo import haversine_m


class MemorySearchStore:
    """In-process inverted index. Same document shape as Elasticsearch.

    Production: ElasticsearchSearchStore with the same method names.
    """

    def __init__(self):
        self.shipments: dict[str, dict] = {}
        self.drivers: dict[str, dict] = {}
        self.knowledge: dict[str, dict] = {}

    def reset(self) -> None:
        self.shipments.clear()
        self.drivers.clear()
        self.knowledge.clear()

    def upsert_shipment(self, doc: dict) -> None:
        self.shipments[_sid(doc["tenant_id"], doc["shipment_id"])] = doc

    def upsert_driver(self, doc: dict) -> None:
        self.drivers[_sid(doc["tenant_id"], doc["driver_id"])] = doc

    def upsert_knowledge(self, doc: dict) -> None:
        self.knowledge[_sid(doc["tenant_id"], doc["chunk_id"])] = doc

    def delete_shipment(self, tenant_id, shipment_id) -> None:
        self.shipments.pop(_sid(tenant_id, shipment_id), None)

    def search_shipments(
        self,
        *,
        tenant_id: str,
        q: str = "",
        delayed: bool | None = None,
        city: str | None = None,
        status: str | None = None,
        size: int = 25,
    ) -> dict:
        rows = [d for d in self.shipments.values() if d["tenant_id"] == str(tenant_id)]
        if delayed is not None:
            rows = [d for d in rows if bool(d.get("delayed")) is delayed]
        if city:
            rows = [d for d in rows if (d.get("city") or "").lower() == city.lower()]
        if status:
            rows = [d for d in rows if d.get("status") == status]
        scored = [(_bm25(q, d.get("search_all", "") + " " + d.get("address_text", "")), d) for d in rows]
        if q.strip():
            scored = [(s, d) for s, d in scored if s > 0]
        scored.sort(key=lambda x: x[0], reverse=True)
        hits = scored[:size]
        facets = {"by_warehouse": defaultdict(int), "by_status": defaultdict(int)}
        for _, d in scored:
            facets["by_warehouse"][d.get("warehouse_code") or ""] += 1
            facets["by_status"][d.get("status") or ""] += 1
        return {
            "hits": [{"id": d["shipment_id"], "score": s, **d} for s, d in hits],
            "total": len(scored),
            "facets": {
                "by_warehouse": dict(facets["by_warehouse"]),
                "by_status": dict(facets["by_status"]),
            },
        }

    def search_drivers(
        self,
        *,
        tenant_id: str,
        q: str = "",
        skills: list[str] | None = None,
        available: bool | None = None,
        lat: float | None = None,
        lng: float | None = None,
        radius_km: float | None = None,
        size: int = 25,
    ) -> dict:
        rows = [d for d in self.drivers.values() if d["tenant_id"] == str(tenant_id)]
        if available:
            rows = [d for d in rows if d.get("status") == "available"]
        if skills:
            need = {s.lower() for s in skills}
            rows = [d for d in rows if need <= {x.lower() for x in (d.get("skills") or [])}]
        if lat is not None and lng is not None and radius_km:
            kept = []
            for d in rows:
                loc = d.get("location") or {}
                if loc.get("lat") is None:
                    continue
                if haversine_m(lat, lng, loc["lat"], loc["lon"]) <= radius_km * 1000:
                    kept.append(d)
            rows = kept
        scored = [(_bm25(q, d.get("search_all", "")), d) for d in rows]
        if q.strip():
            scored = [(s, d) for s, d in scored if s > 0]
        scored.sort(key=lambda x: (-(x[1].get("rating") or 0), -x[0]))
        hits = scored[:size]
        return {"hits": [{"id": d["driver_id"], "score": s, **d} for s, d in hits], "total": len(scored)}

    def search_knowledge(
        self,
        *,
        tenant_id: str,
        q: str,
        doc_type: str | None = None,
        size: int = 5,
    ) -> dict:
        rows = [d for d in self.knowledge.values() if d["tenant_id"] == str(tenant_id)]
        if doc_type:
            rows = [d for d in rows if d.get("doc_type") == doc_type]
        q_vec = embed(q)
        bm25 = sorted(
            ((_bm25(q, (d.get("heading") or "") + " " + (d.get("text") or "")), d) for d in rows),
            key=lambda x: x[0],
            reverse=True,
        )
        knn = sorted(((cosine(q_vec, d.get("embedding") or []), d) for d in rows), key=lambda x: x[0], reverse=True)
        bm25_ids = [d["chunk_id"] for s, d in bm25 if s > 0][:50]
        knn_ids = [d["chunk_id"] for s, d in knn][:50]
        fused = rrf([bm25_ids, knn_ids])
        by_id = {d["chunk_id"]: d for d in rows}
        # cheap rerank: heading token overlap
        q_toks = set(tokenize(q))

        def _rerank(item):
            doc_id, rrf_score = item
            d = by_id[doc_id]
            overlap = len(q_toks & set(tokenize(d.get("heading") or "")))
            return rrf_score + 0.1 * overlap

        ranked = sorted(fused, key=_rerank, reverse=True)[:size]
        hits = []
        for doc_id, score in ranked:
            d = by_id[doc_id]
            hits.append(
                {
                    "id": d["chunk_id"],
                    "score": score,
                    "text": d.get("text") or "",
                    "title": d.get("title") or "",
                    "heading": d.get("heading") or "",
                    "page": d.get("page"),
                    "source": d.get("source") or "",
                    "doc_type": d.get("doc_type") or "",
                }
            )
        return {"hits": hits, "total": len(fused)}


def _sid(tenant_id, obj_id) -> str:
    return f"{tenant_id}:{obj_id}"


def _bm25(q: str, text: str) -> float:
    if not q.strip():
        return 0.0
    q_toks = tokenize(q)
    doc = tokenize(text)
    if not doc:
        return 0.0
    tf = defaultdict(int)
    for t in doc:
        tf[t] += 1
    score = 0.0
    for t in q_toks:
        f = tf.get(t, 0)
        if not f:
            continue
        score += (f * 2.2) / (f + 1.5)
    return score
