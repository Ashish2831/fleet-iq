# FleetIQ processes (Phase I)

Same Django codebase, different `FLEETIQ_ROLE` / URLConf. JWT is issued by Core and verified everywhere (`GET /api/v1/auth/jwks`).

| Process | Port | Role | Owns |
|---|---|---|---|
| Core | 8000 | `core` | Identity, orders, fleet master, dispatch apply, search |
| Tracking | 8001 | `tracking` | GPS ingest, Redis latest, Mongo history, `/ws/fleet` |
| AI | 8002 | `ai` | `/api/v1/ai/runs`, LangGraph tools |
| Analytics | 8003 | `analytics` | KPI projections from Kafka `DailyEventCount` |
| Gateway | 4000 | `gateway` | Composed GraphQL (`dashboard { … }` still works) |
| Notify | worker | — | `python manage.py consume_events --group fleetiq-notify` |

Local (without Docker):

```bash
# terminals
FLEETIQ_ROLE=core daphne -p 8000 config.asgi_core:application
FLEETIQ_ROLE=tracking daphne -p 8001 config.asgi_tracking:application
FLEETIQ_ROLE=ai daphne -p 8002 config.asgi_core:application
FLEETIQ_ROLE=analytics daphne -p 8003 config.asgi_core:application
FLEETIQ_ROLE=gateway daphne -p 4000 config.asgi_core:application
```

Compose:

```bash
docker compose --profile dist up --build
```

The in-process composer (`apps.api.federation.execute_federated`) is what tests use. Production would replace it with Apollo Router calling subgraph HTTP endpoints. Browser still has **one** GraphQL URL (the gateway). WS stays on Tracking (`NEXT_PUBLIC_TRACKING_WS`).
