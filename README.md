# FleetIQ

Multi-tenant logistics / fleet intelligence. Architecture: `docs/architecture/`.

**Implemented:** Phase A (domain) · Phase B (REST + GraphQL + Next.js shell) · Phase C (Redis live GPS + Channels + `/live-map`)

## Run

```bash
docker compose up -d postgres redis
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r ../requirements.txt
cp .env.example .env
python manage.py migrate
python manage.py seed_bangalore
python manage.py runserver
```

`runserver` uses Daphne (ASGI) so `/ws/fleet` works. Postgres is on host **5434**; Redis is on **6380**.

```bash
cd apps/web
npm install
npm run dev
```

In another terminal, walk the Bangalore seed routes:

```bash
cd backend && source .venv/bin/activate
python manage.py simulate_gps --tenant acme-logistics --interval 1
```

- API: http://127.0.0.1:8000/api/v1/docs/ · GraphQL: http://127.0.0.1:8000/graphql
- UI: http://localhost:3000  login `acme-logistics` / `ops@acme-logistics.example` / `password`
- Live map: http://localhost:3000/live-map

`pytest` in `backend/` covers tenant isolation, outbox, idempotency, GraphQL, GPS ingest, Redis locks, and WebSocket rooms.
