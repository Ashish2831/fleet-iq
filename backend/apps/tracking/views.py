from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.response import Response

from apps.api.permissions import IsTenantAuthenticated
from apps.tracking.services import ingest_location, snapshot_for_tenant
from apps.tracking.throttles import GpsBurstThrottle


@api_view(["POST"])
@permission_classes([IsTenantAuthenticated])
@throttle_classes([GpsBurstThrottle])
def ingest(request):
    payload = request.data
    required = ("vehicle_id", "recorded_at", "lat", "lng", "event_id")
    missing = [k for k in required if k not in payload]
    if missing:
        return Response({"detail": f"Missing {missing}"}, status=400)
    try:
        result = ingest_location(user=request.user, payload=payload)
    except ValueError as exc:
        return Response({"detail": str(exc)}, status=400)
    if result.get("rate_limited"):
        return Response({"detail": "GPS rate limited", **result}, status=429)
    return Response(result, status=status.HTTP_202_ACCEPTED)


@api_view(["GET"])
@permission_classes([IsTenantAuthenticated])
def vehicles_snapshot(request):
    return Response(snapshot_for_tenant(request.user.tenant))
