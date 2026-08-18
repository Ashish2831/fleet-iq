from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("common", "0002_idempotencykey"),
    ]

    operations = [
        migrations.AddField(
            model_name="outboxevent",
            name="topic",
            field=models.CharField(blank=True, max_length=128),
        ),
        migrations.AddField(
            model_name="outboxevent",
            name="partition_key",
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.AddField(
            model_name="outboxevent",
            name="attempts",
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name="outboxevent",
            name="last_error",
            field=models.TextField(blank=True),
        ),
    ]
