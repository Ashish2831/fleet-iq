# FleetIQ

Multi-tenant logistics / fleet intelligence. Architecture: `docs/architecture/`.

**Implemented:** Phase A (domain) · Phase B (REST + GraphQL + Next.js) · Phase C (Redis live GPS + Channels) · Phase D (outbox + Kafka/Redpanda) · Phase E (Mongo GPS history) · Phase F (Elasticsearch ops search + hybrid SOP RAG)

## Run

```bash
docker compose up -d postgres redis redpanda console mongo elasticsearch
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r ../requirements.txt
cp .env.example .env
python manage.py migrate
python manage.py seed_bangalore
python manage.py ensure_topics
python manage.py ensure_mongo
python manage.py reindex_search
python manage.py runserver
```

`runserver` uses Daphne (ASGI) so `/ws/fleet` works. Postgres **5434**, Redis **6380**, Kafka **19092**, Mongo **27018**, Elasticsearch **9201**, Redpanda console **8088**.

Workers (separate terminals):

```bash
python manage.py outbox_publish          # Postgres outbox → Kafka
python manage.py consume_events --group fleetiq-notify
python manage.py consume_events --group fleetiq-analytics
python manage.py consume_events --group fleetiq-location
python manage.py downsample_locations --minutes 2
python manage.py consume_events --group fleetiq-search
```

Set `KAFKA_ENABLED=true`, `MONGO_ENABLED=true`, and `ES_ENABLED=true` when those services are up. Leave them `false` for tests (in-memory bus, telemetry, and search). GPS history is Mongo. Ops search and SOP chunks are Elasticsearch (or the in-memory index in tests). Order create does not wait on ES.

```bash
cd apps/web
npm install
npm run dev
```

GPS demo:

```bash
cd backend && source .venv/bin/activate
python manage.py simulate_gps --tenant acme-logistics --interval 1
```

- API: http://127.0.0.1:8000/api/v1/docs/ · GraphQL: http://127.0.0.1:8000/graphql
- UI: http://localhost:3000  login `acme-logistics` / `ops@acme-logistics.example` / `password`
- Live map: http://localhost:3000/live-map
- Ops search: http://localhost:3000/search
- Redpanda console: http://localhost:8088

`pytest` in `backend/` covers tenant isolation, outbox, Kafka, Mongo history, Elasticsearch-shaped search, hybrid SOP retrieval, and tenant-scoped knowledge.
