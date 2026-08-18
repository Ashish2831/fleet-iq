# FleetIQ

Multi-tenant logistics / fleet intelligence. Architecture: `docs/architecture/`.

**Implemented:** Phase A (domain) · Phase B (REST + GraphQL + Next.js) · Phase C (Redis live GPS + Channels) · Phase D (outbox + Kafka/Redpanda)

## Run

```bash
docker compose up -d postgres redis redpanda console
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r ../requirements.txt
cp .env.example .env
python manage.py migrate
python manage.py seed_bangalore
python manage.py ensure_topics
python manage.py runserver
```

`runserver` uses Daphne (ASGI) so `/ws/fleet` works. Postgres **5434**, Redis **6380**, Kafka **19092**, Redpanda console **8088**.

Workers (separate terminals):

```bash
python manage.py outbox_publish          # Postgres outbox → Kafka
python manage.py consume_events --group fleetiq-notify
python manage.py consume_events --group fleetiq-analytics
python manage.py consume_events --group fleetiq-location
```

Set `KAFKA_ENABLED=true` in `backend/.env` when Redpanda is up. Leave it `false` for tests (in-memory bus). GPS ticks never write `outbox_events`; they produce `fleetiq.vehicle.location` after Redis. If Kafka is down, ingest still returns 202 and the live map keeps working.

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
- Redpanda console: http://localhost:8088

`pytest` in `backend/` covers tenant isolation, outbox, idempotency, GraphQL, GPS ingest, Redis locks, WebSocket rooms, SKIP LOCKED publish, consumer inbox, and DLQ.
