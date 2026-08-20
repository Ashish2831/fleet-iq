"""GraphQL composition. In-process for tests; HTTP subgraphs when GATEWAY_HTTP=true."""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from asgiref.sync import async_to_sync
from django.conf import settings
from graphql import parse, OperationDefinitionNode, FieldNode
from graphql.language.ast import VariableNode

from apps.api.graphql.subgraphs import ai_schema, analytics_schema, core_schema, tracking_schema


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


def _arg_value(field: FieldNode, name: str, variables):
    for arg in field.arguments:
        if arg.name.value != name:
            continue
        node = arg.value
        if isinstance(node, VariableNode):
            return (variables or {}).get(node.name.value)
        return getattr(node, "value", None)
    return None


def _execute(schema, query: str, variables, context) -> dict:
    result = async_to_sync(schema.execute)(query, variable_values=variables or {}, context_value=context)
    out: dict = {"data": result.data}
    if result.errors:
        out["errors"] = [{"message": str(e), "path": getattr(e, "path", None)} for e in result.errors]
    return out


def _auth_header(context) -> str:
    request = getattr(context, "request", None)
    if request is None:
        return ""
    return request.META.get("HTTP_AUTHORIZATION") or request.headers.get("Authorization") or ""


def _http_graphql(url: str, query: str, variables, auth: str) -> dict:
    from apps.common.patterns.circuit_breaker import CircuitOpenError, SimpleCircuitBreaker
    from apps.common.patterns.retry import FixedRetryStrategy, with_retry

    breakers = getattr(_http_graphql, "_breakers", None)
    if breakers is None:
        breakers = {}
        _http_graphql._breakers = breakers  # type: ignore[attr-defined]
    breaker = breakers.get(url)
    if breaker is None:
        breaker = SimpleCircuitBreaker(failure_threshold=5, reset_seconds=30.0)
        breakers[url] = breaker

    body = json.dumps({"query": query, "variables": variables or {}}).encode()
    headers = {"Content-Type": "application/json"}
    if auth:
        headers["Authorization"] = auth
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")

    def call():
        try:
            with urllib.request.urlopen(req, timeout=8) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            body = exc.read().decode() if exc.fp else ""
            try:
                return json.loads(body) if body else {"data": None, "errors": [{"message": f"HTTP {exc.code}"}]}
            except json.JSONDecodeError:
                return {"data": None, "errors": [{"message": f"HTTP {exc.code}"}]}
        except urllib.error.URLError as exc:
            raise ConnectionError(str(exc)) from exc

    try:
        return breaker.call(
            lambda: with_retry(
                call,
                strategy=FixedRetryStrategy(attempts=1, delay=0.05),
                retry_on=(ConnectionError,),
                sleeper=lambda _: None,
            )
        )
    except CircuitOpenError:
        return {"data": None, "errors": [{"message": f"subgraph circuit open: {url}"}]}
    except (urllib.error.URLError, ConnectionError) as exc:
        return {"data": None, "errors": [{"message": f"subgraph unreachable: {exc}"}]}


def execute_federated(query: str, variables: dict | None, context) -> dict:
    if getattr(settings, "GATEWAY_HTTP", False):
        return _execute_http(query, variables, context)
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


CORE_DASHBOARD_FIELDS = {
    "activeVehicles": "activeVehicles",
    "activeDrivers": "activeDrivers",
    "delayedDeliveries": "delayedDeliveries",
    "inTransitShipments": "inTransitShipments",
    "routes": "routes { id routeNumber status driverName vehiclePlate stopCount completedStops eta }",
}


def _core_dashboard_query(dash: FieldNode) -> str:
    sels = _sel_names(dash)
    core_fields = [CORE_DASHBOARD_FIELDS[s] for s in sels if s in CORE_DASHBOARD_FIELDS]
    return "query { dashboard { %s } }" % (" ".join(core_fields) or "delayedDeliveries")


def _merge_dashboard(query, variables, context, dash: FieldNode, names: list[str]) -> dict:
    sels = set(_sel_names(dash))
    core = _execute(core_schema, _core_dashboard_query(dash), None, context)
    data = dict(core.get("data") or {})
    dashboard = dict((data.get("dashboard") or {}))
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
    op = _op(query)
    vehicle_f = _field(op, "vehicle")
    vid = _arg_value(vehicle_f, "id", variables) if vehicle_f else None
    sels = set(_sel_names(vehicle_f)) if vehicle_f else set()
    master = [s for s in sels if s not in TRACKING_VEHICLE_FIELDS]
    if "id" not in master:
        master.insert(0, "id")
    core_q = f'query {{ vehicle(id: "{vid}") {{ {" ".join(master)} }} }}'
    core = _execute(core_schema, core_q, None, context)
    track_bits = []
    if "live" in sels:
        track_bits.append("live { lat lng speedKmh heading status recordedAt }")
    if "track" in sels:
        track_bits.append("id")
    tracking = {"data": {}}
    if track_bits:
        tracking = _execute(
            tracking_schema,
            f'query {{ vehicle(id: "{vid}") {{ {" ".join(track_bits)} }} }}',
            None,
            context,
        )
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


def _execute_http(query: str, variables, context) -> dict:
    op = _op(query)
    names = _root_names(op)
    is_mutation = op.operation.value == "mutation"
    auth = _auth_header(context)
    core_url = settings.CORE_GRAPHQL_URL
    tracking_url = settings.TRACKING_GRAPHQL_URL
    ai_url = settings.AI_GRAPHQL_URL
    analytics_url = settings.ANALYTICS_GRAPHQL_URL

    if is_mutation and set(names) <= AI_MUTS:
        return _http_graphql(ai_url, query, variables, auth)
    if set(names) <= TRACKING_ROOTS or (set(names) <= {"vehicle"} and _vehicle_is_tracking(op)):
        return _http_graphql(tracking_url, query, variables, auth)
    if set(names) <= AI_ROOTS:
        return _http_graphql(ai_url, query, variables, auth)
    if set(names) <= ANALYTICS_ROOTS:
        return _http_graphql(analytics_url, query, variables, auth)

    dash = _field(op, "dashboard")
    core_q = _core_dashboard_query(dash) if dash else query
    core = _http_graphql(core_url, core_q, variables if not dash else None, auth)
    if not dash:
        return core
    data = dict(core.get("data") or {})
    dashboard = dict(data.get("dashboard") or {})
    sels = set(_sel_names(dash))
    errors = list(core.get("errors") or [])
    if sels & DASHBOARD_TRACKING:
        live = _http_graphql(tracking_url, "query { liveCounts { active delivering delayed offline } }", None, auth)
        if live.get("data") and data.get("dashboard") is not None:
            dashboard["liveCounts"] = live["data"].get("liveCounts")
        errors.extend(live.get("errors") or [])
    if sels & DASHBOARD_ANALYTICS:
        kpis = _http_graphql(
            analytics_url,
            "query { analyticsKpis { slaYesterday ordersYesterday deliveriesCompleted day } }",
            None,
            auth,
        )
        if kpis.get("data") and data.get("dashboard") is not None:
            payload = kpis["data"].get("analyticsKpis") or {}
            dashboard["slaYesterday"] = payload.get("slaYesterday")
            dashboard["ordersYesterday"] = payload.get("ordersYesterday")
        errors.extend(kpis.get("errors") or [])
    if data.get("dashboard") is not None:
        data["dashboard"] = dashboard
    out = {"data": data}
    if errors:
        out["errors"] = errors
    return out
