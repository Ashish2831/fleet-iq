from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from apps.api.permissions import IsTenantAuthenticated
from apps.common.errors import NotFound
from apps.fleet.models import Vehicle, VehicleAssignment


@api_view(["GET"])
@permission_classes([IsTenantAuthenticated])
def vehicle_assignment(request, pk):
    """Core read for Tracking ingest. Prefer Kafka snapshots in production."""
    vehicle = Vehicle.objects.for_tenant(request.user.tenant).filter(id=pk, deleted_at__isnull=True).first()
    if not vehicle:
        raise NotFound("Vehicle not found")
    asg = (
        VehicleAssignment.objects.for_tenant(request.user.tenant)
        .filter(vehicle=vehicle, ends_at__isnull=True)
        .select_related("driver")
        .first()
    )
    return Response(
        {
            "vehicle_id": str(vehicle.id),
            "plate_number": vehicle.plate_number,
            "driver_id": str(asg.driver_id) if asg else None,
            "driver_name": asg.driver.full_name if asg else None,
        }
    )
