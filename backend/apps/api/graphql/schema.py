from datetime import date, datetime
from enum import Enum
from typing import Optional

import strawberry
from asgiref.sync import sync_to_async
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Count, Max, Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from graphql import GraphQLError

from apps.api.graphql.loaders import Loaders
from apps.api.permissions import WRITE_ROLES, _roles
from apps.catalog.models import Customer as CustomerModel
from apps.catalog.models import Warehouse as WarehouseModel
from apps.common.errors import ApiError
from apps.common.queries import delayed_shipments
from apps.fleet.models import Driver as DriverModel
from apps.fleet.models import Vehicle as VehicleModel
from apps.fleet.models import VehicleAssignment
from apps.identity.models import User as UserModel
from apps.orders.models import Order as OrderModel
from apps.orders.services import confirm_order
from apps.routing.models import Route as RouteModel
from apps.routing.services import assign_route
from apps.shipments.models import Shipment as ShipmentModel
from apps.tracking.services import live_for_vehicle, snapshot_for_tenant


def _user(info: strawberry.Info) -> UserModel:
    if not info.context.user:
        raise GraphQLError("Authentication required", extensions={"code": "UNAUTHORIZED"})
    return info.context.user


def _gql(exc: ApiError):
    raise GraphQLError(exc.detail, extensions={"code": exc.code}) from exc


@strawberry.type
class UserType:
    id: strawberry.ID
    email: str
    full_name: str
    tenant_slug: str
    roles: list[str]


@strawberry.type
class AddressType:
    id: strawberry.ID
    line1: str
    city: str
    lat: Optional[float]
    lng: Optional[float]


@strawberry.type
class CustomerType:
    id: strawberry.ID
    name: str
    email: str


@strawberry.type
class WarehouseType:
    id: strawberry.ID
    code: str
    name: str


@strawberry.type
class OrderItemType:
    id: strawberry.ID
    sku: str
    description: str
    quantity: float
    weight_kg: float


@strawberry.type
class DriverType:
    id: strawberry.ID
    employee_code: str
    full_name: str
    status: str
    skills: list[str]
    rating: Optional[float]


@strawberry.enum
class VehicleLiveStatus(Enum):
    ACTIVE = "active"
    DELIVERING = "delivering"
    DELAYED = "delayed"
    OFFLINE = "offline"
    STOPPED = "stopped"


@strawberry.type
class VehicleLive:
    lat: Optional[float]
    lng: Optional[float]
    speed_kmh: Optional[float]
    heading: Optional[float]
    status: VehicleLiveStatus
    recorded_at: Optional[datetime]


@strawberry.type
class LiveCounts:
    active: int
    delivering: int
    delayed: int
    offline: int


def _live_status(raw: str | None) -> VehicleLiveStatus:
    if raw in ("idle_on_route", "stopped"):
        return VehicleLiveStatus.STOPPED
    mapping = {item.value: item for item in VehicleLiveStatus}
    return mapping.get(raw or "", VehicleLiveStatus.OFFLINE)


@strawberry.type(name="Vehicle")
class VehicleGql:
    id: strawberry.ID
    plate_number: str
    status: str
    make: str
    model: str
    vehicle_type_name: str

    @strawberry.field
    async def live(self, info: strawberry.Info) -> Optional[VehicleLive]:
        def inner():
            data = live_for_vehicle(info.context.tenant, str(self.id))
            if not data:
                return VehicleLive(
                    lat=None,
                    lng=None,
                    speed_kmh=None,
                    heading=None,
                    status=VehicleLiveStatus.OFFLINE,
                    recorded_at=None,
                )
            recorded = data.get("recorded_at")
            dt = parse_datetime(recorded) if recorded else None
            return VehicleLive(
                lat=data.get("lat"),
                lng=data.get("lng"),
                speed_kmh=data.get("speed_kmh"),
                heading=data.get("heading"),
                status=_live_status(data.get("status")),
                recorded_at=dt,
            )

        return await sync_to_async(inner)()


@strawberry.type
class ShipmentType:
    id: strawberry.ID
    shipment_number: str
    status: str
    promised_at: Optional[datetime]


@strawberry.type
class DeliveryType:
    id: strawberry.ID
    status: str
    failure_reason: str


@strawberry.type
class RouteAssignmentType:
    driver_name: Optional[str]
    vehicle_plate: Optional[str]


@strawberry.type
class RouteStopType:
    id: strawberry.ID
    sequence: int
    stop_type: str
    status: str
    _address_id: strawberry.Private[str]
    _shipment_id: strawberry.Private[Optional[str]]

    @strawberry.field
    async def address(self, info: strawberry.Info) -> AddressType:
        row = await info.context.loaders.address.load(self._address_id)
        return AddressType(id=str(row.id), line1=row.line1, city=row.city, lat=row.lat, lng=row.lng)

    @strawberry.field
    async def shipment(self, info: strawberry.Info) -> Optional[ShipmentType]:
        if not self._shipment_id:
            return None
        row = await info.context.loaders.shipment.load(self._shipment_id)
        if not row:
            return None
        return ShipmentType(
            id=str(row.id),
            shipment_number=row.shipment_number,
            status=row.status,
            promised_at=row.promised_at,
        )

    @strawberry.field
    async def delivery(self, info: strawberry.Info) -> Optional[DeliveryType]:
        row = await info.context.loaders.delivery_by_stop.load(str(self.id))
        if not row:
            return None
        return DeliveryType(id=str(row.id), status=row.status, failure_reason=row.failure_reason or "")


@strawberry.type
class OrderType:
    id: strawberry.ID
    order_number: str
    status: str
    deadline_at: Optional[datetime]
    _customer_id: strawberry.Private[str]
    _warehouse_id: strawberry.Private[str]

    @strawberry.field
    async def customer(self, info: strawberry.Info) -> CustomerType:
        row = await info.context.loaders.customer.load(self._customer_id)
        return CustomerType(id=str(row.id), name=row.name, email=row.email or "")

    @strawberry.field
    async def warehouse(self, info: strawberry.Info) -> WarehouseType:
        row = await info.context.loaders.warehouse.load(self._warehouse_id)
        return WarehouseType(id=str(row.id), code=row.code, name=row.name)

    @strawberry.field
    async def items(self, info: strawberry.Info) -> list[OrderItemType]:
        rows = await info.context.loaders.items_by_order.load(str(self.id))
        return [
            OrderItemType(
                id=str(i.id),
                sku=i.sku,
                description=i.description or "",
                quantity=float(i.quantity),
                weight_kg=float(i.weight_kg),
            )
            for i in rows
        ]

    @strawberry.field
    async def shipments(self, info: strawberry.Info) -> list[ShipmentType]:
        rows = await info.context.loaders.shipments_by_order.load(str(self.id))
        return [
            ShipmentType(
                id=str(s.id),
                shipment_number=s.shipment_number,
                status=s.status,
                promised_at=s.promised_at,
            )
            for s in rows
        ]


@strawberry.type
class RouteType:
    id: strawberry.ID
    route_number: str
    status: str
    planned_date: date

    @strawberry.field
    async def assignment(self, info: strawberry.Info) -> Optional[RouteAssignmentType]:
        row = await info.context.loaders.assignment_by_route.load(str(self.id))
        if not row:
            return None
        return RouteAssignmentType(
            driver_name=row.driver.full_name,
            vehicle_plate=row.vehicle.plate_number,
        )

    @strawberry.field
    async def stops(self, info: strawberry.Info) -> list[RouteStopType]:
        rows = await info.context.loaders.stops_by_route.load(str(self.id))
        return [
            RouteStopType(
                id=str(s.id),
                sequence=s.sequence,
                stop_type=s.stop_type,
                status=s.status,
                _address_id=str(s.address_id),
                _shipment_id=str(s.shipment_id) if s.shipment_id else None,
            )
            for s in rows
        ]


@strawberry.type
class DashboardRoute:
    id: strawberry.ID
    route_number: str
    status: str
    driver_name: Optional[str]
    vehicle_plate: Optional[str]
    stop_count: int
    completed_stops: int
    eta: Optional[datetime]


@strawberry.type
class Dashboard:
    active_vehicles: int
    active_drivers: int
    delayed_deliveries: int
    in_transit_shipments: int
    routes: list[DashboardRoute]

    @strawberry.field
    async def live_counts(self, info: strawberry.Info) -> LiveCounts:
        def inner():
            snap = snapshot_for_tenant(info.context.tenant)
            c = snap["counts"]
            return LiveCounts(
                active=c.get("active") or 0,
                delivering=c.get("delivering") or 0,
                delayed=c.get("delayed") or 0,
                offline=c.get("offline") or 0,
            )

        return await sync_to_async(inner)()


@strawberry.type
class Edge:
    cursor: str
    node: strawberry.ID


def _order_type(obj: OrderModel) -> OrderType:
    return OrderType(
        id=str(obj.id),
        order_number=obj.order_number,
        status=obj.status,
        deadline_at=obj.deadline_at,
        _customer_id=str(obj.customer_id),
        _warehouse_id=str(obj.warehouse_id),
    )


def _driver_type(obj: DriverModel) -> DriverType:
    return DriverType(
        id=str(obj.id),
        employee_code=obj.employee_code,
        full_name=obj.full_name,
        status=obj.status,
        skills=list(obj.skills or []),
        rating=float(obj.rating) if obj.rating is not None else None,
    )


def _vehicle_type(obj: VehicleModel) -> VehicleGql:
    return VehicleGql(
        id=str(obj.id),
        plate_number=obj.plate_number,
        status=obj.status,
        make=obj.make or "",
        model=obj.model or "",
        vehicle_type_name=obj.vehicle_type.name if getattr(obj, "vehicle_type", None) else "",
    )


def _route_type(obj: RouteModel) -> RouteType:
    return RouteType(
        id=str(obj.id),
        route_number=obj.route_number,
        status=obj.status,
        planned_date=obj.planned_date,
    )


@strawberry.type
class IdentityQuery:
    @strawberry.field
    async def me(self, info: strawberry.Info) -> UserType:
        def inner():
            user = _user(info)
            return UserType(
                id=str(user.id),
                email=user.email,
                full_name=user.full_name,
                tenant_slug=user.tenant.slug,
                roles=list(_roles(user)),
            )

        return await sync_to_async(inner)()


@strawberry.type
class DashboardQuery:
    @strawberry.field
    async def dashboard(self, info: strawberry.Info) -> Dashboard:
        user = _user(info)
        tenant = user.tenant
        now = timezone.now()
        today = timezone.localdate()

        def inner() -> Dashboard:
            active_vehicles = VehicleModel.objects.for_tenant(tenant).filter(
                deleted_at__isnull=True, status__in=["active", "in_use"]
            ).count()
            active_drivers = DriverModel.objects.for_tenant(tenant).filter(
                deleted_at__isnull=True, status=DriverModel.Status.AVAILABLE
            ).count()
            delayed = delayed_shipments(tenant, now=now).count()
            in_transit = ShipmentModel.objects.for_tenant(tenant).filter(status="in_transit").count()
            routes_qs = (
                RouteModel.objects.for_tenant(tenant)
                .filter(planned_date=today)
                .select_related("assignment__driver", "assignment__vehicle")
                .annotate(
                    stop_count=Count("stops"),
                    completed_stops=Count("stops", filter=Q(stops__status="completed")),
                    eta=Max("stops__planned_arrival", filter=~Q(stops__status="completed")),
                )
            )
            routes = []
            for r in routes_qs:
                try:
                    assignment = r.assignment
                except ObjectDoesNotExist:
                    assignment = None
                routes.append(
                    DashboardRoute(
                        id=str(r.id),
                        route_number=r.route_number,
                        status=r.status,
                        driver_name=assignment.driver.full_name if assignment else None,
                        vehicle_plate=assignment.vehicle.plate_number if assignment else None,
                        stop_count=r.stop_count,
                        completed_stops=r.completed_stops,
                        eta=r.eta,
                    )
                )
            return Dashboard(
                active_vehicles=active_vehicles,
                active_drivers=active_drivers,
                delayed_deliveries=delayed,
                in_transit_shipments=in_transit,
                routes=routes,
            )

        return await sync_to_async(inner)()


@strawberry.type
class FleetQuery:
    @strawberry.field
    async def driver(self, info: strawberry.Info, id: strawberry.ID) -> Optional[DriverType]:
        _user(info)

        def inner():
            row = DriverModel.objects.for_tenant(info.context.tenant).filter(id=id).first()
            return _driver_type(row) if row else None

        return await sync_to_async(inner)()

    @strawberry.field
    async def drivers(
        self,
        info: strawberry.Info,
        status: Optional[str] = None,
        has_vehicle: Optional[bool] = None,
        first: int = 20,
        after: Optional[str] = None,
    ) -> list[DriverType]:
        _user(info)

        def inner():
            qs = DriverModel.objects.for_tenant(info.context.tenant).filter(deleted_at__isnull=True)
            if status:
                qs = qs.filter(status=status)
            if has_vehicle is True:
                assigned = VehicleAssignment.objects.filter(ends_at__isnull=True).values("driver_id")
                qs = qs.filter(id__in=assigned)
            elif has_vehicle is False:
                assigned = VehicleAssignment.objects.filter(ends_at__isnull=True).values("driver_id")
                qs = qs.exclude(id__in=assigned)
            return [_driver_type(d) for d in qs.order_by("employee_code")[:first]]

        return await sync_to_async(inner)()

    @strawberry.field
    async def vehicle(self, info: strawberry.Info, id: strawberry.ID) -> Optional[VehicleGql]:
        _user(info)

        def inner():
            row = (
                VehicleModel.objects.select_related("vehicle_type")
                .for_tenant(info.context.tenant)
                .filter(id=id)
                .first()
            )
            return _vehicle_type(row) if row else None

        return await sync_to_async(inner)()

    @strawberry.field
    async def vehicles(self, info: strawberry.Info, status: Optional[str] = None, first: int = 20) -> list[VehicleGql]:
        _user(info)

        def inner():
            qs = VehicleModel.objects.select_related("vehicle_type").for_tenant(info.context.tenant).filter(
                deleted_at__isnull=True
            )
            if status:
                qs = qs.filter(status=status)
            return [_vehicle_type(v) for v in qs.order_by("plate_number")[:first]]

        return await sync_to_async(inner)()


@strawberry.type
class OrderQuery:
    @strawberry.field
    async def order(self, info: strawberry.Info, id: strawberry.ID) -> Optional[OrderType]:
        _user(info)

        def inner():
            row = OrderModel.objects.for_tenant(info.context.tenant).filter(id=id).first()
            return _order_type(row) if row else None

        return await sync_to_async(inner)()

    @strawberry.field
    async def orders(self, info: strawberry.Info, status: Optional[str] = None, first: int = 20) -> list[OrderType]:
        _user(info)

        def inner():
            qs = OrderModel.objects.for_tenant(info.context.tenant)
            if status:
                qs = qs.filter(status=status)
            return [_order_type(o) for o in qs.order_by("-created_at")[:first]]

        return await sync_to_async(inner)()

    @strawberry.field
    async def shipment(self, info: strawberry.Info, id: strawberry.ID) -> Optional[ShipmentType]:
        _user(info)

        def inner():
            row = ShipmentModel.objects.for_tenant(info.context.tenant).filter(id=id).first()
            if not row:
                return None
            return ShipmentType(
                id=str(row.id),
                shipment_number=row.shipment_number,
                status=row.status,
                promised_at=row.promised_at,
            )

        return await sync_to_async(inner)()

    @strawberry.field
    async def shipments(
        self,
        info: strawberry.Info,
        status: Optional[str] = None,
        delayed: Optional[bool] = None,
        city: Optional[str] = None,
    ) -> list[ShipmentType]:
        _user(info)

        def inner():
            qs = ShipmentModel.objects.select_related("delivery_address").for_tenant(info.context.tenant)
            if status:
                qs = qs.filter(status=status)
            if delayed:
                qs = delayed_shipments(info.context.tenant)
            if city:
                qs = qs.filter(delivery_address__city__iexact=city)
            return [
                ShipmentType(
                    id=str(s.id),
                    shipment_number=s.shipment_number,
                    status=s.status,
                    promised_at=s.promised_at,
                )
                for s in qs.order_by("-created_at")[:50]
            ]

        return await sync_to_async(inner)()


@strawberry.type
class RoutingQuery:
    @strawberry.field
    async def route(self, info: strawberry.Info, id: strawberry.ID) -> Optional[RouteType]:
        _user(info)

        def inner():
            row = RouteModel.objects.for_tenant(info.context.tenant).filter(id=id).first()
            return _route_type(row) if row else None

        return await sync_to_async(inner)()

    @strawberry.field
    async def routes(
        self, info: strawberry.Info, date: Optional[date] = None, status: Optional[str] = None
    ) -> list[RouteType]:
        _user(info)

        def inner():
            qs = RouteModel.objects.for_tenant(info.context.tenant)
            if date:
                qs = qs.filter(planned_date=date)
            if status:
                qs = qs.filter(status=status)
            return [_route_type(r) for r in qs.order_by("route_number")[:50]]

        return await sync_to_async(inner)()


@strawberry.type
class Query(IdentityQuery, DashboardQuery, FleetQuery, OrderQuery, RoutingQuery):
    pass


@strawberry.type
class Mutation:
    @strawberry.mutation
    async def confirm_order(self, info: strawberry.Info, id: strawberry.ID) -> OrderType:
        def inner():
            user = _user(info)
            if not (_roles(user) & WRITE_ROLES):
                raise GraphQLError("Forbidden", extensions={"code": "FORBIDDEN"})
            try:
                order = confirm_order(tenant=user.tenant, order_id=id)
            except ApiError as exc:
                _gql(exc)
            return _order_type(order)

        return await sync_to_async(inner)()

    @strawberry.mutation
    async def assign_route(
        self, info: strawberry.Info, route_id: strawberry.ID, driver_id: strawberry.ID, vehicle_id: strawberry.ID
    ) -> RouteType:
        def inner():
            user = _user(info)
            if not (_roles(user) & WRITE_ROLES):
                raise GraphQLError("Forbidden", extensions={"code": "FORBIDDEN"})
            try:
                route = assign_route(
                    tenant=user.tenant,
                    route_id=route_id,
                    driver_id=driver_id,
                    vehicle_id=vehicle_id,
                )
            except ApiError as exc:
                _gql(exc)
            return _route_type(route)

        return await sync_to_async(inner)()
