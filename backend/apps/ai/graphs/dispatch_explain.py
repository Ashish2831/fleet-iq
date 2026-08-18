from __future__ import annotations

import re

from apps.ai.context import ToolContext
from apps.ai.tools import call_tool
from apps.common.errors import NotFound
from apps.orders.models import Order

ORDER_RE = re.compile(r"(ACM-[A-Za-z0-9-]+)|order\s+#?([A-Za-z0-9-]+)", re.I)


def run(ctx: ToolContext, question: str) -> dict:
    agent = "dispatch_explain"
    m = ORDER_RE.search(question)
    number = (m.group(1) or m.group(2)) if m else None
    order = None
    if number:
        order = Order.objects.for_tenant(ctx.tenant).filter(order_number=number).first()
    if order is None:
        order = Order.objects.for_tenant(ctx.tenant).order_by("-created_at").first()
    if not order:
        return {
            "summary": "No order found for this tenant.",
            "delayed_count": None,
            "clusters": [],
            "root_causes": ["not_found"],
            "recommended_actions": [],
            "sources": [],
            "proposal_id": None,
        }
    try:
        proposal = call_tool(ctx, agent, "get_dispatch_proposal", "retrieve", order_id=str(order.id))
    except NotFound:
        return {
            "summary": f"No DispatchProposal for order {order.order_number}.",
            "delayed_count": None,
            "clusters": [],
            "root_causes": ["no_proposal"],
            "recommended_actions": [],
            "sources": [],
            "proposal_id": None,
        }
    chosen = proposal.get("chosen") or {}
    driver = chosen.get("driver_name") or chosen.get("driver_id") or "unknown"
    vehicle = chosen.get("vehicle_plate") or chosen.get("vehicle_id") or "unknown"
    summary = (
        f"Order {order.order_number} was scored to driver {driver} / vehicle {vehicle} "
        f"(score {proposal.get('score')}). This agent reads the stored proposal and does not re-solve."
    )
    return {
        "summary": summary,
        "delayed_count": None,
        "clusters": [],
        "root_causes": ["dispatch_score"],
        "recommended_actions": [],
        "sources": [{"title": "DispatchProposal", "source": str(proposal.get("id"))}],
        "proposal_id": str(proposal.get("id")),
        "explanation": proposal.get("explanation"),
        "chosen": chosen,
    }
