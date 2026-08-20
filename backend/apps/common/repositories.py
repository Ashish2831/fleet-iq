"""Repository layer — tenant-scoped and global data access with a stable interface."""

from __future__ import annotations

from typing import Any, Generic, Iterable, TypeVar
from uuid import UUID

from django.db import models
from django.db.models import OuterRef

from apps.ai.models import AiRun
from apps.catalog.models import Address, Customer, CustomerAddress, Warehouse
from apps.common.models import IdempotencyKey, OutboxEvent, TenantManager
from apps.dispatch.models import DispatchProposal
from apps.events.models import DailyEventCount, ProcessedEvent
from apps.fleet.models import (
    Driver,
    FuelTransaction,
    MaintenanceRecord,
    Vehicle,
    VehicleAssignment,
    VehicleType,
)
from apps.identity.models import Permission, Role, Tenant, User, UserRole
from apps.orders.models import Order, OrderItem
from apps.routing.models import Route, RouteAssignment, RouteStop
from apps.shipments.models import Delivery, Shipment, ShipmentItem

M = TypeVar("M", bound=models.Model)


class BaseRepository(Generic[M]):
    model: type[M]

    def __init__(self, tenant):
        self.tenant = tenant

    def tenant_qs(self) -> models.QuerySet[M]:
        """Bare tenant filter — no select_related / soft-delete filters."""
        manager = self.model.objects
        if isinstance(manager, TenantManager) or hasattr(manager, "for_tenant"):
            return manager.for_tenant(self.tenant)
        return manager.filter(tenant=self.tenant)

    def qs(self) -> models.QuerySet[M]:
        return self.tenant_qs()

    def by_ids(self, ids: Iterable) -> models.QuerySet[M]:
        return self.tenant_qs().filter(pk__in=list(ids))

    def get(self, id: UUID | str) -> M | None:
        return self.qs().filter(pk=id).first()

    def get_or_none(self, **filters) -> M | None:
        return self.qs().filter(**filters).first()

    def list(self, *, offset: int = 0, limit: int = 25, **filters) -> list[M]:
        return list(self.qs().filter(**filters)[offset : offset + limit])

    def create(self, **data: Any) -> M:
        return self.model.objects.create(tenant=self.tenant, **data)

    def bulk_create(self, instances: list[M]) -> list[M]:
        return self.model.objects.bulk_create(instances)

    def update_or_create(self, defaults: dict | None = None, **lookup):
        defaults = dict(defaults or {})
        if "tenant" not in defaults and "tenant" not in lookup:
            defaults["tenant"] = self.tenant
        return self.model.objects.update_or_create(defaults=defaults, **lookup)

    def get_or_create(self, defaults: dict | None = None, **lookup):
        defaults = dict(defaults or {})
        if "tenant" not in defaults and "tenant" not in lookup:
            defaults["tenant"] = self.tenant
        return self.model.objects.get_or_create(defaults=defaults, **lookup)

    def update(self, instance: M, **data: Any) -> M:
        for key, value in data.items():
            setattr(instance, key, value)
        fields = list(data.keys())
        if "updated_at" in {f.name for f in instance._meta.fields}:
            fields.append("updated_at")
        instance.save(update_fields=fields or None)
        return instance

    def exists(self, **filters) -> bool:
        return self.qs().filter(**filters).exists()

    def count(self, **filters) -> int:
        return self.qs().filter(**filters).count()

    def for_update(self, id: UUID | str) -> M | None:
        # Do not use self.qs() — select_related outer joins break SELECT FOR UPDATE on Postgres.
        return self.tenant_qs().select_for_update().filter(pk=id).first()


class GlobalRepository(Generic[M]):
    """Non-tenant models (permissions, processed events, tenants table)."""

    model: type[M]

    def qs(self) -> models.QuerySet[M]:
        return self.model.objects.all()

    def get(self, id: UUID | str) -> M | None:
        return self.qs().filter(pk=id).first()

    def get_or_none(self, **filters) -> M | None:
        return self.qs().filter(**filters).first()

    def create(self, **data: Any) -> M:
        return self.model.objects.create(**data)

    def get_or_create(self, defaults: dict | None = None, **lookup):
        return self.model.objects.get_or_create(defaults=defaults or {}, **lookup)

    def exists(self, **filters) -> bool:
        return self.qs().filter(**filters).exists()

    def filter(self, **filters) -> models.QuerySet[M]:
        return self.qs().filter(**filters)


# --- Identity -----------------------------------------------------------------


class TenantRepository(GlobalRepository[Tenant]):
    model = Tenant

    def by_slug(self, slug: str, *, active_only: bool = False) -> Tenant | None:
        qs = self.filter(slug=slug)
        if active_only:
            qs = qs.filter(status=Tenant.Status.ACTIVE)
        return qs.first()

    def by_id(self, tenant_id) -> Tenant | None:
        return self.get(tenant_id)

    def active(self) -> models.QuerySet[Tenant]:
        return self.filter(status=Tenant.Status.ACTIVE)

    def delete_by_slugs(self, slugs: Iterable[str]) -> None:
        self.filter(slug__in=list(slugs)).delete()

    def exists_slug(self, slug: str) -> bool:
        return self.exists(slug=slug)


class UserRepository(BaseRepository[User]):
    model = User

    def qs(self):
        return self.tenant_qs().select_related("tenant")

    def by_email(self, email: str, *, active_only: bool = True) -> User | None:
        qs = self.qs().filter(email=email)
        if active_only:
            qs = qs.filter(is_active=True)
        return qs.first()

    @classmethod
    def by_id_in_tenant(cls, user_id, tenant_id) -> User | None:
        return (
            cls.model.objects.select_related("tenant")
            .filter(id=user_id, tenant_id=tenant_id, is_active=True)
            .first()
        )

    def first(self) -> User | None:
        return self.qs().first()


class PermissionRepository(GlobalRepository[Permission]):
    model = Permission

    def codenames_for_user(self, user) -> list[str]:
        return list(
            self.filter(roles__users=user).distinct().values_list("codename", flat=True)
        )


class RoleRepository(BaseRepository[Role]):
    model = Role


class UserRoleRepository(BaseRepository[UserRole]):
    model = UserRole

    def create(self, **data: Any) -> UserRole:
        # Through table may omit tenant FK depending on schema.
        if "tenant" in {f.name for f in self.model._meta.fields}:
            return super().create(**data)
        return self.model.objects.create(**data)


# --- Catalog / fleet extras ---------------------------------------------------


class CustomerRepository(BaseRepository[Customer]):
    model = Customer


class CustomerAddressRepository(BaseRepository[CustomerAddress]):
    model = CustomerAddress


class WarehouseRepository(BaseRepository[Warehouse]):
    model = Warehouse

    def qs(self):
        return self.tenant_qs().select_related("address")


class AddressRepository(BaseRepository[Address]):
    model = Address


class VehicleTypeRepository(BaseRepository[VehicleType]):
    model = VehicleType


class MaintenanceRecordRepository(BaseRepository[MaintenanceRecord]):
    model = MaintenanceRecord

    def ranked_per_vehicle(self, *, n: int = 3, annotate_rn):
        return self.tenant_qs().annotate(rn=annotate_rn).filter(rn__lte=n)


class FuelTransactionRepository(BaseRepository[FuelTransaction]):
    model = FuelTransaction

    @staticmethod
    def subquery_latest_cost():
        return (
            FuelTransaction.objects.filter(vehicle_id=OuterRef("pk"))
            .order_by("-occurred_at")
            .values("cost")[:1]
        )


# --- Orders / shipments / fleet / routing -------------------------------------


class OrderRepository(BaseRepository[Order]):
    model = Order

    def qs(self):
        return (
            self.tenant_qs()
            .select_related("customer", "warehouse")
            .prefetch_related("items")
        )

    def by_number(self, order_number: str):
        return self.get_or_none(order_number=order_number)


class OrderItemRepository(BaseRepository[OrderItem]):
    model = OrderItem

    def for_orders(self, order_ids: Iterable):
        return self.tenant_qs().filter(order_id__in=list(order_ids))


class VehicleRepository(BaseRepository[Vehicle]):
    model = Vehicle

    def qs(self):
        return (
            self.tenant_qs()
            .select_related("vehicle_type")
            .filter(deleted_at__isnull=True)
        )

    def by_plate(self, plate_number: str):
        return self.get_or_none(plate_number=plate_number)


class DriverRepository(BaseRepository[Driver]):
    model = Driver

    def qs(self):
        return self.tenant_qs().filter(deleted_at__isnull=True)

    def for_user(self, user):
        return self.qs().filter(user=user).first()


class VehicleAssignmentRepository(BaseRepository[VehicleAssignment]):
    model = VehicleAssignment

    def qs(self):
        return self.tenant_qs().select_related("driver", "vehicle")

    def active_for_vehicle(self, vehicle):
        return self.qs().filter(vehicle=vehicle, ends_at__isnull=True).first()

    def active_driver_ids(self):
        return self.tenant_qs().filter(ends_at__isnull=True).values("driver_id")

    def is_assigned(self, *, vehicle, driver) -> bool:
        return self.tenant_qs().filter(
            vehicle=vehicle, driver=driver, ends_at__isnull=True
        ).exists()

    @staticmethod
    def active_for_driver_subquery():
        return VehicleAssignment.objects.filter(
            driver_id=OuterRef("pk"), ends_at__isnull=True
        )


class ShipmentRepository(BaseRepository[Shipment]):
    model = Shipment

    def qs(self):
        return self.tenant_qs().select_related("warehouse", "delivery_address")

    def by_number(self, shipment_number: str):
        return self.get_or_none(shipment_number=shipment_number)

    def for_order(self, order_id: UUID | str):
        return (
            self.qs()
            .filter(shipment_items__order_item__order_id=order_id)
            .select_related("delivery_address", "warehouse")
            .first()
        )

    @classmethod
    def by_route_id(cls, route_id) -> list[Shipment]:
        return list(
            Shipment.objects.filter(deliveries__route_stop__route_id=route_id)
            .distinct()
            .select_related("delivery_address", "warehouse")
        )

    @classmethod
    def by_order_id(cls, order_id) -> list[Shipment]:
        return list(
            Shipment.objects.filter(shipment_items__order_item__order_id=order_id)
            .distinct()
            .select_related("delivery_address", "warehouse")
        )


class ShipmentItemRepository(BaseRepository[ShipmentItem]):
    model = ShipmentItem

    def for_orders(self, order_ids: Iterable):
        return (
            self.tenant_qs()
            .select_related("order_item")
            .filter(order_item__order_id__in=list(order_ids))
        )


class DeliveryRepository(BaseRepository[Delivery]):
    model = Delivery

    def qs(self):
        return self.tenant_qs().select_related("shipment")

    def for_stops(self, stop_ids: Iterable):
        return self.tenant_qs().filter(route_stop_id__in=list(stop_ids))


class RouteRepository(BaseRepository[Route]):
    model = Route

    def qs(self):
        return (
            self.tenant_qs()
            .select_related("assignment__driver", "assignment__vehicle")
            .prefetch_related("stops")
        )

    def in_progress_for_vehicle(self, vehicle):
        return (
            self.tenant_qs()
            .filter(assignment__vehicle=vehicle, status=Route.Status.IN_PROGRESS)
            .first()
        )

    def active_for_driver(self, driver):
        return (
            self.tenant_qs()
            .filter(
                assignment__driver=driver,
                status__in=[Route.Status.ASSIGNED, Route.Status.IN_PROGRESS],
            )
            .first()
        )


class RouteStopRepository(BaseRepository[RouteStop]):
    model = RouteStop

    def for_routes(self, route_ids: Iterable):
        return self.tenant_qs().filter(route_id__in=list(route_ids)).order_by("sequence")

    @staticmethod
    def prefetch_ordered():
        return RouteStop.objects.select_related("address", "shipment").order_by("sequence")


class RouteAssignmentRepository(BaseRepository[RouteAssignment]):
    model = RouteAssignment

    def for_routes(self, route_ids: Iterable):
        return (
            self.tenant_qs()
            .select_related("driver", "vehicle")
            .filter(route_id__in=list(route_ids))
        )


class DispatchProposalRepository(BaseRepository[DispatchProposal]):
    model = DispatchProposal

    def qs(self):
        return self.tenant_qs().select_related("order")

    def pending_for_order(self, order_id: UUID | str):
        return self.get_or_none(order_id=order_id, status=DispatchProposal.Status.PENDING)


# --- AI / API / events --------------------------------------------------------


class AiRunRepository(BaseRepository[AiRun]):
    model = AiRun

    def recent(self, *, limit: int = 50):
        return self.tenant_qs().order_by("-created_at")[:limit]


class IdempotencyKeyRepository(BaseRepository[IdempotencyKey]):
    model = IdempotencyKey

    def by_key(self, key: str) -> IdempotencyKey | None:
        return self.tenant_qs().filter(key=key).first()


class OutboxEventRepository(BaseRepository[OutboxEvent]):
    model = OutboxEvent

    @classmethod
    def claim_unpublished(cls, *, limit: int, max_attempts: int):
        return list(
            OutboxEvent.objects.select_for_update(skip_locked=True)
            .filter(published_at__isnull=True, attempts__lt=max_attempts)
            .order_by("created_at")[:limit]
        )

    @classmethod
    def all_qs(cls):
        return OutboxEvent.objects.all()


class ProcessedEventRepository(GlobalRepository[ProcessedEvent]):
    model = ProcessedEvent

    def already_processed(self, consumer_name: str, event_id: str) -> bool:
        return self.exists(consumer_name=consumer_name, event_id=str(event_id))


class DailyEventCountRepository(BaseRepository[DailyEventCount]):
    model = DailyEventCount

    def for_day(self, day):
        return self.tenant_qs().filter(day=day)

    def get_or_create_locked(self, *, day, event_type: str, defaults: dict | None = None):
        return (
            self.model.objects.select_for_update().get_or_create(
                tenant=self.tenant,
                day=day,
                event_type=event_type,
                defaults=defaults or {},
            )
        )

    def increment(self, pk) -> None:
        self.model.objects.filter(pk=pk).update(count=models.F("count") + 1)
