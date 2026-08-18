from django.http import JsonResponse
from django.urls import include, path

from apps.api.graphql.views import PublicSchemaView, PublicSwaggerView, graphql_view


def health(_request):
    from django.conf import settings as dj_settings

    return JsonResponse({"status": "ok", "phase": "I", "role": getattr(dj_settings, "FLEETIQ_ROLE", "all")})


urlpatterns = [
    path("health", health),
    path("api/v1/", include("apps.api.rest.urls")),
    path("api/v1/schema/", PublicSchemaView.as_view(), name="schema"),
    path("api/v1/docs/", PublicSwaggerView.as_view(url_name="schema")),
    path("graphql", graphql_view),
]
