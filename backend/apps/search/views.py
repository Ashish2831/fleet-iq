from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from apps.api.permissions import CanReadOps, IsTenantAuthenticated
from apps.search.query import search_drivers, search_knowledge, search_shipments


@api_view(["GET"])
@permission_classes([IsTenantAuthenticated, CanReadOps])
def search_shipments_view(request):
    delayed = request.query_params.get("delayed")
    delayed_b = None if delayed is None else delayed.lower() in ("1", "true", "yes")
    result = search_shipments(
        tenant_id=request.user.tenant_id,
        q=request.query_params.get("q") or "",
        delayed=delayed_b,
        city=request.query_params.get("city"),
        status=request.query_params.get("status"),
    )
    return Response(result)


@api_view(["GET"])
@permission_classes([IsTenantAuthenticated, CanReadOps])
def search_drivers_view(request):
    skills = request.query_params.get("skills")
    skill_list = [s for s in (skills or "").split(",") if s.strip()] or None
    available = request.query_params.get("available")
    lat = request.query_params.get("lat")
    lng = request.query_params.get("lng")
    radius = request.query_params.get("radius_km")
    result = search_drivers(
        tenant_id=request.user.tenant_id,
        q=request.query_params.get("q") or "",
        skills=skill_list,
        available=None if available is None else available.lower() in ("1", "true", "yes"),
        lat=float(lat) if lat else None,
        lng=float(lng) if lng else None,
        radius_km=float(radius) if radius else None,
    )
    return Response(result)


@api_view(["POST"])
@permission_classes([IsTenantAuthenticated, CanReadOps])
def search_knowledge_view(request):
    q = (request.data.get("q") or "").strip()
    result = search_knowledge(
        tenant_id=request.user.tenant_id,
        q=q,
        doc_type=request.data.get("doc_type"),
        size=int(request.data.get("size") or 5),
    )
    return Response(result)
