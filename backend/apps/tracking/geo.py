import math


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def interpolate(lat1, lng1, lat2, lng2, steps: int):
    steps = max(steps, 1)
    for i in range(steps):
        t = i / steps
        yield lat1 + (lat2 - lat1) * t, lng1 + (lng2 - lng1) * t
