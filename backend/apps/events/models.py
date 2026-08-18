from django.db import models

from apps.common.models import TenantModel


class ProcessedEvent(models.Model):
    consumer_name = models.CharField(max_length=64)
    event_id = models.CharField(max_length=64)
    processed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "processed_events"
        constraints = [
            models.UniqueConstraint(
                fields=["consumer_name", "event_id"], name="uq_processed_consumer_event"
            )
        ]


class DailyEventCount(TenantModel):
    updated_at = None
    day = models.DateField()
    event_type = models.CharField(max_length=128)
    count = models.IntegerField(default=0)

    class Meta:
        db_table = "analytics_daily_counts"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "day", "event_type"], name="uq_analytics_tenant_day_type"
            )
        ]
