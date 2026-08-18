from __future__ import annotations

from django.conf import settings

from apps.telemetry.memory import MemoryTelemetryStore

_store = None


def get_store():
    global _store
    if _store is None:
        if getattr(settings, "MONGO_ENABLED", False):
            from apps.telemetry.mongo import MongoTelemetryStore

            _store = MongoTelemetryStore(
                settings.MONGO_URI,
                settings.MONGO_DB,
                raw_ttl=int(getattr(settings, "MONGO_RAW_TTL_SECONDS", 604800)),
                minute_ttl=int(getattr(settings, "MONGO_MINUTE_TTL_SECONDS", 7776000)),
            )
            _store.ensure()
        else:
            _store = MemoryTelemetryStore()
    return _store


def reset_store(store=None):
    global _store
    _store = store if store is not None else MemoryTelemetryStore()
    return _store
