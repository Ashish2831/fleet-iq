from __future__ import annotations

import math


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def path_length_m(points: list[dict]) -> float:
    total = 0.0
    for a, b in zip(points, points[1:]):
        total += haversine_m(a["lat"], a["lng"], b["lat"], b["lng"])
    return total


def simplify(points: list[dict], epsilon_m: float = 25.0) -> list[dict]:
    """Douglas–Peucker on lat/lng using metres as the threshold."""
    if len(points) < 3:
        return points

    def _d(p, a, b):
        # distance from p to segment a-b in metres (approx)
        return abs(
            haversine_m(a["lat"], a["lng"], p["lat"], p["lng"])
            + haversine_m(p["lat"], p["lng"], b["lat"], b["lng"])
            - haversine_m(a["lat"], a["lng"], b["lat"], b["lng"])
        )

    def _rec(pts):
        if len(pts) < 3:
            return pts
        a, b = pts[0], pts[-1]
        idx, dist = 0, 0.0
        for i in range(1, len(pts) - 1):
            d = _d(pts[i], a, b)
            if d > dist:
                idx, dist = i, d
        if dist > epsilon_m:
            left = _rec(pts[: idx + 1])
            right = _rec(pts[idx:])
            return left[:-1] + right
        return [a, b]

    return _rec(points)


def idle_stops(points: list[dict], *, min_minutes: float = 2.0, max_speed: float = 3.0) -> list[dict]:
    """Speed below max_speed for at least min_minutes."""
    stops = []
    run = None
    for p in points:
        speed = float(p.get("speed_kmh") or 0)
        ts = p["recorded_at"]
        if speed < max_speed:
            if run is None:
                run = {"started_at": ts, "lat": p["lat"], "lng": p["lng"]}
            run["ended_at"] = ts
        elif run is not None:
            _flush(stops, run, min_minutes)
            run = None
    if run is not None:
        _flush(stops, run, min_minutes)
    return stops


def _flush(stops, run, min_minutes):
    start, end = run["started_at"], run["ended_at"]
    seconds = (end - start).total_seconds() if hasattr(end, "timestamp") else 0
    if seconds >= min_minutes * 60:
        stops.append({**run, "duration_s": seconds})
