from django.contrib.auth.hashers import check_password
from django.db import connection
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle

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
from apps.catalog.models import Address, Customer, Warehouse
from apps.common.errors import NotFound, Unauthorized
from apps.common.queries import delayed_shipments
from apps.fleet.models import Driver, Vehicle
from apps.identity.models import Tenant, User
from apps.orders.models import Order
from apps.orders.services import confirm_order, create_order
from apps.routing.models import Route
from apps.routing.services import assign_route
from apps.shipments.models import Delivery, Shipment
from apps.shipments.services import complete_delivery


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
    return Response({"status": "ok", "phase": "D"})


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
    tenant = Tenant.objects.filter(slug=tenant_slug, status=Tenant.Status.ACTIVE).first()
    user = (
        User.objects.select_related("tenant").filter(tenant=tenant, email=email, is_active=True).first()
        if tenant
        else None
    )
    if not user or not check_password(password, user.hashed_password):
        raise Unauthorized("Invalid credentials")
    access = jwt_mod.access_token(user)
    refresh = jwt_mod.refresh_token(user)
    response = Response({"access": access, "user": MeSerializer(user).data})
    return _set_refresh_cookie(response, refresh)


@api_view(["POST"])
@permission_classes([AllowAny])
def refresh(request):
    token = request.COOKIES.get("fq_refresh") or request.data.get("refresh")
    if not token:
        raise Unauthorized("Missing refresh token")
    payload = jwt_mod.decode(token, "refresh")
    user = User.objects.select_related("tenant").filter(id=payload["sub"], tenant_id=payload["tid"]).first()
    if not user or not user.is_active:
        raise Unauthorized("Invalid refresh token")
    return Response({"access": jwt_mod.access_token(user)})


@api_view(["GET", "PATCH"])
@permission_classes([IsTenantAuthenticated])
def me(request):
    if request.method == "PATCH":
        name = request.data.get("full_name")
        if name:
            request.user.full_name = name
            request.user.save(update_fields=["full_name", "updated_at"])
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
    queryset = Driver.objects.filter(deleted_at__isnull=True)
    serializer_class = DriverSerializer
    filterset_fields = ("status",)


class VehicleViewSet(TenantViewSet):
    queryset = Vehicle.objects.select_related("vehicle_type").filter(deleted_at__isnull=True)
    serializer_class = VehicleSerializer
    filterset_fields = ("status",)


class WarehouseViewSet(TenantViewSet):
    queryset = Warehouse.objects.select_related("address")
    serializer_class = WarehouseSerializer

    def perform_create(self, serializer):
        tenant = self.request.user.tenant
        address = Address.objects.for_tenant(tenant).filter(id=serializer.validated_data.pop("address_id")).first()
        if not address:
            raise NotFound("Address not found")
        serializer.save(tenant=tenant, address=address)


class CustomerViewSet(TenantViewSet):
    queryset = Customer.objects.filter(deleted_at__isnull=True)
    serializer_class = CustomerSerializer
    filterset_fields = ("name",)


class OrderViewSet(TenantViewSet):
    queryset = Order.objects.select_related("customer", "warehouse").prefetch_related("items")
    filterset_fields = ("status",)

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
            customer = Customer.objects.for_tenant(tenant).filter(id=data["customer_id"]).first()
            warehouse = Warehouse.objects.for_tenant(tenant).filter(id=data["warehouse_id"]).first()
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
            out = OrderReadSerializer(
                Order.objects.prefetch_related("items")
                .select_related("customer", "warehouse")
                .get(pk=order.pk)
            )
            return Response(out.data, status=status.HTTP_201_CREATED)

        return idempotent_post(request, handler)

    @action(detail=True, methods=["post"])
    def confirm(self, request, pk=None):
        order = confirm_order(tenant=request.user.tenant, order_id=pk)
        return Response(OrderReadSerializer(order).data)


class ShipmentViewSet(TenantViewSet):
    queryset = Shipment.objects.select_related("warehouse", "delivery_address")
    serializer_class = ShipmentSerializer
    filterset_fields = ("status",)

    def perform_create(self, serializer):
        serializer.save(tenant=self.request.user.tenant)


class RouteViewSet(TenantViewSet):
    queryset = Route.objects.select_related(
        "assignment__driver", "assignment__vehicle"
    ).prefetch_related("stops")
    serializer_class = RouteSerializer
    filterset_fields = ("status",)

    def perform_create(self, serializer):
        serializer.save(tenant=self.request.user.tenant)

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
        route = (
            Route.objects.select_related("assignment__driver", "assignment__vehicle")
            .prefetch_related("stops")
            .get(pk=route.pk)
        )
        return Response(RouteSerializer(route).data)


class DeliveryViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsTenantAuthenticated, CanWriteOps]
    serializer_class = DeliverySerializer
    queryset = Delivery.objects.select_related("shipment")

    def get_queryset(self):
        qs = Delivery.objects.for_tenant(self.request.user.tenant).select_related("shipment")
        if self.request.query_params.get("status") == "delayed":
            delayed_ids = delayed_shipments(self.request.user.tenant).values_list("id", flat=True)
            return qs.filter(
                status=Delivery.Status.IN_TRANSIT,
                shipment_id__in=delayed_ids,
            )
        filter_status = self.request.query_params.get("status")
        if filter_status:
            qs = qs.filter(status=filter_status)
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
