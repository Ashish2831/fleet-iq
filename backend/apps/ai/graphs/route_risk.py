from __future__ import annotations

from apps.ai.context import ToolContext
from apps.ai.tools import call_tool
from apps.routing.models import Route


def run(ctx: ToolContext, question: str) -> dict:
    agent = "route_risk"
    metrics = call_tool(ctx, agent, "get_delivery_metrics", "retrieve")
    route = (
        Route.objects.for_tenant(ctx.tenant)
        .filter(status=Route.Status.IN_PROGRESS)
        .order_by("-created_at")
        .first()
    )
    if route is None:
        route = Route.objects.for_tenant(ctx.tenant).order_by("-created_at").first()
    enqueued = None
    if route:
        enqueued = call_tool(
            ctx,
            agent,
            "propose_reoptimization",
            "propose",
            route_id=str(route.id),
            reason=question,
        )
    delayed = metrics.get("delayed_count")
    summary = f"{delayed} delayed deliveries. "
    if route:
        summary += f"Enqueued reoptimization for route {route.route_number}."
    else:
        summary += "No route available to reoptimize."
    return {
        "summary": summary,
        "delayed_count": delayed,
        "clusters": list((metrics.get("cities") or {}).keys()),
        "root_causes": ["eta_risk"],
        "recommended_actions": ["Approve the wave after OR-Tools runs; do not edit stops by hand."],
        "sources": [],
        "proposal_id": None,
        "reoptimization": enqueued,
    }
