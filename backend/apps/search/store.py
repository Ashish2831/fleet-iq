from __future__ import annotations

from django.conf import settings

from apps.search.memory import MemorySearchStore

_store = None


def get_search():
    global _store
    if _store is None:
        if getattr(settings, "ES_ENABLED", False):
            from apps.search.elastic import ElasticSearchStore

            _store = ElasticSearchStore(settings.ES_URL)
            _store.ensure()
        else:
            _store = MemorySearchStore()
    return _store


def reset_search(store=None):
    global _store
    _store = store if store is not None else MemorySearchStore()
    return _store
