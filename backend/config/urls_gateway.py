from django.http import JsonResponse
from django.urls import path

from apps.api.gateway_views import graphql_gateway


def health(_request):
    return JsonResponse({"status": "ok", "phase": "I", "role": "gateway"})


urlpatterns = [
    path("health", health),
    path("graphql", graphql_gateway),
]
