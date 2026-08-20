from __future__ import annotations

from apps.ai.context import ToolContext
from apps.ai.tools import call_tool
from apps.common.repositories import VehicleRepository
from apps.common.sanitize import sanitize_text


def run(ctx: ToolContext, question: str) -> dict:
    agent = "maintenance"
    question = sanitize_text(question, max_len=4000)
    vehicle = VehicleRepository(ctx.tenant).qs().first()
    if not vehicle:
        return {
            "summary": "No vehicle found for this tenant.",
            "delayed_count": None,
            "clusters": [],
            "root_causes": ["not_found"],
            "recommended_actions": [],
            "sources": [],
            "proposal_id": None,
        }
    ticket = call_tool(
        ctx,
        agent,
        "open_maintenance_ticket",
        "propose",
        vehicle_id=str(vehicle.id),
        reason=question,
    )
    return {
        "summary": (
            f"Opened maintenance ticket {ticket['ticket_id']} for vehicle {vehicle.plate_number}. "
            "VehicleMaintenanceDue is in the outbox; no silent vehicle UPDATE."
        ),
        "delayed_count": None,
        "clusters": [],
        "root_causes": ["maintenance"],
        "recommended_actions": ["Inspect vehicle before the next wave."],
        "sources": [],
        "proposal_id": None,
        "ticket": ticket,
    }
