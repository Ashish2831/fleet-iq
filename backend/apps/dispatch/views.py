from rest_framework import serializers, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response

from apps.api.permissions import CanAssign, IsTenantAuthenticated
from apps.common.errors import NotFound
from apps.common.repositories import DispatchProposalRepository, OrderRepository
from apps.common.sanitize import sanitize_text
from apps.dispatch.models import DispatchProposal
from apps.dispatch.services import approve, propose, reject


class DispatchProposalSerializer(serializers.ModelSerializer):
    order_number = serializers.CharField(source="order.order_number", read_only=True)

    class Meta:
        model = DispatchProposal
        fields = (
            "id",
            "order",
            "order_number",
            "status",
            "chosen",
            "alternatives",
            "hard_pass",
            "score",
            "explanation",
            "policy",
            "created_at",
            "decided_at",
        )


class DispatchProposalViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsTenantAuthenticated, CanAssign]
    serializer_class = DispatchProposalSerializer
    queryset = DispatchProposal.objects.none()

    def get_queryset(self):
        qs = DispatchProposalRepository(self.request.user.tenant).qs()
        status = self.request.query_params.get("status")
        if status:
            qs = qs.filter(status=sanitize_text(status, max_len=32))
        return qs.order_by("-created_at")

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        proposal = approve(tenant=request.user.tenant, proposal_id=pk, actor=request.user)
        return Response(self.get_serializer(proposal).data)

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        proposal = reject(tenant=request.user.tenant, proposal_id=pk, actor=request.user)
        return Response(self.get_serializer(proposal).data)


@api_view(["POST"])
@permission_classes([IsTenantAuthenticated, CanAssign])
def dispatch_propose(request, pk):
    if not OrderRepository(request.user.tenant).exists(id=pk):
        raise NotFound("Order not found")
    proposal = propose(tenant=request.user.tenant, order_id=pk)
    return Response(DispatchProposalSerializer(proposal).data)
