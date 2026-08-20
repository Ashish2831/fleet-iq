from __future__ import annotations

from django.utils import timezone

from apps.ai.context import ToolContext
from apps.ai.graphs import dispatch_explain, maintenance, operations, route_risk
from apps.ai.models import AiRun
from apps.ai.traces import record_trace
from apps.common.errors import BadRequest
from apps.common.sanitize import sanitize_text

AGENTS = {
    "operations": operations.run,
    "dispatch_explain": dispatch_explain.run,
    "route_risk": route_risk.run,
    "maintenance": maintenance.run,
}


def serialize_run(run: AiRun) -> dict:
    return {
        "id": str(run.id),
        "agent": run.agent,
        "status": run.status,
        "input": run.input,
        "output": run.output or {},
        "proposal_id": str(run.proposal_id) if run.proposal_id else None,
        "trace": run.trace or [],
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
    }


def start_run(*, tenant, user, agent: str, question: str) -> AiRun:
    agent = sanitize_text(agent, max_len=64)
    question = sanitize_text(question, max_len=4000)
    if agent not in AGENTS:
        raise BadRequest(f"Unknown agent {agent}")
    run = AiRun.objects.create(
        tenant=tenant,
        user=user,
        agent=agent,
        input=question,
        status=AiRun.Status.RUNNING,
    )
    ctx = ToolContext(tenant=tenant, user=user)
    try:
        output = AGENTS[agent](ctx, question)
        run.output = output
        run.trace = ctx.traces
        pid = output.get("proposal_id")
        if pid:
            run.proposal_id = pid
            run.status = AiRun.Status.WAITING_APPROVAL
        else:
            run.status = AiRun.Status.COMPLETED
        run.completed_at = timezone.now()
        run.save()
        record_trace(tenant_id=tenant.id, run_id=run.id, events=ctx.traces)
    except Exception as exc:
        run.status = AiRun.Status.FAILED
        run.output = {
            "summary": str(exc),
            "delayed_count": None,
            "clusters": [],
            "root_causes": ["error"],
            "recommended_actions": [],
            "sources": [],
            "proposal_id": None,
        }
        run.trace = ctx.traces
        run.completed_at = timezone.now()
        run.save()
    return run
