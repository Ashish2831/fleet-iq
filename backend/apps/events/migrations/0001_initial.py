from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("identity", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="ProcessedEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("consumer_name", models.CharField(max_length=64)),
                ("event_id", models.CharField(max_length=64)),
                ("processed_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"db_table": "processed_events"},
        ),
        migrations.AddConstraint(
            model_name="processedevent",
            constraint=models.UniqueConstraint(
                fields=("consumer_name", "event_id"), name="uq_processed_consumer_event"
            ),
        ),
        migrations.CreateModel(
            name="DailyEventCount",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("day", models.DateField()),
                ("event_type", models.CharField(max_length=128)),
                ("count", models.IntegerField(default=0)),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="%(app_label)s_%(class)s_set",
                        to="identity.tenant",
                    ),
                ),
            ],
            options={"db_table": "analytics_daily_counts"},
        ),
        migrations.AddConstraint(
            model_name="dailyeventcount",
            constraint=models.UniqueConstraint(
                fields=("tenant", "day", "event_type"), name="uq_analytics_tenant_day_type"
            ),
        ),
    ]
