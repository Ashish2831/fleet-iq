from django.core.management.base import BaseCommand

from apps.events.outbox import publish_batch


class Command(BaseCommand):
    help = "Publish unpublished outbox rows to Kafka (SKIP LOCKED)."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true")
        parser.add_argument("--limit", type=int, default=100)
        parser.add_argument("--loop-sleep", type=float, default=1.0)

    def handle(self, *args, **opts):
        import time

        while True:
            result = publish_batch(limit=opts["limit"])
            if result["claimed"]:
                self.stdout.write(str(result))
            if opts["once"]:
                return
            time.sleep(opts["loop_sleep"])
