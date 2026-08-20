from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from apps.api.permissions import IsTenantAuthenticated
from apps.common.errors import NotFound
from apps.common.repositories import VehicleAssignmentRepository, VehicleRepository


@api_view(["GET"])
@permission_classes([IsTenantAuthenticated])
def vehicle_assignment(request, pk):
    """Core read for Tracking ingest. Prefer Kafka snapshots in production."""
    vehicle = VehicleRepository(request.user.tenant).get(pk)
    if not vehicle:
        raise NotFound("Vehicle not found")
    asg = VehicleAssignmentRepository(request.user.tenant).active_for_vehicle(vehicle)
    return Response(
        {
            "vehicle_id": str(vehicle.id),
            "plate_number": vehicle.plate_number,
            "driver_id": str(asg.driver_id) if asg else None,
            "driver_name": asg.driver.full_name if asg else None,
        }
    )
