import uuid

from django.db import models
from django.db.models import Q


class TenantQuerySet(models.QuerySet):
    def for_tenant(self, tenant):
        return self.filter(tenant=tenant)


class TenantManager(models.Manager):
    def get_queryset(self):
        return TenantQuerySet(self.model, using=self._db)

    def for_tenant(self, tenant):
        return self.get_queryset().for_tenant(tenant)


class TenantModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "identity.Tenant",
        on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)s_set",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TenantManager()

    class Meta:
        abstract = True


def status_constraint(field: str, values: tuple[str, ...], name: str):
    return models.CheckConstraint(condition=Q(**{f"{field}__in": values}), name=name)


class OutboxEvent(TenantModel):

    updated_at = None  # only created_at + published_at in the spec

    aggregate_type = models.CharField(max_length=64)
    aggregate_id = models.UUIDField()
    event_type = models.CharField(max_length=128)
    payload = models.JSONField(default=dict)
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "outbox_events"
        indexes = [
            models.Index(
                fields=["created_at"],
                name="idx_outbox_unpublished",
                condition=Q(published_at__isnull=True),
            )
        ]

    def __str__(self):
        return f"{self.event_type} {self.aggregate_id}"


class IdempotencyKey(TenantModel):
    updated_at = None
    key = models.CharField(max_length=128)
    method = models.CharField(max_length=8)
    path = models.CharField(max_length=255)
    request_hash = models.CharField(max_length=64)
    response_code = models.IntegerField(null=True, blank=True)
    response_body = models.JSONField(null=True, blank=True)

    class Meta:
        db_table = "idempotency_keys"
        constraints = [
            models.UniqueConstraint(fields=["tenant", "key"], name="uq_idempotency_tenant_key")
        ]

