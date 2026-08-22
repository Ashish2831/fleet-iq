#!/usr/bin/env bash
# Optional Kafka path: outbox publisher + consumers. Requires KAFKA_ENABLED=true.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/backend"
# shellcheck disable=SC1091
source .venv/bin/activate 2>/dev/null || true

python manage.py outbox_publish &
python manage.py consume_events --group fleetiq-notify &
python manage.py consume_events --group fleetiq-analytics &
python manage.py consume_events --group fleetiq-location &
python manage.py consume_events --group fleetiq-search &
python manage.py consume_events --group fleetiq-dispatch &

echo "Workers running (outbox + notify/analytics/location/search/dispatch)."
echo "Ctrl-C stops this script; kill leftover python manage.py processes if needed."
wait
