from django.urls import path

from apps.tracking.consumers import FleetConsumer

websocket_urlpatterns = [
    path("ws/fleet", FleetConsumer.as_asgi()),
]
