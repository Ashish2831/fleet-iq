from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.api.rest import views

router = DefaultRouter()
router.register("drivers", views.DriverViewSet, basename="driver")
router.register("vehicles", views.VehicleViewSet, basename="vehicle")
router.register("warehouses", views.WarehouseViewSet, basename="warehouse")
router.register("customers", views.CustomerViewSet, basename="customer")
router.register("orders", views.OrderViewSet, basename="order")
router.register("shipments", views.ShipmentViewSet, basename="shipment")
router.register("routes", views.RouteViewSet, basename="route")
router.register("deliveries", views.DeliveryViewSet, basename="delivery")

urlpatterns = [
    path("health", views.health),
    path("ready", views.ready),
    path("auth/login", views.login),
    path("auth/refresh", views.refresh),
    path("me", views.me),
    path("", include(router.urls)),
]
