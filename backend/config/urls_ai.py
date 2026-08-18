from django.http import JsonResponse
from django.urls import include, path

from apps.api.graphql.views import graphql_view
from apps.api.rest.urls import ai_urls


def health(_request):
    return JsonResponse({"status": "ok", "phase": "I", "role": "ai"})


urlpatterns = [
    path("health", health),
    path("api/v1/", include(ai_urls)),
    path("graphql", graphql_view),
]
