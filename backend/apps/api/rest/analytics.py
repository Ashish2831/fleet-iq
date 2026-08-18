from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from apps.api.permissions import CanReadOps, IsTenantAuthenticated
from apps.events.kpis import tenant_kpis


@api_view(["GET"])
@permission_classes([IsTenantAuthenticated, CanReadOps])
def kpis(request):
    return Response(tenant_kpis(request.user.tenant))
