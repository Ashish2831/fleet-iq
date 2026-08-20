#!/usr/bin/env bash
# Run Core, Tracking, AI, Analytics, and the GraphQL gateway as five processes.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/backend"
source .venv/bin/activate 2>/dev/null || true

export JWT_SECRET="${JWT_SECRET:-dev-only-change-me-please-use-32b+}"

FLEETIQ_ROLE=core daphne -b 127.0.0.1 -p 8000 config.asgi_core:application &
FLEETIQ_ROLE=tracking daphne -b 127.0.0.1 -p 8001 config.asgi_tracking:application &
FLEETIQ_ROLE=ai CORE_API_URL=http://127.0.0.1:8000 daphne -b 127.0.0.1 -p 8002 config.asgi_core:application &
FLEETIQ_ROLE=analytics daphne -b 127.0.0.1 -p 8003 config.asgi_core:application &
FLEETIQ_ROLE=gateway GATEWAY_HTTP=true \
  CORE_GRAPHQL_URL=http://127.0.0.1:8000/graphql \
  TRACKING_GRAPHQL_URL=http://127.0.0.1:8001/graphql \
  AI_GRAPHQL_URL=http://127.0.0.1:8002/graphql \
  ANALYTICS_GRAPHQL_URL=http://127.0.0.1:8003/graphql \
  daphne -b 127.0.0.1 -p 4000 config.asgi_core:application &

echo "Core :8000  Tracking :8001  AI :8002  Analytics :8003  Gateway :4000"
echo "Point the shell at NEXT_PUBLIC_GRAPHQL_URL=http://127.0.0.1:4000/graphql"
wait
