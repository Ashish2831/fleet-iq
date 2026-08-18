from django.core.management.base import BaseCommand

from apps.telemetry.store import get_store


class Command(BaseCommand):
    help = "Create Mongo time-series + dedupe collections (no-op for the in-memory store)."

    def handle(self, *args, **opts):
        store = get_store()
        if hasattr(store, "ensure"):
            store.ensure()
            self.stdout.write("mongo collections ready")
        else:
            self.stdout.write("using in-memory telemetry store")
