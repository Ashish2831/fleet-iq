from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import redis
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.utils.dateparse import parse_datetime

from apps.api.permissions import WRITE_ROLES, _roles
from apps.common.errors import Forbidden, NotFound, Unavailable
from apps.common.queries import delayed_shipments, delayed_vehicle_ids
from apps.fleet.models import Driver, Vehicle, VehicleAssignment
from apps.routing.models import Route
from apps.tracking.geo import haversine_m
from apps.tracking import redis_state as rs

logger = logging.getLogger(__name__)


def _parse_ts(value) -> datetime:
    if isinstance(value, datetime):
        dt = value
    else:
        dt = parse_datetime(str(value))
        if dt is None:
            raise ValueError("Invalid recorded_at")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def ingest_location(*, user, payload: dict) -> dict:
    tenant = user.tenant
    vehicle_id = str(payload["vehicle_id"])
    event_id = str(payload["event_id"])
    try:
        recorded_at = _parse_ts(payload["recorded_at"])
        lat = float(payload["lat"])
        lng = float(payload["lng"])
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid location payload") from exc

    now = datetime.now(timezone.utc)
    if recorded_at - now > timedelta(seconds=30):
        raise ValueError("recorded_at is too far in the future")

    vehicle = Vehicle.objects.for_tenant(tenant).filter(id=vehicle_id, deleted_at__isnull=True).first()
    if not vehicle:
        raise NotFound("Vehicle not found")

    roles = _roles(user)
    if roles & WRITE_ROLES:
        pass
    elif "driver" in roles:
        driver = Driver.objects.for_tenant(tenant).filter(user=user).first()
        assigned = (
            VehicleAssignment.objects.filter(vehicle=vehicle, driver=driver, ends_at__isnull=True).exists()
            if driver
            else False
        )
        if not assigned:
            raise Forbidden("Driver is not assigned to this vehicle")
    else:
        raise Forbidden("Not allowed to publish GPS")

    try:
        if rs.event_seen(tenant, event_id):
            return {"accepted": True, "duplicate": True}

        last = rs.last_recorded_at(tenant, vehicle_id)
        if last and recorded_at < last:
            rs.ingest_event_id(tenant, event_id)
            return {"accepted": True, "ignored": True, "reason": "stale"}

        if not rs.rate_limit_gps(tenant, vehicle_id):
            return {"accepted": False, "rate_limited": True}
        if not rs.ingest_event_id(tenant, event_id):
            return {"accepted": True, "duplicate": True}

        assignment = (
            VehicleAssignment.objects.select_related("driver")
            .filter(vehicle=vehicle, ends_at__isnull=True)
            .first()
        )
        route = (
            Route.objects.for_tenant(tenant)
            .filter(assignment__vehicle=vehicle, status=Route.Status.IN_PROGRESS)
            .first()
        )
        speed = float(payload.get("speed_kmh") or 0)
        status = rs.derive_status(speed_kmh=speed, on_route=bool(route))
        live = rs.write_live(
            tenant,
            vehicle_id,
            {
                "lat": lat,
                "lng": lng,
                "speed": speed,
                "heading": payload.get("heading") or "",
                "status": status,
                "recorded_at": recorded_at.isoformat(),
                "driver_id": str(assignment.driver_id) if assignment else "",
                "route_id": str(route.id) if route else "",
                "battery": payload.get("battery") or "",
                "fuel_level": payload.get("fuel_level") or "",
                "plate": vehicle.plate_number,
            },
        )
        _maybe_eta(tenant, route, lat, lng)
        from apps.events.gps import produce_location

        produce_location(
            tenant=tenant,
            vehicle_id=vehicle_id,
            event_id=event_id,
            lat=lat,
            lng=lng,
            speed_kmh=speed,
            heading=payload.get("heading"),
            recorded_at=recorded_at,
            battery=payload.get("battery"),
            fuel_level=payload.get("fuel_level"),
            driver_id=assignment.driver_id if assignment else None,
            route_id=route.id if route else None,
        )
        if rs.should_broadcast(tenant, vehicle_id, lat=lat, lng=lng, status=status):
            _broadcast(tenant, vehicle_id, live, status)
        return {"accepted": True, "duplicate": False, "status": status}
    except redis.RedisError as exc:
        logger.exception("redis ingest failed")
        raise Unavailable("Live tracking store unavailable") from exc


def _maybe_eta(tenant, route, lat, lng):
    if not route:
        return
    remaining = route.stops.exclude(status__in=["completed", "skipped"]).select_related("address")
    metres = 0.0
    cur_lat, cur_lng = lat, lng
    for stop in remaining:
        if stop.address.lat is None or stop.address.lng is None:
            continue
        metres += haversine_m(cur_lat, cur_lng, stop.address.lat, stop.address.lng)
        cur_lat, cur_lng = stop.address.lat, stop.address.lng
        if stop.shipment_id:
            seconds = int((metres / 1000) / 25 * 3600)
            rs.cache_eta(tenant, stop.shipment_id, seconds)


def _broadcast(tenant, vehicle_id, live: dict, status: str):
    snap = snapshot_for_tenant(tenant)
    payload = {
        "type": "vehicle.updated",
        "vehicle": {
            "id": vehicle_id,
            "lat": float(live["lat"]),
            "lng": float(live["lng"]),
            "speed": float(live.get("speed") or 0),
            "heading": float(live["heading"]) if live.get("heading") else None,
            "status": status,
            "recorded_at": live.get("recorded_at"),
            "plate": live.get("plate"),
        },
        "counts": snap["counts"],
    }
    try:
        layer = get_channel_layer()
        if layer is None:
            return
        async_to_sync(layer.group_send)(
            f"tenant.{tenant.id}.fleet",
            {"type": "fleet.update", "payload": payload},
        )
    except Exception:
        logger.exception("channel broadcast dropped")


def snapshot_for_tenant(tenant):
    try:
        delayed_vids = delayed_vehicle_ids(tenant)
        vehicles, counts = rs.snapshot(tenant, delayed_ids=delayed_vids)
        # Delayed tile is Postgres promised_at, not Redis — BFF mix of stores.
        counts["delayed"] = delayed_shipments(tenant).count()
        return {"vehicles": vehicles, "counts": counts}
    except redis.RedisError as exc:
        raise Unavailable("Live tracking store unavailable") from exc


def live_for_vehicle(tenant, vehicle_id: str) -> dict | None:
    try:
        data = rs.get_vehicle_hash(tenant, vehicle_id)
    except redis.RedisError:
        return None
    if not data:
        return {
            "status": "offline",
            "lat": None,
            "lng": None,
            "speed_kmh": None,
            "heading": None,
            "recorded_at": None,
        }
    status = data.get("status") or "active"
    if str(vehicle_id) in delayed_vehicle_ids(tenant):
        status = "delayed"
    return {
        "status": status,
        "lat": float(data["lat"]) if data.get("lat") else None,
        "lng": float(data["lng"]) if data.get("lng") else None,
        "speed_kmh": float(data["speed"]) if data.get("speed") else 0,
        "heading": float(data["heading"]) if data.get("heading") else None,
        "recorded_at": data.get("recorded_at"),
    }
