from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.telemetry.queries import downsample_window


class Command(BaseCommand):
    help = "Roll raw GPS ticks into 1-minute buckets (raw 7d / 1min 90d story)."

    def add_arguments(self, parser):
        parser.add_argument("--minutes", type=int, default=2)

    def handle(self, *args, **opts):
        end = timezone.now()
        start = end - timedelta(minutes=opts["minutes"])
        n = downsample_window(start, end)
        self.stdout.write(f"wrote {n} minute buckets")
