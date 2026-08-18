from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from apps.api.authentication import user_from_access
from apps.common.errors import Unauthorized
from apps.tracking.services import snapshot_for_tenant


class FleetConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        user = self.scope.get("user")
        tenant = self.scope.get("tenant")
        if user and tenant:
            await self._join(tenant)
            sub = self.scope.get("ws_subprotocol")
            await self.accept(subprotocol=sub) if sub else await self.accept()
            await self._send_snapshot(tenant)
            return
        # Prefer first-message auth over query tokens when the handshake had none.
        self._pending_auth = True
        await self.accept()

    async def disconnect(self, code):
        if getattr(self, "group", None):
            await self.channel_layer.group_discard(self.group, self.channel_name)

    async def receive_json(self, content, **kwargs):
        if getattr(self, "_pending_auth", False):
            token = content.get("token") if content.get("type") == "auth" else None
            if not token:
                await self.close(code=4401)
                return
            try:
                user = await database_sync_to_async(user_from_access)(token)
            except Unauthorized:
                await self.close(code=4401)
                return
            self._pending_auth = False
            self.scope["user"] = user
            self.scope["tenant"] = user.tenant
            await self._join(user.tenant)
            await self._send_snapshot(user.tenant)
            return
        if content.get("type") == "ping":
            await self.send_json({"type": "pong"})

    async def fleet_update(self, event):
        await self.send_json(event["payload"])

    async def _join(self, tenant):
        # Group is always derived from JWT tenant — never from a client payload.
        self.group = f"tenant.{tenant.id}.fleet"
        await self.channel_layer.group_add(self.group, self.channel_name)

    async def _send_snapshot(self, tenant):
        snap = await database_sync_to_async(snapshot_for_tenant)(tenant)
        await self.send_json({"type": "snapshot", **snap})
