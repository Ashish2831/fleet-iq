from django.conf import settings
from django.contrib.auth.hashers import check_password
from django.db import connection
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from django.http import HttpResponse

from apps.api import jwt as jwt_mod
from apps.api.permissions import CanAssign, CanWriteOps, IsTenantAuthenticated
from apps.api.rest.idempotency import idempotent_post
from apps.api.rest.serializers import (
    AssignRouteSerializer,
    CustomerSerializer,
    DeliverySerializer,
    DriverSerializer,
    MeSerializer,
    OrderReadSerializer,
    OrderWriteSerializer,
    RouteSerializer,
    ShipmentSerializer,
    VehicleSerializer,
    WarehouseSerializer,
)
from datetime import timedelta

from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.catalog.models import Customer, Warehouse
from apps.catalog.services import create_customer, create_warehouse
from apps.common.errors import BadRequest, NotFound, Unauthorized
from apps.common.patterns.io_formats import get_export_strategy
from apps.common.patterns.session import default_session_storage
from apps.common.queries import delayed_shipments
from apps.common.repositories import (
    CustomerRepository,
    DeliveryRepository,
    DriverRepository,
    OrderRepository,
    RouteRepository,
    ShipmentRepository,
    TenantRepository,
    UserRepository,
    VehicleRepository,
    WarehouseRepository,
)
from apps.fleet.models import Driver, Vehicle
from apps.fleet.services import create_driver, create_vehicle
from apps.identity.services import update_profile
from apps.orders.models import Order
from apps.orders.services import confirm_order, create_order
from apps.routing.models import Route
from apps.routing.services import assign_route, create_draft_route
from apps.shipments.models import Delivery, Shipment
from apps.shipments.services import complete_delivery, create_draft_shipment
from apps.telemetry.queries import vehicle_track


def _set_refresh_cookie(response, token: str):
    response.set_cookie(
        "fq_refresh",
        token,
        httponly=True,
        secure=False,
        samesite="Lax",
        max_age=60 * 60 * 24 * 7,
        path="/api/v1/auth",
    )
    return response


class LoginThrottle(AnonRateThrottle):
    rate = "20/min"


@api_view(["GET"])
@permission_classes([AllowAny])
def health(_request):
    return Response({"status": "ok", "phase": "I", "role": getattr(settings, "FLEETIQ_ROLE", "all")})


@api_view(["GET"])
@permission_classes([AllowAny])
def ready(_request):
    connection.ensure_connection()
    return Response({"status": "ready"})


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([LoginThrottle])
def login(request):
    email = request.data.get("email")
    password = request.data.get("password")
    tenant_slug = request.data.get("tenant")
    if not email or not password or not tenant_slug:
        raise Unauthorized("email, password, and tenant are required")
    tenant = TenantRepository().by_slug(tenant_slug, active_only=True)
    user = UserRepository(tenant).by_email(email) if tenant else None
    if not user or not check_password(password, user.hashed_password):
        raise Unauthorized("Invalid credentials")
    access = jwt_mod.access_token(user)
    refresh = jwt_mod.refresh_token(user)
    session_id = default_session_storage().create(
        {"user_id": str(user.id), "tenant_id": str(user.tenant_id), "email": user.email},
        ttl_seconds=60 * 60 * 24 * 7,
    )
    response = Response({"access": access, "user": MeSerializer(user).data, "session_id": session_id})
    return _set_refresh_cookie(response, refresh)


@api_view(["POST"])
@permission_classes([AllowAny])
def refresh(request):
    token = request.COOKIES.get("fq_refresh") or request.data.get("refresh")
    if not token:
        raise Unauthorized("Missing refresh token")
    payload = jwt_mod.decode(token, "refresh")
    user = UserRepository.by_id_in_tenant(payload["sub"], payload["tid"])
    if not user or not user.is_active:
        raise Unauthorized("Invalid refresh token")
    return Response({"access": jwt_mod.access_token(user)})


@api_view(["GET", "PATCH"])
@permission_classes([IsTenantAuthenticated])
def me(request):
    if request.method == "PATCH":
        name = request.data.get("full_name")
        if name:
            update_profile(user=request.user, full_name=name)
    return Response(MeSerializer(request.user).data)


class TenantViewSet(viewsets.ModelViewSet):
    permission_classes = [IsTenantAuthenticated, CanWriteOps]
    http_method_names = ["get", "post", "patch", "head", "options"]
    filter_backends = [DjangoFilterBackend]

    def get_queryset(self):
        return self.queryset.for_tenant(self.request.user.tenant)

    def perform_create(self, serializer):
        serializer.save(tenant=self.request.user.tenant)


class DriverViewSet(TenantViewSet):
    queryset = Driver.objects.none()
    serializer_class = DriverSerializer
    filterset_fields = ("status",)

    def get_queryset(self):
        return DriverRepository(self.request.user.tenant).qs()

    def perform_create(self, serializer):
        serializer.instance = create_driver(tenant=self.request.user.tenant, **serializer.validated_data)


class VehicleViewSet(TenantViewSet):
    queryset = Vehicle.objects.none()
    serializer_class = VehicleSerializer
    filterset_fields = ("status",)

    def get_queryset(self):
        return VehicleRepository(self.request.user.tenant).qs()

    def perform_create(self, serializer):
        serializer.instance = create_vehicle(tenant=self.request.user.tenant, **serializer.validated_data)

    @action(detail=True, methods=["get"])
    def track(self, request, pk=None):
        vehicle = self.get_object()
        now = timezone.now()
        start = parse_datetime(request.query_params.get("from") or "") or (now - timedelta(minutes=15))
        end = parse_datetime(request.query_params.get("to") or "") or now
        if start.tzinfo is None:
            start = timezone.make_aware(start)
        if end.tzinfo is None:
            end = timezone.make_aware(end)
        source = request.query_params.get("source") or "raw"
        points = vehicle_track(
            tenant_id=request.user.tenant_id,
            vehicle_id=vehicle.id,
            start=start,
            end=end,
            source=source,
        )
        return Response(
            {
                "vehicle_id": str(vehicle.id),
                "source": source,
                "points": [
                    {
                        "recorded_at": p["recorded_at"].isoformat(),
                        "lat": p["lat"],
                        "lng": p["lng"],
                        "speed_kmh": p["speed_kmh"],
                        "heading": p.get("heading"),
                    }
                    for p in points
                ],
            }
        )


class WarehouseViewSet(TenantViewSet):
    queryset = Warehouse.objects.none()
    serializer_class = WarehouseSerializer

    def get_queryset(self):
        return WarehouseRepository(self.request.user.tenant).qs()

    def perform_create(self, serializer):
        data = serializer.validated_data
        serializer.instance = create_warehouse(
            tenant=self.request.user.tenant,
            code=data["code"],
            name=data["name"],
            address_id=data.pop("address_id"),
            status=data.get("status"),
        )


class CustomerViewSet(TenantViewSet):
    queryset = Customer.objects.none()
    serializer_class = CustomerSerializer
    filterset_fields = ("name",)

    def get_queryset(self):
        return CustomerRepository(self.request.user.tenant).qs().filter(deleted_at__isnull=True)

    def perform_create(self, serializer):
        serializer.instance = create_customer(tenant=self.request.user.tenant, **serializer.validated_data)


class OrderViewSet(TenantViewSet):
    queryset = Order.objects.none()
    filterset_fields = ("status",)

    def get_queryset(self):
        return OrderRepository(self.request.user.tenant).qs()

    def get_serializer_class(self):
        if self.action == "create":
            return OrderWriteSerializer
        return OrderReadSerializer

    def create(self, request, *args, **kwargs):
        def handler():
            ser = OrderWriteSerializer(data=request.data)
            ser.is_valid(raise_exception=True)
            data = ser.validated_data
            tenant = request.user.tenant
            customer = CustomerRepository(tenant).get(data["customer_id"])
            warehouse = WarehouseRepository(tenant).get(data["warehouse_id"])
            if not customer or not warehouse:
                raise NotFound("Customer or warehouse not found")
            order = create_order(
                tenant=tenant,
                customer=customer,
                warehouse=warehouse,
                order_number=data["order_number"],
                items=data["items"],
                deadline_at=data.get("deadline_at"),
                notes=data.get("notes") or "",
            )
            out = OrderReadSerializer(OrderRepository(tenant).get(order.pk))
            return Response(out.data, status=status.HTTP_201_CREATED)

        return idempotent_post(request, handler)

    @action(detail=True, methods=["post"])
    def confirm(self, request, pk=None):
        order = confirm_order(tenant=request.user.tenant, order_id=pk)
        return Response(OrderReadSerializer(order).data)

    @action(detail=False, methods=["get"])
    def export(self, request):
        fmt = request.query_params.get("format") or "csv"
        try:
            strategy = get_export_strategy(fmt)
        except ValueError as exc:
            raise BadRequest(str(exc)) from exc
        qs = self.filter_queryset(self.get_queryset())[:500]
        rows = [
            {
                "id": str(o.id),
                "order_number": o.order_number,
                "status": o.status,
                "customer": getattr(o.customer, "name", ""),
                "warehouse": getattr(o.warehouse, "code", ""),
                "priority": o.priority,
                "deadline_at": o.deadline_at.isoformat() if o.deadline_at else "",
            }
            for o in qs
        ]
        payload = strategy.export(
            rows,
            fieldnames=["id", "order_number", "status", "customer", "warehouse", "priority", "deadline_at"],
        )
        response = HttpResponse(payload, content_type=strategy.content_type)
        response["Content-Disposition"] = f'attachment; filename="orders.{strategy.extension}"'
        return response


class ShipmentViewSet(TenantViewSet):
    queryset = Shipment.objects.none()
    serializer_class = ShipmentSerializer
    filterset_fields = ("status",)

    def get_queryset(self):
        return ShipmentRepository(self.request.user.tenant).qs()

    def perform_create(self, serializer):
        serializer.instance = create_draft_shipment(tenant=self.request.user.tenant, **serializer.validated_data)


class RouteViewSet(TenantViewSet):
    queryset = Route.objects.none()
    serializer_class = RouteSerializer
    filterset_fields = ("status",)

    def get_queryset(self):
        return RouteRepository(self.request.user.tenant).qs()

    def perform_create(self, serializer):
        serializer.instance = create_draft_route(tenant=self.request.user.tenant, **serializer.validated_data)

    @action(detail=True, methods=["post"], permission_classes=[IsTenantAuthenticated, CanAssign])
    def assign(self, request, pk=None):
        ser = AssignRouteSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        route = assign_route(
            tenant=request.user.tenant,
            route_id=pk,
            driver_id=ser.validated_data["driver_id"],
            vehicle_id=ser.validated_data["vehicle_id"],
        )
        route = RouteRepository(request.user.tenant).get(route.pk)
        return Response(RouteSerializer(route).data)


class DeliveryViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsTenantAuthenticated, CanWriteOps]
    serializer_class = DeliverySerializer
    queryset = Delivery.objects.none()

    def get_queryset(self):
        from apps.common.sanitize import sanitize_text

        qs = DeliveryRepository(self.request.user.tenant).qs()
        if self.request.query_params.get("status") == "delayed":
            delayed_ids = delayed_shipments(self.request.user.tenant).values_list("id", flat=True)
            return qs.filter(
                status=Delivery.Status.IN_TRANSIT,
                shipment_id__in=delayed_ids,
            )
        filter_status = self.request.query_params.get("status")
        if filter_status:
            qs = qs.filter(status=sanitize_text(filter_status, max_len=32))
        return qs

    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        delivery = complete_delivery(
            tenant=request.user.tenant,
            delivery_id=pk,
            failed=bool(request.data.get("failed")),
            reason=request.data.get("reason") or "",
        )
        return Response(DeliverySerializer(delivery).data)
