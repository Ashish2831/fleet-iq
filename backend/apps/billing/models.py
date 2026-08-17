from django.db import models

from apps.common.models import TenantModel


class Invoice(TenantModel):
    customer = models.ForeignKey(
        "catalog.Customer", on_delete=models.PROTECT, related_name="invoices"
    )
    invoice_number = models.CharField(max_length=64)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=32, default="draft")

    class Meta:
        db_table = "invoices"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "invoice_number"], name="uq_invoices_tenant_number"
            )
        ]


class Payment(TenantModel):
    updated_at = None
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="payments")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=32, default="pending")
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "payments"
