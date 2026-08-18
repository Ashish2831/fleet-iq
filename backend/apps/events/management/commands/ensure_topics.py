from django.core.management.base import BaseCommand

from apps.events.bus import get_bus
from apps.events.topics import ALL_TOPICS


class Command(BaseCommand):
    help = "Create FleetIQ Kafka topics (no-op for the in-memory bus)."

    def handle(self, *args, **opts):
        bus = get_bus()
        if hasattr(bus, "ensure_topics"):
            bus.ensure_topics(ALL_TOPICS)
        self.stdout.write("topics: " + ", ".join(ALL_TOPICS))
