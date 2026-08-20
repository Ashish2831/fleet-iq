from django.core.management.base import BaseCommand

from apps.common.repositories import TenantRepository
from apps.search.indexer import reindex_tenant


class Command(BaseCommand):
    help = "Rebuild shipments, drivers, and knowledge search docs from Postgres + SOP files."

    def add_arguments(self, parser):
        parser.add_argument("--tenant", default="")

    def handle(self, *args, **opts):
        qs = TenantRepository().active()
        if opts["tenant"]:
            qs = qs.filter(slug=opts["tenant"])
        for tenant in qs:
            stats = reindex_tenant(tenant)
            self.stdout.write(f"{tenant.slug}: {stats}")
