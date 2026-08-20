"""Process-boundary GraphQL subgraphs. Core still ships the combined schema for local all-in-one."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Optional

import strawberry
from asgiref.sync import sync_to_async
from graphql import GraphQLError
from strawberry import Schema

from apps.api.graphql.schema import (
    AiRunType,
    CoreMutation,
    CoreQuery,
    LiveCounts,
    TrackPoint,
    VehicleLive,
    VehicleLiveStatus,
    _ai_run_type,
    _live_status,
    _user,
)
from apps.api.permissions import WRITE_ROLES, _roles
from apps.ai.gateway import start_run
from apps.common.errors import ApiError
from apps.common.repositories import AiRunRepository, VehicleRepository
from apps.common.sanitize import sanitize_text
from apps.events.kpis import tenant_kpis
from apps.telemetry.queries import vehicle_track
from apps.tracking.services import live_for_vehicle, snapshot_for_tenant
from django.utils.dateparse import parse_datetime


@strawberry.type(name="Vehicle")
class TrackingVehicle:
    id: strawberry.ID

    @strawberry.field
    async def live(self, info: strawberry.Info) -> Optional[VehicleLive]:
        def inner():
            data = live_for_vehicle(info.context.tenant, str(self.id))
            if not data:
                return VehicleLive(
                    lat=None,
                    lng=None,
                    speed_kmh=None,
                    heading=None,
                    status=VehicleLiveStatus.OFFLINE,
                    recorded_at=None,
                )
            recorded = data.get("recorded_at")
            dt = parse_datetime(recorded) if recorded else None
            return VehicleLive(
                lat=data.get("lat"),
                lng=data.get("lng"),
                speed_kmh=data.get("speed_kmh") or data.get("speed"),
                heading=data.get("heading"),
                status=_live_status(data.get("status")),
                recorded_at=dt,
            )

        return await sync_to_async(inner)()

    @strawberry.field
    async def track(
        self,
        info: strawberry.Info,
        from_: Annotated[datetime, strawberry.argument(name="from")],
        to: datetime,
        source: str = "raw",
    ) -> list[TrackPoint]:
        _user(info)

        def inner():
            points = vehicle_track(
                tenant_id=info.context.tenant.id,
                vehicle_id=self.id,
                start=from_,
                end=to,
                source=source,
            )
            return [
                TrackPoint(
                    recorded_at=p["recorded_at"],
                    lat=p["lat"],
                    lng=p["lng"],
                    speed_kmh=p["speed_kmh"],
                )
                for p in points
            ]

        return await sync_to_async(inner)()


@strawberry.type
class TrackingQuery:
    @strawberry.field
    async def live_counts(self, info: strawberry.Info) -> LiveCounts:
        _user(info)

        def inner():
            snap = snapshot_for_tenant(info.context.tenant)
            c = snap["counts"]
            return LiveCounts(
                active=c.get("active") or 0,
                delivering=c.get("delivering") or 0,
                delayed=c.get("delayed") or 0,
                offline=c.get("offline") or 0,
            )

        return await sync_to_async(inner)()

    @strawberry.field
    async def vehicle(self, info: strawberry.Info, id: strawberry.ID) -> Optional[TrackingVehicle]:
        user = _user(info)

        def inner():
            row = VehicleRepository(user.tenant).get(id)
            return TrackingVehicle(id=str(row.id)) if row else None

        return await sync_to_async(inner)()


@strawberry.type
class AnalyticsKpis:
    day: str
    sla_yesterday: Optional[float]
    orders_yesterday: int
    deliveries_completed: int


@strawberry.type
class AnalyticsQuery:
    @strawberry.field
    async def analytics_kpis(self, info: strawberry.Info) -> AnalyticsKpis:
        user = _user(info)

        def inner():
            data = tenant_kpis(user.tenant)
            return AnalyticsKpis(
                day=data["day"],
                sla_yesterday=data["sla_yesterday"],
                orders_yesterday=data["orders_yesterday"],
                deliveries_completed=data["deliveries_completed"],
            )

        return await sync_to_async(inner)()


@strawberry.type
class AiSubgraphQuery:
    @strawberry.field
    async def ai_run(self, info: strawberry.Info, id: strawberry.ID) -> Optional[AiRunType]:
        user = _user(info)

        def inner():
            run = AiRunRepository(user.tenant).get(id)
            return _ai_run_type(run) if run else None

        return await sync_to_async(inner)()

    @strawberry.field
    async def ai_runs(self, info: strawberry.Info) -> list[AiRunType]:
        user = _user(info)

        def inner():
            qs = AiRunRepository(user.tenant).recent(limit=50)
            return [_ai_run_type(r) for r in qs]

        return await sync_to_async(inner)()


@strawberry.type
class AiSubgraphMutation:
    @strawberry.mutation
    async def start_ai_run(self, info: strawberry.Info, agent: str, input: str) -> AiRunType:
        def inner():
            user = _user(info)
            if not (_roles(user) & WRITE_ROLES):
                raise GraphQLError("Forbidden", extensions={"code": "FORBIDDEN"})
            try:
                run = start_run(
                    tenant=user.tenant,
                    user=user,
                    agent=sanitize_text(agent, max_len=64),
                    question=sanitize_text(input, max_len=4000),
                )
            except ApiError as exc:
                raise GraphQLError(exc.detail, extensions={"code": exc.code}) from exc
            return _ai_run_type(run)

        return await sync_to_async(inner)()


core_schema = Schema(query=CoreQuery, mutation=CoreMutation)
tracking_schema = Schema(query=TrackingQuery)
analytics_schema = Schema(query=AnalyticsQuery)
ai_schema = Schema(query=AiSubgraphQuery, mutation=AiSubgraphMutation)
