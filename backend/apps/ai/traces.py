from __future__ import annotations

from django.utils import timezone


def record_trace(*, tenant_id, run_id, events: list) -> dict:
    """Persist a demo debrief. OLTP path uses AiRun.trace; this is the Mongo-shaped copy."""
    doc = {
        "tenant_id": str(tenant_id),
        "run_id": str(run_id),
        "recorded_at": timezone.now().isoformat(),
        "events": events,
    }
    try:
        from apps.telemetry.store import get_store

        store = get_store()
        if hasattr(store, "traces"):
            store.traces.append(doc)
        elif hasattr(store, "insert_trace"):
            store.insert_trace(doc)
    except Exception:
        pass
    return doc
