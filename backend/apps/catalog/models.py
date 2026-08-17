import uuid

from django.db import models

from apps.common.models import TenantModel


class Address(TenantModel):
    line1 = models.CharField(max_length=255)
    line2 = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=128)
    state = models.CharField(max_length=128, blank=True)
    postal_code = models.CharField(max_length=32, blank=True)
    country = models.CharField(max_length=2, default="IN")
    lat = models.FloatField(null=True, blank=True)
    lng = models.FloatField(null=True, blank=True)
    geohash = models.CharField(max_length=16, blank=True)

    class Meta:
        db_table = "addresses"
        indexes = [models.Index(fields=["tenant", "city"], name="idx_addresses_tenant_city")]


class Warehouse(TenantModel):
    code = models.CharField(max_length=32)
    name = models.CharField(max_length=255)
    address = models.ForeignKey(Address, on_delete=models.PROTECT, related_name="warehouses")
    status = models.CharField(max_length=32, default="active")

    class Meta:
        db_table = "warehouses"
        constraints = [
            models.UniqueConstraint(fields=["tenant", "code"], name="uq_warehouses_tenant_code")
        ]


class Customer(TenantModel):
    name = models.CharField(max_length=255)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=32, blank=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    addresses = models.ManyToManyField(
        Address, through="CustomerAddress", related_name="customers"
    )

    class Meta:
        db_table = "customers"
        indexes = [models.Index(fields=["tenant", "name"], name="idx_customers_tenant_name")]


class CustomerAddress(TenantModel):
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="customer_addresses")
    address = models.ForeignKey(Address, on_delete=models.CASCADE, related_name="customer_links")
    label = models.CharField(max_length=32, default="delivery")
    is_default = models.BooleanField(default=False)

    class Meta:
        db_table = "customer_addresses"
