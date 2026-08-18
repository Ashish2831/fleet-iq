from django.core.management.base import BaseCommand, CommandError

from apps.events.consumers import GROUP_TOPICS, consume_once


class Command(BaseCommand):
    help = "Run a Kafka consumer group (notify, analytics, dispatch, location)."

    def add_arguments(self, parser):
        parser.add_argument("--group", required=True, choices=sorted(GROUP_TOPICS))
        parser.add_argument("--once", action="store_true")
        parser.add_argument("--max-records", type=int, default=50)
        parser.add_argument("--loop-sleep", type=float, default=0.5)

    def handle(self, *args, **opts):
        import time

        group = opts["group"]
        if group not in GROUP_TOPICS:
            raise CommandError(group)
        while True:
            result = consume_once(group, max_records=opts["max_records"])
            if result["polled"]:
                self.stdout.write(f"{group} {result}")
            if opts["once"]:
                return
            time.sleep(opts["loop_sleep"])
