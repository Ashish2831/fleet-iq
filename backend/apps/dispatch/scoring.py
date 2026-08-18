from __future__ import annotations

DEFAULT_WEIGHTS = {
    "distance_km": 4.0,
    "eta_min": 0.15,
    "leftover_kg": 0.01,
    "fuel": 1.2,
    "priority": 8.0,
    "rating": -6.0,
}


def score_candidate(*, features: dict, weights: dict | None = None, priority: int = 0) -> dict:
    w = {**DEFAULT_WEIGHTS, **(weights or {})}
    cost = (
        w["distance_km"] * features["distance_km"]
        + w["eta_min"] * features["eta_min"]
        + w["leftover_kg"] * features["leftover_kg"]
        + w["fuel"] * features["fuel_cost"]
        + w["priority"] * priority * features["lateness_risk"]
        + w["rating"] * features["rating"]
    )
    return {"cost": round(cost, 4), "weights": w, "features": features}
