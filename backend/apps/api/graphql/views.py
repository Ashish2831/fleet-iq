from django.views.decorators.csrf import csrf_exempt
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.permissions import AllowAny
from strawberry.django.views import AsyncGraphQLView

from apps.api.graphql.subgraphs import ai_schema, analytics_schema, core_schema, tracking_schema
from config.schema import get_context, schema


class PublicSchemaView(SpectacularAPIView):
    authentication_classes = []
    permission_classes = [AllowAny]


class PublicSwaggerView(SpectacularSwaggerView):
    authentication_classes = []
    permission_classes = [AllowAny]


class FleetIQGraphQLView(AsyncGraphQLView):
    async def get_context(self, request, response):
        return await get_context(request, response)


# Bearer JWT GraphQL — CSRF not used; session cookie forms still protected by middleware.
graphql_view = csrf_exempt(FleetIQGraphQLView.as_view(schema=schema))
core_graphql_view = csrf_exempt(FleetIQGraphQLView.as_view(schema=core_schema))
tracking_graphql_view = csrf_exempt(FleetIQGraphQLView.as_view(schema=tracking_schema))
ai_graphql_view = csrf_exempt(FleetIQGraphQLView.as_view(schema=ai_schema))
analytics_graphql_view = csrf_exempt(FleetIQGraphQLView.as_view(schema=analytics_schema))

