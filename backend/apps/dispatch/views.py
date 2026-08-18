from rest_framework import serializers, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response

from apps.api.permissions import CanAssign, IsTenantAuthenticated
from apps.dispatch.models import DispatchProposal
from apps.dispatch.services import approve, propose, reject
from apps.orders.models import Order


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
    queryset = DispatchProposal.objects.select_related("order")

    def get_queryset(self):
        qs = DispatchProposal.objects.for_tenant(self.request.user.tenant).select_related("order")
        status = self.request.query_params.get("status")
        if status:
            qs = qs.filter(status=status)
        return qs.order_by("-created_at")

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        proposal = approve(tenant=request.user.tenant, proposal_id=pk, actor=request.user)
        return Response(self.get_serializer(proposal).data)

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        proposal = reject(tenant=request.user.tenant, proposal_id=pk, actor=request.user)
        return Response(self.get_serializer(proposal).data)


class DispatchOrderViewSet(viewsets.ViewSet):
    permission_classes = [IsTenantAuthenticated, CanAssign]

    @action(detail=True, methods=["post"])
    def propose(self, request, pk=None):
        if not Order.objects.for_tenant(request.user.tenant).filter(id=pk).exists():
            from apps.common.errors import NotFound

            raise NotFound("Order not found")
        proposal = propose(tenant=request.user.tenant, order_id=pk)
        return Response(DispatchProposalSerializer(proposal).data)


@api_view(["POST"])
@permission_classes([IsTenantAuthenticated, CanAssign])
def dispatch_propose(request, pk):
    if not Order.objects.for_tenant(request.user.tenant).filter(id=pk).exists():
        from apps.common.errors import NotFound

        raise NotFound("Order not found")
    proposal = propose(tenant=request.user.tenant, order_id=pk)
    return Response(DispatchProposalSerializer(proposal).data)
