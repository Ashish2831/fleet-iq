#!/usr/bin/env bash
# Bring up infra, migrate, seed Bangalore demo, index search.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

docker compose up -d postgres redis redpanda console mongo elasticsearch

echo "Waiting for Postgres…"
for i in $(seq 1 30); do
  if docker compose exec -T postgres pg_isready -U fleetiq >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

cd "$ROOT/backend"
if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -q -r "$ROOT/requirements.txt"
if [ ! -f .env ]; then
  cp .env.example .env
fi

python manage.py migrate --noinput
python manage.py seed_bangalore --reset
python manage.py ensure_topics || true
python manage.py ensure_mongo || true
python manage.py reindex_search || true

echo
echo "Demo tenant: acme-logistics / ops@acme-logistics.example / password"
echo "API  http://127.0.0.1:8000/api/v1/docs/"
echo "UI   http://localhost:3000"
echo
echo "Next:"
echo "  make run          # Django (Daphne)"
echo "  make web          # Next.js shell"
echo "  make workers      # outbox + consumers (optional)"
echo "  make gps          # simulate live map pings"
