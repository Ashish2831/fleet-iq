# FleetIQ

Multi-tenant logistics / fleet intelligence. Architecture: `docs/architecture/`.

**Implemented:** Phase A (domain) · Phase B (REST + GraphQL + Next.js shell)

## Run

```bash
docker compose up -d postgres
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r ../requirements.txt
cp .env.example .env
python manage.py migrate
python manage.py seed_bangalore
python manage.py runserver
```

```bash
cd apps/web
npm install
npm run dev
```

- API: http://127.0.0.1:8000/api/v1/docs/ · GraphQL: http://127.0.0.1:8000/graphql
- UI: http://localhost:3000  login `acme-logistics` / `ops@acme-logistics.example` / `password`
- Postgres host port **5434**

`pytest` in `backend/` covers tenant isolation, outbox, idempotency, GraphQL dashboard, DataLoader query count.
