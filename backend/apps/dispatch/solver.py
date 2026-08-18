from __future__ import annotations

from apps.dispatch.constraints import (
    current_assignment,
    estimate_eta_min,
    hard_check,
    insertion_cost_km,
    leftover_kg,
    traffic_factor,
)
from apps.dispatch.scoring import score_candidate
from apps.fleet.models import Driver
from apps.routing.models import Route
from apps.search.query import search_drivers
from apps.shipments.models import Shipment


def destination_for_order(order):
    ship = (
        Shipment.objects.for_tenant(order.tenant)
        .filter(shipment_items__order_item__order=order)
        .select_related("delivery_address")
        .first()
    )
    if ship:
        return ship.delivery_address
    return None


def active_route_for_driver(driver: Driver) -> Route | None:
    return (
        Route.objects.for_tenant(driver.tenant)
        .filter(assignment__driver=driver, status__in=[Route.Status.ASSIGNED, Route.Status.IN_PROGRESS])
        .first()
    )


def candidate_drivers(order, dest, limit: int = 20) -> list[Driver]:
    lat = dest.lat if dest else order.warehouse.address.lat
    lng = dest.lng if dest else order.warehouse.address.lng
    ids = []
    try:
        result = search_drivers(
            tenant_id=order.tenant_id,
            available=True,
            lat=lat,
            lng=lng,
            radius_km=15,
            size=limit,
        )
        ids = [h["driver_id"] for h in result.get("hits") or []]
    except Exception:
        ids = []
    qs = Driver.objects.for_tenant(order.tenant).filter(deleted_at__isnull=True)
    if ids:
        found = list(qs.filter(id__in=ids))
        if found:
            return found
    return list(qs.filter(status=Driver.Status.AVAILABLE)[:limit])


def solve_insertion(order) -> dict:
    dest = destination_for_order(order)
    rejects = []
    scored = []
    for driver in candidate_drivers(order, dest):
        asg = current_assignment(driver)
        if asg is None:
            rejects.append({"driver_id": str(driver.id), "reason": "no_vehicle"})
            continue
        vehicle = asg.vehicle
        reasons = hard_check(order=order, driver=driver, vehicle=vehicle, dest=dest)
        if reasons:
            rejects.append({"driver_id": str(driver.id), "vehicle_id": str(vehicle.id), "reasons": reasons})
            continue
        route = active_route_for_driver(driver)
        dist = insertion_cost_km(vehicle=vehicle, dest=dest, route=route)
        eta = estimate_eta_min(vehicle, dest)
        leftover = leftover_kg(vehicle, order)
        features = {
            "distance_km": round(dist, 3),
            "eta_min": round(eta, 2),
            "leftover_kg": round(leftover, 2),
            "fuel_cost": round(dist * traffic_factor() * 12.0, 2),
            "lateness_risk": 1.0 if eta > 40 else 0.2,
            "rating": float(driver.rating or 0),
        }
        ranked = score_candidate(features=features, priority=order.priority)
        scored.append(
            {
                "driver_id": str(driver.id),
                "driver_name": driver.full_name,
                "vehicle_id": str(vehicle.id),
                "vehicle_plate": vehicle.plate_number,
                "route_id": str(route.id) if route else None,
                "cost": ranked["cost"],
                "features": features,
                "weights": ranked["weights"],
            }
        )
    scored.sort(key=lambda r: r["cost"])
    chosen = scored[0] if scored else {}
    return {
        "hard_pass": bool(scored),
        "chosen": chosen,
        "alternatives": scored[1:3],
        "rejects": rejects[:20],
        "score": chosen.get("cost") if chosen else None,
    }


def solve_wave(distance_matrix: list[list[float]], demands: list[int], capacities: list[int]) -> dict:
    """Tiny CVRP: nearest-neighbor + capacity. Swap in OR-Tools RoutingModel in prod."""
    n = len(distance_matrix)
    unassigned = set(range(1, n))
    routes = [[] for _ in capacities]
    load = [0 for _ in capacities]
    pos = [0 for _ in capacities]
    while unassigned:
        progress = False
        for v, cap in enumerate(capacities):
            best = None
            best_d = 1e9
            for node in list(unassigned):
                if load[v] + demands[node] > cap:
                    continue
                d = distance_matrix[pos[v]][node]
                if d < best_d:
                    best, best_d = node, d
            if best is None:
                continue
            routes[v].append(best)
            load[v] += demands[best]
            pos[v] = best
            unassigned.remove(best)
            progress = True
        if not progress:
            break
    return {"routes": routes, "unassigned": sorted(unassigned), "loads": load}
