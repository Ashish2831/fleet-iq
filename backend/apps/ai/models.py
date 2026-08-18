from django.db import models

from apps.common.models import TenantModel, status_constraint


class AiRun(TenantModel):
    class Agent(models.TextChoices):
        OPERATIONS = "operations"
        DISPATCH_EXPLAIN = "dispatch_explain"
        ROUTE_RISK = "route_risk"
        MAINTENANCE = "maintenance"

    class Status(models.TextChoices):
        RUNNING = "running"
        WAITING_APPROVAL = "waiting_approval"
        COMPLETED = "completed"
        FAILED = "failed"

    agent = models.CharField(max_length=32, choices=Agent.choices)
    user = models.ForeignKey("identity.User", on_delete=models.CASCADE, related_name="ai_runs")
    input = models.TextField()
    output = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.RUNNING)
    proposal = models.ForeignKey(
        "dispatch.DispatchProposal",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ai_runs",
    )
    trace = models.JSONField(default=list, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "ai_runs"
        constraints = [
            status_constraint(
                "status",
                ("running", "waiting_approval", "completed", "failed"),
                "ai_run_status_valid",
            ),
        ]
        indexes = [models.Index(fields=["tenant", "-created_at"], name="idx_ai_runs_tenant")]
