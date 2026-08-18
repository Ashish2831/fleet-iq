# Phase F — Elasticsearch (ops search + hybrid RAG)

**Goal:** Elasticsearch (or OpenSearch — same APIs) is the **read-optimized projection** for operational search and the **vector+BM25 store** for SOP documents. Postgres stays the system of record. You learn mappings, filters, aggregations, BM25, kNN, and a rerank step. LangGraph in Phase H **calls this retriever**; it does not own the index.

**Depends on:** Phase A/B domain APIs, Phase D Kafka domain topics. Phase E is not required for shipment search; knowledge index does not need Mongo.

**Out of scope for F:** LangGraph agents, dispatch solver, ES as source of truth, putting GPS ticks into ES (Mongo owns history).

Local: single-node ES 8+ with the `dense_vector` mapping, or OpenSearch with `knn_vector`. Pick **Elasticsearch 8** so `knn` + RRF docs match what you will cite in interviews.

---

## 1. Why Elasticsearch is here

SQL `ILIKE` and Postgres FTS can search order numbers. They struggle at:

- “delayed deliveries in Whitefield” across status + city + deadline + driver name + warehouse **in one ranked list**
- Facets: count by status, city, warehouse
- Typo / BM25 ranking (“Whitfield” ≈ Whitefield)
- Hybrid RAG: keyword **and** embedding over driver SOPs, insurance, temperature procedures

| Index | Question | Phase H |
|---|---|---|
| `shipments` | all delayed in Bangalore | ops agent tool `search_shipments` |
| `drivers` | available, reefer skill, near a point | dispatch search / agent |
| `knowledge` | “what if temperature-sensitive cargo exceeds limit?” | RAG retriever |

ES is **rebuildable**. If you wipe the cluster, a reindex job from Postgres + PDFs restores it. Never take a write that only exists in ES.

---

## 2. Indexing path

Same pattern as Mongo: **Kafka consumer → bulk indexer**. Bootstrap: `manage.py reindex_search --tenant acme-logistics`.

```
Postgres commit + outbox
        → Kafka  fleetiq.orders / routing / deliveries / fleet
        → consumer group  fleetiq-search
        → bulk index/update/delete ES

PDF / SOP upload
        → parser → chunks → embeddings
        → index  knowledge
```

`fleetiq-search` upserts on domain events:

| Event | ES action |
|---|---|
| `OrderCreated` / `OrderConfirmed` | optional orders index later; F can skip |
| `RouteUpdated` / `DriverAssigned` | update `shipments.driver_*`, `route_id` |
| `DeliveryStarted/Completed/Failed` | update `shipments.status`, `delayed` |
| vehicle/driver REST updates | also hook service-layer “search enqueue” for fields Kafka does not emit yet |

Idempotency: document `_id` = `{tenant_id}:{shipment_id}` (or driver_id). Repeat events overwrite. No inbox table required if upserts are last-write-wins on projected fields. For lagged events, store `projected_at` / `event_occurred_at` and **ignore older envelopes**.

---

## 3. Index: `shipments`

Mapping (filters = `keyword` / typed; search = `text`):

```json
{
  "mappings": {
    "properties": {
      "tenant_id":      { "type": "keyword" },
      "shipment_id":    { "type": "keyword" },
      "shipment_number": { "type": "keyword" },
      "status":         { "type": "keyword" },
      "delayed":        { "type": "boolean" },
      "promised_at":    { "type": "date" },
      "customer_name":  { "type": "text", "fields": { "raw": { "type": "keyword" } } },
      "driver_name":    { "type": "text", "fields": { "raw": { "type": "keyword" } } },
      "driver_id":      { "type": "keyword" },
      "warehouse_code": { "type": "keyword" },
      "city":           { "type": "keyword" },
      "state":          { "type": "keyword" },
      "address_text":   { "type": "text" },
      "location":       { "type": "geo_point" },
      "weight_kg":      { "type": "float" },
      "search_all":     { "type": "text" }
    }
  }
}
```

`search_all` is a catch-all (`shipment_number`, customer, address, driver, warehouse) for a single search box.

**Always filter `term: { tenant_id }` first.** ES has no accidentally-correct JOIN to save you from a leak.

Delayed flag: denormalize from Postgres (`status not terminal AND promised_at < now`). A 60s job can refresh `delayed` for in-flight docs, or compute at index time and on `promised_at` tick.

Query: *all delayed deliveries in Bangalore*

```json
{
  "query": {
    "bool": {
      "filter": [
        { "term": { "tenant_id": "…" } },
        { "term": { "delayed": true } },
        { "term": { "city": "Bengaluru" } }
      ],
      "must": { "match": { "address_text": "Whitefield" } }
    }
  },
  "aggs": {
    "by_warehouse": { "terms": { "field": "warehouse_code" } },
    "by_status":    { "terms": { "field": "status" } }
  }
}
```

This is BM25 **plus** metadata filters — the interesting part of your original design. Facets are why ops UIs use ES rather than raw SQL.

---

## 4. Index: `drivers`

```json
{
  "properties": {
    "tenant_id":     { "type": "keyword" },
    "driver_id":     { "type": "keyword" },
    "full_name":     { "type": "text", "fields": { "raw": { "type": "keyword" } } },
    "status":        { "type": "keyword" },
    "skills":        { "type": "keyword" },
    "rating":        { "type": "float" },
    "vehicle_types": { "type": "keyword" },
    "has_vehicle":   { "type": "boolean" },
    "location":      { "type": "geo_point" },
    "search_all":    { "type": "text" }
  }
}
```

`location` is **copied from Redis last-known** on a 10–30s beat (or on ingest sampled). Do not index every GPS Hz into ES — that is Mongo’s job. ES geo is for “drivers within 5 km of the warehouse **now-ish**”.

Query: available + reefer + near Whitefield:

```json
{
  "query": {
    "bool": {
      "filter": [
        { "term": { "tenant_id": "…" } },
        { "term": { "status": "available" } },
        { "term": { "skills": "reefer" } },
        { "geo_distance": { "distance": "8km", "location": { "lat": 12.97, "lon": 77.75 } } }
      ]
    }
  },
  "sort": [ { "rating": "desc" } ]
}
```

Phase G dispatch solver can call this as `get_available_drivers()` **candidate generation**, then score in Python/OR-Tools. ES is not the solver.

---

## 5. Index: `knowledge` (RAG)

Pipeline (your original diagram, implemented in F so H only graphs it):

```
PDF / markdown SOP
    → parser (pypdf / unstructured)
    → chunk (512–800 tokens, 80-token overlap, keep headings)
    → embed (OpenAI small or local bge-small)
    → ES document
```

Mapping:

```json
{
  "properties": {
    "tenant_id":     { "type": "keyword" },
    "doc_id":        { "type": "keyword" },
    "source":        { "type": "keyword" },
    "title":         { "type": "text" },
    "heading":       { "type": "text" },
    "page":          { "type": "integer" },
    "text":          { "type": "text" },
    "embedding":     { "type": "dense_vector", "dims": 768, "index": true, "similarity": "cosine" },
    "doc_type":      { "type": "keyword" }
  }
}
```

`doc_type`: `sop`, `driver_policy`, `vehicle_manual`, `insurance`, `safety`, `pricing_contract`, `warehouse_procedure`.

Seed 4–6 **real-ish** PDFs (temperature SOP, late-delivery policy, accident procedure, POD rules). RAG with empty Wikipedia dumps teaches nothing for this domain.

---

## 6. Hybrid search + rerank

This is the ES lesson that matches your original “BM25 + vector + filter + rerank”:

```
Question
  → embed query
  → ES:
       knn on embedding (k=50)
       BM25 on text (size=50)
       filter tenant_id + optional doc_type
  → RRF (reciprocal rank fusion) or weighted sum
  → rerank top 20 (cross-encoder or Cohere rerank — optional but implement one)
  → return top 5 chunks + source/page
```

REST: `POST /api/v1/search/knowledge { "q": "...", "doc_type": "sop" }`

Response **always includes sources** (`title`, `page`, `doc_id`). Phase H must cite them; the API contract starts here.

Without an LLM in F: return chunks only. A tiny “answer” endpoint that just concatenates chunks is enough to test. Full RAG generate is H.

Leaking tenants: a test that tenant B’s query cannot return tenant A’s contract chunks.

---

## 7. GraphQL / UI

```graphql
type Query {
  searchShipments(
    q: String
    delayed: Boolean
    city: String
    status: ShipmentStatus
  ): ShipmentSearchConnection!

  searchDrivers(
    q: String
    skills: [String!]
    available: Boolean
    near: GeoInput
    radiusKm: Float
  ): DriverSearchConnection!

  searchKnowledge(q: String!, docType: String): KnowledgeHitConnection!
}

type KnowledgeHit {
  text: String!
  title: String!
  page: Int
  source: String!
  score: Float!
}
```

Next.js: `/orders` list can keep Postgres pagination; add **ops search** on `/dispatch` or `/shipments/search` — one box + facet chips (status, city, delayed). `(ai)` placeholder can call `searchKnowledge` before the agent exists.

---

## 8. Failure and consistency

| Case | Expected |
|---|---|
| ES down | Create order still 201 (Postgres + outbox); search API 503; list endpoints fall back to SQL |
| Consumer lag | Search stale; UI shows “indexed as of …” optional |
| Delete shipment | ES `delete` by `_id`; missing delete = ghost hit — handle `ShipmentCancelled` |
| Reindex | Wipe index, replay from Postgres; Kafka lag catches up |

Postgres image for a shipment is canonical. If ES and SQL disagree, **trust SQL** and reindex that id.

---

## 9. What you should be able to explain after F

- ES is a denormalized projection + RAG index, not the system of record.
- `filter` (tenant, status, geo) vs `must` (BM25) vs `knn`.
- Why GPS 1 Hz does not belong in ES.
- Hybrid RRF + rerank vs “just embeddings”.
- How an agent tool is a thin client of `searchShipments` / `searchKnowledge`.
- Rebuild story from Postgres + PDFs.

---

## 10. Phase F done when

- [x] `shipments` and `drivers` indices; Kafka `fleetiq-search` upserts
- [x] Query “delayed + Bengaluru + Whitefield” returns seed shipments with warehouse facets
- [x] Driver geo + skills filter works from Redis-refreshed `location`
- [x] `knowledge` index: 4+ SOP PDFs chunked, embedded, hybrid search with sources
- [x] GraphQL `searchShipments` / `searchKnowledge` tenant-filtered
- [x] Reindex command rebuilds from Postgres
- [x] ES down does not block order create
- [x] Tenant B cannot retrieve tenant A knowledge chunks

Next: **Phase G** — dispatch as a **deterministic** scorer / OR-Tools on `OrderCreated`; Redis locks from C; ES `searchDrivers` for candidates; optional LangGraph **approval** node only (the LLM does not compute VRP).
