from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from apps.ai.gateway import serialize_run, start_run
from apps.ai.models import AiRun
from apps.api.permissions import CanWriteOps, IsTenantAuthenticated
from apps.common.errors import BadRequest, NotFound
from apps.common.sanitize import sanitize_text


@api_view(["GET", "POST"])
@permission_classes([IsTenantAuthenticated, CanWriteOps])
def ai_runs(request):
    tenant = request.user.tenant
    if request.method == "GET":
        rows = AiRun.objects.for_tenant(tenant).order_by("-created_at")[:50]
        return Response([serialize_run(r) for r in rows])
    agent = sanitize_text(request.data.get("agent") or "operations", max_len=64)
    question = sanitize_text(
        request.data.get("input") or request.data.get("question") or "",
        max_len=4000,
    )
    if not question.strip():
        raise BadRequest("input is required")
    run = start_run(tenant=tenant, user=request.user, agent=agent, question=question)
    return Response(serialize_run(run), status=201)


@api_view(["GET"])
@permission_classes([IsTenantAuthenticated, CanWriteOps])
def ai_run_detail(request, pk):
    run = AiRun.objects.for_tenant(request.user.tenant).filter(id=pk).first()
    if not run:
        raise NotFound("Run not found")
    return Response(serialize_run(run))
