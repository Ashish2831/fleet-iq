import time
import uuid

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.common.repositories import RouteRepository, TenantRepository, UserRepository
from apps.routing.models import Route
from apps.tracking.geo import interpolate
from apps.tracking.services import ingest_location


class Command(BaseCommand):
    help = "Walk in-progress routes and publish GPS ticks (Phase C demo)."

    def add_arguments(self, parser):
        parser.add_argument("--tenant", default="acme-logistics")
        parser.add_argument("--interval", type=float, default=1.0)
        parser.add_argument("--steps", type=int, default=8)
        parser.add_argument("--loops", type=int, default=1)
        parser.add_argument("--once", action="store_true")

    def handle(self, *args, **opts):
        tenant = TenantRepository().by_slug(opts["tenant"])
        if not tenant:
            self.stderr.write(f"Unknown tenant {opts['tenant']}")
            return
        users = UserRepository(tenant)
        user = users.by_email("ops@acme-logistics.example", active_only=False) or users.first()
        routes = list(
            RouteRepository(tenant)
            .tenant_qs()
            .filter(status=Route.Status.IN_PROGRESS)
            .select_related("assignment__vehicle")
            .prefetch_related("stops__address")
        )
        loops = 1 if opts["once"] else opts["loops"]
        published = 0
        for _ in range(loops):
            for route in routes:
                vehicle = getattr(getattr(route, "assignment", None), "vehicle", None)
                if not vehicle:
                    continue
                stops = list(route.stops.order_by("sequence"))
                coords = [
                    (s.address.lat, s.address.lng)
                    for s in stops
                    if s.address.lat is not None and s.address.lng is not None
                ]
                if len(coords) < 2:
                    continue
                n = 2 if opts["once"] else opts["steps"]
                seq = 0
                for (lat1, lng1), (lat2, lng2) in zip(coords, coords[1:]):
                    for lat, lng in interpolate(lat1, lng1, lat2, lng2, n):
                        ingest_location(
                            user=user,
                            payload={
                                "vehicle_id": str(vehicle.id),
                                "event_id": f"sim-{route.id}-{seq}-{uuid.uuid4()}",
                                "recorded_at": timezone.now(),
                                "lat": lat,
                                "lng": lng,
                                "speed_kmh": 28,
                                "heading": 90,
                            },
                        )
                        published += 1
                        seq += 1
                        if not opts["once"]:
                            time.sleep(opts["interval"])
                        if opts["once"]:
                            break
                    if opts["once"]:
                        break
        self.stdout.write(f"Published {published} GPS ticks for {len(routes)} in-progress routes.")
