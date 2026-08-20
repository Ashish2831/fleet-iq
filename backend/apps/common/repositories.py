"""Repository layer — tenant-scoped data access with a stable interface."""

from __future__ import annotations

from typing import Any, Generic, Iterable, TypeVar
from uuid import UUID

from django.db import models

from apps.catalog.models import Address, Customer, Warehouse
from apps.common.models import TenantManager
from apps.dispatch.models import DispatchProposal
from apps.fleet.models import Driver, Vehicle, VehicleAssignment
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


class CustomerRepository(BaseRepository[Customer]):
    model = Customer


class WarehouseRepository(BaseRepository[Warehouse]):
    model = Warehouse

    def qs(self):
        return self.tenant_qs().select_related("address")


class AddressRepository(BaseRepository[Address]):
    model = Address


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
