from __future__ import annotations

import re

from apps.ai.context import ToolContext
from apps.ai.tools import call_tool
from apps.common.errors import NotFound

SHIP_RE = re.compile(
    r"(?:shipment\s*#?\s*)?(SHP-[A-Za-z0-9-]+)|shipment\s*#?\s*([A-Za-z0-9-]+)",
    re.I,
)


def classify(question: str) -> dict:
    q = question.lower()
    number = None
    m = SHIP_RE.search(question)
    if m:
        number = m.group(1) or m.group(2)
    if "reassign" in q or "propose" in q:
        intent = "reassign"
    elif number or "shipment" in q:
        intent = "shipment"
    elif "sop" in q or "policy" in q or "temperature" in q:
        intent = "policy"
    else:
        intent = "fleet"
    return {"intent": intent, "shipment_number": number}


def _sources(knowledge: dict | None) -> list[dict]:
    hits = (knowledge or {}).get("hits") or []
    return [
        {
            "title": h.get("title") or "",
            "heading": h.get("heading") or "",
            "page": h.get("page"),
            "source": h.get("source") or "",
            "text": (h.get("text") or "")[:240],
        }
        for h in hits[:5]
    ]


def retrieve(ctx: ToolContext, classified: dict, question: str) -> dict:
    agent = "operations"
    tools: dict = {}
    intent = classified["intent"]
    number = classified.get("shipment_number")
    if intent in ("fleet", "reassign") or not number:
        tools["metrics"] = call_tool(ctx, agent, "get_delivery_metrics", "retrieve")
        tools["search"] = call_tool(ctx, agent, "search_shipments", "retrieve", delayed=True)
        tools["knowledge"] = call_tool(
            ctx, agent, "search_knowledge", "retrieve", q="late delivery promised_at Whitefield"
        )
        tools["traffic"] = call_tool(ctx, agent, "get_traffic", "retrieve", area="Whitefield")
    if intent in ("shipment", "reassign") or number:
        if number:
            try:
                tools["shipment"] = call_tool(ctx, agent, "get_shipment", "retrieve", number=number)
            except NotFound:
                tools["shipment"] = {"error": "not found", "shipment_number": number}
            ship = tools.get("shipment") or {}
            vid = ship.get("vehicle_id")
            if vid:
                tools["live"] = call_tool(ctx, agent, "get_vehicle_live", "retrieve", vehicle_id=vid)
                tools["track"] = call_tool(ctx, agent, "get_vehicle_track", "retrieve", vehicle_id=vid)
            tools["knowledge"] = call_tool(
                ctx, agent, "search_knowledge", "retrieve", q="late delivery promised_at SOP"
            )
    if intent == "policy":
        tools["knowledge"] = call_tool(ctx, agent, "search_knowledge", "retrieve", q=question)
    return tools


def analyze(tools: dict, classified: dict) -> dict:
    metrics = tools.get("metrics") or {}
    delayed_count = metrics.get("delayed_count")
    cities = metrics.get("cities") or {}
    clusters = [f"{k} ({v})" for k, v in cities.items()]
    sources = _sources(tools.get("knowledge"))
    ship = tools.get("shipment")
    causes: list[str] = []
    actions: list[str] = []
    if ship and ship.get("error"):
        return {
            "summary": "No shipment found for this tenant.",
            "delayed_count": None,
            "clusters": [],
            "root_causes": ["not_found"],
            "recommended_actions": [],
            "sources": sources,
            "proposal_id": None,
        }
    if ship:
        delayed = ship.get("delayed")
        summary = (
            f"Shipment {ship.get('shipment_number')} is "
            f"{'delayed' if delayed else 'on time'} in {ship.get('city') or 'unknown city'}."
        )
        if delayed:
            causes.append("missed promised_at")
        live = tools.get("live") or {}
        if live:
            causes.append(f"vehicle {live.get('status')}")
            summary += f" Live status {live.get('status')}."
        track = tools.get("track") or {}
        if track:
            causes.append(f"{track.get('count') or 0} GPS points in the last hour")
        if sources:
            summary += f" Policy: {sources[0].get('title') or sources[0].get('source')}."
            actions.append("Follow late-delivery SOP: notify customer and set a new ETA.")
        else:
            summary += " No policy document found."
        return {
            "summary": summary,
            "delayed_count": 1 if delayed else 0,
            "clusters": [ship.get("city")] if ship.get("city") else [],
            "root_causes": causes or ["unknown"],
            "recommended_actions": actions,
            "sources": sources,
            "proposal_id": None,
        }
    cluster_txt = ", ".join(clusters) or "no city cluster"
    if delayed_count is None:
        summary = "Delivery metrics were not available from tools."
    else:
        summary = f"{delayed_count} deliveries delayed. Clusters: {cluster_txt}."
        traffic = tools.get("traffic") or {}
        if traffic:
            summary += f" Traffic factor {traffic.get('factor')} around {traffic.get('area')}."
        search = tools.get("search") or {}
        if search.get("facets"):
            summary += f" Search facets {search.get('facets')}."
        if sources:
            summary += f" Sources: {sources[0].get('title') or sources[0].get('source')}."
        else:
            summary += " No policy document found."
        if delayed_count:
            causes.append("missed promised_at")
            actions.append("Reassign overloaded vehicles via a DispatchProposal.")
    return {
        "summary": summary,
        "delayed_count": delayed_count,
        "clusters": clusters,
        "root_causes": causes or ["unknown"],
        "recommended_actions": actions,
        "sources": sources,
        "proposal_id": None,
    }


def maybe_propose(ctx: ToolContext, question: str, tools: dict, answer: dict) -> dict:
    q = question.lower()
    if "reassign" not in q and "propose" not in q:
        return answer
    ids = []
    ship = tools.get("shipment") or {}
    if ship.get("id"):
        ids = [ship["id"]]
    result = call_tool(
        ctx,
        "operations",
        "propose_reassignment",
        "propose",
        shipment_ids=ids,
        reason=answer.get("summary") or "",
    )
    answer["proposal_id"] = result.get("proposal_id")
    actions = list(answer.get("recommended_actions") or [])
    actions.append(f"Pending DispatchProposal {result.get('proposal_id')}")
    answer["recommended_actions"] = actions
    return answer


def run(ctx: ToolContext, question: str) -> dict:
    classified = classify(question)
    ctx.log("classify", "classify", {"question": question}, classified)
    tools = retrieve(ctx, classified, question)
    answer = analyze(tools, classified)
    return maybe_propose(ctx, question, tools, answer)
