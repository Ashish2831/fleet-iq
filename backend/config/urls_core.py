from django.http import JsonResponse
from django.urls import include, path

from apps.api.graphql.views import PublicSchemaView, PublicSwaggerView, core_graphql_view
from apps.api.rest.urls import core_urls


def health(_request):
    return JsonResponse({"status": "ok", "phase": "I", "role": "core"})


urlpatterns = [
    path("health", health),
    path("api/v1/", include(core_urls)),
    path("api/v1/schema/", PublicSchemaView.as_view(), name="schema"),
    path("api/v1/docs/", PublicSwaggerView.as_view(url_name="schema")),
    path("graphql", core_graphql_view),
]
