"""In-process GraphQL composition. Production swaps this for Apollo Router over HTTP subgraphs."""

from __future__ import annotations

from asgiref.sync import async_to_sync
from graphql import parse, OperationDefinitionNode, FieldNode

from apps.api.graphql.subgraphs import ai_schema, analytics_schema, tracking_schema
from config.schema import schema as core_schema


TRACKING_ROOTS = {"liveCounts"}
AI_ROOTS = {"aiRun", "aiRuns"}
AI_MUTS = {"startAiRun"}
ANALYTICS_ROOTS = {"analyticsKpis"}
TRACKING_VEHICLE_FIELDS = {"live", "track"}
DASHBOARD_TRACKING = {"liveCounts"}
DASHBOARD_ANALYTICS = {"slaYesterday", "ordersYesterday"}


def _op(query: str):
    doc = parse(query)
    return next(d for d in doc.definitions if isinstance(d, OperationDefinitionNode))


def _root_names(op) -> list[str]:
    return [s.name.value for s in op.selection_set.selections if isinstance(s, FieldNode)]


def _field(op, name: str) -> FieldNode | None:
    for s in op.selection_set.selections:
        if isinstance(s, FieldNode) and s.name.value == name:
            return s
    return None


def _sel_names(field: FieldNode) -> list[str]:
    if not field.selection_set:
        return []
    return [s.name.value for s in field.selection_set.selections if isinstance(s, FieldNode)]


def _execute(schema, query: str, variables, context) -> dict:
    result = async_to_sync(schema.execute)(query, variable_values=variables or {}, context_value=context)
    out: dict = {"data": result.data}
    if result.errors:
        out["errors"] = [{"message": str(e), "path": getattr(e, "path", None)} for e in result.errors]
    return out


def execute_federated(query: str, variables: dict | None, context) -> dict:
    op = _op(query)
    names = _root_names(op)
    is_mutation = op.operation.value == "mutation"

    if is_mutation and set(names) <= AI_MUTS:
        return _execute(ai_schema, query, variables, context)
    if set(names) <= TRACKING_ROOTS or (set(names) <= {"vehicle"} and _vehicle_is_tracking(op)):
        return _execute(tracking_schema, query, variables, context)
    if set(names) <= AI_ROOTS:
        return _execute(ai_schema, query, variables, context)
    if set(names) <= ANALYTICS_ROOTS:
        return _execute(analytics_schema, query, variables, context)

    dash = _field(op, "dashboard")
    if dash:
        return _merge_dashboard(query, variables, context, dash, names)

    vehicle = _field(op, "vehicle")
    if vehicle and TRACKING_VEHICLE_FIELDS & set(_sel_names(vehicle)):
        return _merge_vehicle(query, variables, context)

    return _execute(core_schema, query, variables, context)


def _vehicle_is_tracking(op) -> bool:
    vehicle = _field(op, "vehicle")
    if not vehicle:
        return False
    sels = set(_sel_names(vehicle))
    return bool(sels) and sels <= TRACKING_VEHICLE_FIELDS | {"id"}


def _merge_dashboard(query, variables, context, dash: FieldNode, names: list[str]) -> dict:
    core = _execute(core_schema, query, variables, context)
    data = dict(core.get("data") or {})
    dashboard = dict((data.get("dashboard") or {}))
    sels = set(_sel_names(dash))
    errors = list(core.get("errors") or [])
    if sels & DASHBOARD_TRACKING:
        live = _execute(tracking_schema, "query { liveCounts { active delivering delayed offline } }", None, context)
        if live.get("data") and data.get("dashboard") is not None:
            dashboard["liveCounts"] = live["data"]["liveCounts"]
        errors.extend(live.get("errors") or [])
    if sels & DASHBOARD_ANALYTICS:
        kpis = _execute(
            analytics_schema,
            "query { analyticsKpis { slaYesterday ordersYesterday deliveriesCompleted day } }",
            None,
            context,
        )
        if kpis.get("data") and data.get("dashboard") is not None:
            payload = kpis["data"]["analyticsKpis"]
            dashboard["slaYesterday"] = payload.get("slaYesterday")
            dashboard["ordersYesterday"] = payload.get("ordersYesterday")
        errors.extend(kpis.get("errors") or [])
    if data.get("dashboard") is not None:
        data["dashboard"] = dashboard
    out = {"data": data}
    if errors:
        out["errors"] = errors
    return out


def _merge_vehicle(query, variables, context) -> dict:
    core = _execute(core_schema, query, variables, context)
    tracking = _execute(tracking_schema, query, variables, context)
    data = dict(core.get("data") or {})
    vehicle = dict(data.get("vehicle") or {})
    t_vehicle = (tracking.get("data") or {}).get("vehicle") or {}
    vehicle.update({k: v for k, v in t_vehicle.items() if v is not None or k not in vehicle})
    if data.get("vehicle") is not None or t_vehicle:
        data["vehicle"] = vehicle
    errors = list(core.get("errors") or []) + list(tracking.get("errors") or [])
    out = {"data": data}
    if errors:
        out["errors"] = errors
    return out
