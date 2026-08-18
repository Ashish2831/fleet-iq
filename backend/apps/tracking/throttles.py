from rest_framework.throttling import UserRateThrottle


class GpsBurstThrottle(UserRateThrottle):
    """Redis-backed via Django CACHES. Complements the 1 Hz per-vehicle Redis key."""

    scope = "gps"
    rate = "30/min"
