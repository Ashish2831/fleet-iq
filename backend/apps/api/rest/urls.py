from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.api.jwks import jwks
from apps.api.rest import analytics as analytics_views
from apps.api.rest import batch as batch_views
from apps.api.rest import internal as internal_views
from apps.api.rest import views
from apps.ai import views as ai_views
from apps.dispatch.views import DispatchProposalViewSet, dispatch_propose
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
router.register("dispatch/proposals", DispatchProposalViewSet, basename="dispatch-proposal")

auth_urls = [
    path("health", views.health),
    path("ready", views.ready),
    path("auth/login", views.login),
    path("auth/refresh", views.refresh),
    path("auth/jwks", jwks),
    path("me", views.me),
    path("batch", batch_views.batch),
]

core_urls = auth_urls + [
    path("search/shipments", search_views.search_shipments_view),
    path("search/drivers", search_views.search_drivers_view),
    path("search/knowledge", search_views.search_knowledge_view),
    path("dispatch/orders/<uuid:pk>/propose", dispatch_propose),
    path("internal/vehicles/<uuid:pk>/assignment", internal_views.vehicle_assignment),
    path("", include(router.urls)),
]

tracking_urls = auth_urls + [
    path("tracking/locations", tracking_views.ingest),
    path("tracking/vehicles", tracking_views.vehicles_snapshot),
]

ai_urls = auth_urls + [
    path("ai/runs", ai_views.ai_runs),
    path("ai/runs/<uuid:pk>", ai_views.ai_run_detail),
]

analytics_urls = auth_urls + [
    path("analytics/kpis", analytics_views.kpis),
]

# Monolith (FLEETIQ_ROLE=all): every capability on one process.
urlpatterns = core_urls + [
    path("tracking/locations", tracking_views.ingest),
    path("tracking/vehicles", tracking_views.vehicles_snapshot),
    path("ai/runs", ai_views.ai_runs),
    path("ai/runs/<uuid:pk>", ai_views.ai_run_detail),
    path("analytics/kpis", analytics_views.kpis),
]
