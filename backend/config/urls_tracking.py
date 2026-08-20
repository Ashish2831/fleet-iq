from django.http import JsonResponse
from django.urls import include, path

from apps.api.graphql.views import tracking_graphql_view
from apps.api.rest.urls import tracking_urls


def health(_request):
    return JsonResponse({"status": "ok", "phase": "I", "role": "tracking"})


urlpatterns = [
    path("health", health),
    path("api/v1/", include(tracking_urls)),
    path("graphql", tracking_graphql_view),
]
