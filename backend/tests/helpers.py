"""Test helpers — prefer repositories over model managers in test setup."""

from __future__ import annotations

from django.contrib.auth.hashers import make_password
from django.core.management import call_command

from apps.common.repositories import (
    AiRunRepository,
    CustomerRepository,
    DeliveryRepository,
    DispatchProposalRepository,
    DriverRepository,
    OrderRepository,
    OutboxEventRepository,
    ProcessedEventRepository,
    RoleRepository,
    RouteRepository,
    ShipmentRepository,
    TenantRepository,
    UserRepository,
    UserRoleRepository,
    VehicleRepository,
    VehicleTypeRepository,
    WarehouseRepository,
    DailyEventCountRepository,
)


def seed_bangalore(*, reset: bool = True) -> None:
    call_command("seed_bangalore", reset=reset)


def tenant_by_slug(slug: str = "acme-logistics"):
    return TenantRepository().by_slug(slug)


def acme_tenant():
    return tenant_by_slug("acme-logistics")


def beta_tenant():
    return tenant_by_slug("beta-freight")


def login(client, email="ops@acme-logistics.example", tenant="acme-logistics", password="password"):
    res = client.post(
        "/api/v1/auth/login",
        {"email": email, "password": password, "tenant": tenant},
        format="json",
    )
    assert res.status_code == 200, res.content
    return res.data["access"]


def make_ops_user(tenant, *, email: str, full_name: str = "Ops", password: str = "password"):
    user = UserRepository(tenant).create(
        email=email,
        full_name=full_name,
        hashed_password=make_password(password),
    )
    role = RoleRepository(tenant).create(name="ops_manager")
    UserRoleRepository(tenant).create(user=user, role=role)
    return user


def first_customer(tenant):
    return CustomerRepository(tenant).qs().first()


def first_warehouse(tenant):
    return WarehouseRepository(tenant).qs().first()


def first_order(tenant, **filters):
    qs = OrderRepository(tenant).qs()
    if filters:
        qs = qs.filter(**filters)
    return qs.first()


def first_vehicle(tenant):
    return VehicleRepository(tenant).qs().first()


def first_driver(tenant, **filters):
    qs = DriverRepository(tenant).qs()
    if filters:
        qs = qs.filter(**filters)
    return qs.first()


def first_shipment(tenant, **filters):
    qs = ShipmentRepository(tenant).qs()
    if filters:
        qs = qs.filter(**filters)
    return qs.first()


def first_route(tenant):
    return RouteRepository(tenant).qs().first()


def first_delivery(tenant, **filters):
    qs = DeliveryRepository(tenant).qs()
    if filters:
        qs = qs.filter(**filters)
    return qs.first()


def vehicles(tenant):
    return VehicleRepository(tenant)


def drivers(tenant):
    return DriverRepository(tenant)


def orders(tenant):
    return OrderRepository(tenant)


def shipments(tenant):
    return ShipmentRepository(tenant)


def routes(tenant):
    return RouteRepository(tenant)


def deliveries(tenant):
    return DeliveryRepository(tenant)


def proposals(tenant):
    return DispatchProposalRepository(tenant)


def outbox(tenant):
    return OutboxEventRepository(tenant)


def outbox_all():
    return OutboxEventRepository.all_qs()


def ai_runs(tenant):
    return AiRunRepository(tenant)


def users(tenant):
    return UserRepository(tenant)


def vehicle_types(tenant):
    return VehicleTypeRepository(tenant)


def daily_counts(tenant):
    return DailyEventCountRepository(tenant)


def processed_events():
    return ProcessedEventRepository()
