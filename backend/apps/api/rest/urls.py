from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.api.rest import views
from apps.search import views as search_views
from apps.tracking import views as tracking_views

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
    path("tracking/locations", tracking_views.ingest),
    path("tracking/vehicles", tracking_views.vehicles_snapshot),
    path("search/shipments", search_views.search_shipments_view),
    path("search/drivers", search_views.search_drivers_view),
    path("search/knowledge", search_views.search_knowledge_view),
    path("", include(router.urls)),
]
