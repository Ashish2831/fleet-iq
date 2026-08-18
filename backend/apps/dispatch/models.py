from django.db import models
from django.db.models import Q

from apps.common.models import TenantModel, status_constraint


class DispatchProposal(TenantModel):
    class Status(models.TextChoices):
        PENDING = "pending"
        APPROVED = "approved"
        REJECTED = "rejected"
        APPLIED = "applied"
        FAILED = "failed"
        SUPERSEDED = "superseded"

    order = models.ForeignKey("orders.Order", on_delete=models.CASCADE, related_name="dispatch_proposals")
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.PENDING)
    chosen = models.JSONField(default=dict)
    alternatives = models.JSONField(default=list)
    hard_pass = models.BooleanField(default=False)
    score = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    explanation = models.JSONField(default=dict)
    policy = models.JSONField(default=dict)
    graph_run_id = models.CharField(max_length=64, blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    decided_by = models.ForeignKey(
        "identity.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="dispatch_decisions",
    )

    class Meta:
        db_table = "dispatch_proposals"
        constraints = [
            status_constraint(
                "status",
                ("pending", "approved", "rejected", "applied", "failed", "superseded"),
                "dispatch_status_valid",
            ),
            models.UniqueConstraint(
                fields=["tenant", "order"],
                condition=Q(status="pending"),
                name="uq_dispatch_pending_order",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "order", "-created_at"], name="idx_dispatch_order"),
        ]
