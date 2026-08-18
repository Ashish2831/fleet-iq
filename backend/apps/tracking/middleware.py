from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware

from apps.api.authentication import user_from_access
from apps.common.errors import Unauthorized


class JwtAuthMiddleware(BaseMiddleware):
    async def __call__(self, scope, receive, send):
        token = _token_from_scope(scope)
        user = None
        if token:
            try:
                user = await database_sync_to_async(user_from_access)(token)
            except Unauthorized:
                user = None
        scope["user"] = user
        scope["tenant"] = getattr(user, "tenant", None)
        scope["ws_subprotocol"] = "bearer" if _used_subprotocol(scope) else None
        return await super().__call__(scope, receive, send)


def _used_subprotocol(scope) -> bool:
    headers = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
    sub = headers.get("sec-websocket-protocol", "")
    parts = [p.strip() for p in sub.split(",") if p.strip()]
    return bool(parts and parts[0].lower() == "bearer")


def _token_from_scope(scope) -> str | None:
    headers = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
    sub = headers.get("sec-websocket-protocol", "")
    parts = [p.strip() for p in sub.split(",") if p.strip()]
    if len(parts) >= 2 and parts[0].lower() == "bearer":
        return parts[1]
    qs = parse_qs(scope.get("query_string", b"").decode())
    if qs.get("token"):
        return qs["token"][0]
    return None
