from rest_framework import serializers

from apps.catalog.models import Address, Customer, Warehouse
from apps.fleet.models import Driver, Vehicle
from apps.identity.models import User
from apps.orders.models import Order, OrderItem
from apps.routing.models import Route, RouteAssignment, RouteStop
from apps.shipments.models import Delivery, Shipment


class AddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = Address
        fields = ("id", "line1", "city", "state", "postal_code", "lat", "lng")


class MeSerializer(serializers.ModelSerializer):
    tenant_slug = serializers.CharField(source="tenant.slug")
    roles = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ("id", "email", "full_name", "tenant_slug", "roles")

    def get_roles(self, obj):
        return getattr(obj, "_token_roles", None) or obj.role_names()


class DriverSerializer(serializers.ModelSerializer):
    class Meta:
        model = Driver
        fields = (
            "id",
            "employee_code",
            "full_name",
            "phone",
            "skills",
            "status",
            "rating",
            "home_lat",
            "home_lng",
        )
        read_only_fields = ("id",)


class VehicleSerializer(serializers.ModelSerializer):
    vehicle_type_name = serializers.CharField(source="vehicle_type.name", read_only=True)

    class Meta:
        model = Vehicle
        fields = (
            "id",
            "plate_number",
            "make",
            "model",
            "status",
            "vehicle_type",
            "vehicle_type_name",
            "metadata",
            "current_odometer_km",
        )
        read_only_fields = ("id", "vehicle_type_name")


class WarehouseSerializer(serializers.ModelSerializer):
    address = AddressSerializer(read_only=True)
    address_id = serializers.UUIDField(write_only=True)

    class Meta:
        model = Warehouse
        fields = ("id", "code", "name", "status", "address", "address_id")
        read_only_fields = ("id", "address")


class CustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = ("id", "name", "email", "phone")
        read_only_fields = ("id",)


class OrderItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderItem
        fields = ("id", "sku", "description", "quantity", "weight_kg")
        read_only_fields = ("id",)


class OrderItemWriteSerializer(serializers.Serializer):
    sku = serializers.CharField()
    description = serializers.CharField(required=False, allow_blank=True, default="")
    quantity = serializers.DecimalField(max_digits=12, decimal_places=3)
    weight_kg = serializers.DecimalField(max_digits=10, decimal_places=3)
    temperature_min = serializers.DecimalField(max_digits=5, decimal_places=2, required=False)
    temperature_max = serializers.DecimalField(max_digits=5, decimal_places=2, required=False)


class OrderWriteSerializer(serializers.Serializer):
    customer_id = serializers.UUIDField()
    warehouse_id = serializers.UUIDField()
    order_number = serializers.CharField()
    deadline_at = serializers.DateTimeField(required=False)
    notes = serializers.CharField(required=False, allow_blank=True, default="")
    items = OrderItemWriteSerializer(many=True)


class OrderReadSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    warehouse_code = serializers.CharField(source="warehouse.code", read_only=True)
    items = OrderItemSerializer(many=True, read_only=True)

    class Meta:
        model = Order
        fields = (
            "id",
            "order_number",
            "status",
            "priority",
            "deadline_at",
            "total_weight_kg",
            "notes",
            "customer",
            "customer_name",
            "warehouse",
            "warehouse_code",
            "items",
            "created_at",
        )


class ShipmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Shipment
        fields = (
            "id",
            "shipment_number",
            "status",
            "warehouse",
            "delivery_address",
            "total_weight_kg",
            "promised_at",
        )
        read_only_fields = ("id",)


class RouteStopSerializer(serializers.ModelSerializer):
    class Meta:
        model = RouteStop
        fields = ("id", "sequence", "stop_type", "status", "planned_arrival", "shipment")


class RouteSerializer(serializers.ModelSerializer):
    driver_name = serializers.CharField(source="assignment.driver.full_name", read_only=True, default=None)
    vehicle_plate = serializers.CharField(source="assignment.vehicle.plate_number", read_only=True, default=None)
    stops = RouteStopSerializer(many=True, read_only=True)

    class Meta:
        model = Route
        fields = (
            "id",
            "route_number",
            "status",
            "planned_date",
            "driver_name",
            "vehicle_plate",
            "stops",
        )


class AssignRouteSerializer(serializers.Serializer):
    driver_id = serializers.UUIDField()
    vehicle_id = serializers.UUIDField()


class DeliverySerializer(serializers.ModelSerializer):
    shipment_number = serializers.CharField(source="shipment.shipment_number", read_only=True)
    promised_at = serializers.DateTimeField(source="shipment.promised_at", read_only=True)

    class Meta:
        model = Delivery
        fields = ("id", "status", "shipment", "shipment_number", "promised_at", "failure_reason")
