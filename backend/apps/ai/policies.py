READ_TOOLS = {
    "get_shipment",
    "search_shipments",
    "get_delivery_metrics",
    "get_vehicle_live",
    "get_vehicle_track",
    "get_dispatch_proposal",
    "get_driver",
    "search_drivers",
    "search_knowledge",
    "get_traffic",
}

WRITE_TOOLS = {
    "propose_reassignment",
    "propose_reoptimization",
    "open_maintenance_ticket",
}

AGENT_TOOLS = {
    "operations": READ_TOOLS | {"propose_reassignment"},
    "dispatch_explain": {"get_dispatch_proposal", "get_shipment", "search_knowledge"},
    "route_risk": READ_TOOLS | {"propose_reoptimization"},
    "maintenance": READ_TOOLS | {"open_maintenance_ticket"},
}

MAX_TOOL_CALLS = 12
