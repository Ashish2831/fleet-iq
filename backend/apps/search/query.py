from __future__ import annotations

from django.conf import settings

from apps.common.errors import Unavailable
from apps.search.store import get_search


def search_shipments(*, tenant_id, q="", delayed=None, city=None, status=None, size=25) -> dict:
    try:
        return get_search().search_shipments(
            tenant_id=str(tenant_id), q=q or "", delayed=delayed, city=city, status=status, size=size
        )
    except Exception as exc:
        if getattr(settings, "ES_ENABLED", False):
            raise Unavailable("Search temporarily unavailable") from exc
        raise


def search_drivers(
    *,
    tenant_id,
    q="",
    skills=None,
    available=None,
    lat=None,
    lng=None,
    radius_km=None,
    size=25,
) -> dict:
    try:
        return get_search().search_drivers(
            tenant_id=str(tenant_id),
            q=q or "",
            skills=skills,
            available=available,
            lat=lat,
            lng=lng,
            radius_km=radius_km,
            size=size,
        )
    except Exception as exc:
        if getattr(settings, "ES_ENABLED", False):
            raise Unavailable("Search temporarily unavailable") from exc
        raise


def search_knowledge(*, tenant_id, q: str, doc_type=None, size=5) -> dict:
    if not (q or "").strip():
        return {"hits": [], "total": 0}
    try:
        return get_search().search_knowledge(
            tenant_id=str(tenant_id), q=q, doc_type=doc_type, size=size
        )
    except Exception as exc:
        if getattr(settings, "ES_ENABLED", False):
            raise Unavailable("Search temporarily unavailable") from exc
        raise
