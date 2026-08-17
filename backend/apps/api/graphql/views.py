from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.permissions import AllowAny
from strawberry.django.views import AsyncGraphQLView

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


graphql_view = FleetIQGraphQLView.as_view(schema=schema)
