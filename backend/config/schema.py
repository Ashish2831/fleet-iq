from dataclasses import dataclass

from asgiref.sync import sync_to_async
from strawberry import Schema

from apps.api.authentication import bearer_from_request, user_from_access
from apps.api.graphql.loaders import Loaders
from apps.api.graphql.schema import Mutation, Query
from apps.common.errors import Unauthorized
from apps.common.patterns.chain import PipelineRequest, RequestIdHandler, TenantBoundHandler, run_chain

schema = Schema(query=Query, mutation=Mutation)


@dataclass
class GraphQLContext:
    request: object
    user: object | None
    tenant: object | None
    loaders: Loaders | None


async def get_context(request, _response=None) -> GraphQLContext:
    token = bearer_from_request(request)
    user = None
    if token:
        try:
            user = await sync_to_async(user_from_access)(token)
        except Unauthorized:
            user = None
    tenant = user.tenant if user else None
    headers = {str(k).lower(): str(v) for k, v in getattr(request, "headers", {}).items()}
    run_chain(
        [RequestIdHandler(), TenantBoundHandler()],
        PipelineRequest(path=getattr(request, "path", "/graphql"), method=getattr(request, "method", "POST"), headers=headers, user=user),
        lambda: None,
    )
    loaders = Loaders(tenant) if tenant else None
    return GraphQLContext(request=request, user=user, tenant=tenant, loaders=loaders)
