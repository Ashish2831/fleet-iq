from datetime import datetime, timedelta, timezone

import pytest
import redis
from django.contrib.auth.hashers import make_password
from rest_framework.test import APIClient

from apps.common.errors import Conflict
from apps.common.repositories import RoleRepository, UserRoleRepository
from apps.routing.models import Route
from apps.routing.services import assign_route
from apps.tracking import redis_state as rs
from helpers import (
    acme_tenant,
    beta_tenant,
    drivers,
    first_vehicle,
    login,
    make_ops_user,
    routes,
    seed_bangalore,
    users,
    vehicles,
)


def _seed():
    seed_bangalore()
    tenant = acme_tenant()
    vehicle = (
        vehicles(tenant)
        .tenant_qs()
        .filter(route_assignments__route__status=Route.Status.IN_PROGRESS)
        .first()
    )
    if vehicle is None:
        vehicle = first_vehicle(tenant)
    return tenant, vehicle


def _payload(vehicle, **overrides):
    body = {
        "vehicle_id": str(vehicle.id),
        "event_id": "evt-1",
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "lat": 12.9716,
        "lng": 77.5946,
        "speed_kmh": 32,
        "heading": 90,
    }
    body.update(overrides)
    return body


def test_ingest_writes_redis_hash_and_geo(db, fake_redis):
    tenant, vehicle = _seed()
    client = APIClient()
    token = login(client)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    res = client.post("/api/v1/tracking/locations", _payload(vehicle), format="json")
    assert res.status_code == 202, res.content
    assert res.data["accepted"] is True
    data = fake_redis.hgetall(rs.vehicle_key(tenant, vehicle.id))
    assert float(data["lat"]) == pytest.approx(12.9716)
    assert fake_redis.ttl(rs.vehicle_key(tenant, vehicle.id)) > 0
    assert str(vehicle.id) in fake_redis.smembers(rs.seen_key(tenant))
    assert fake_redis.geopos(rs.geo_key(tenant), str(vehicle.id))[0] is not None


def test_duplicate_event_id_does_not_move_pin(db, fake_redis):
    tenant, vehicle = _seed()
    client = APIClient()
    token = login(client)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    first = _payload(vehicle, event_id="dup-1", lat=12.97, lng=77.59)
    second = _payload(vehicle, event_id="dup-1", lat=13.10, lng=77.80)
    a = client.post("/api/v1/tracking/locations", first, format="json")
    b = client.post("/api/v1/tracking/locations", second, format="json")
    assert a.status_code == 202
    assert b.status_code == 202
    assert b.data["duplicate"] is True
    data = fake_redis.hgetall(rs.vehicle_key(tenant, vehicle.id))
    assert float(data["lat"]) == pytest.approx(12.97)


def test_stale_recorded_at_ignored(db, fake_redis):
    tenant, vehicle = _seed()
    client = APIClient()
    token = login(client)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    now = datetime.now(timezone.utc)
    client.post(
        "/api/v1/tracking/locations",
        _payload(vehicle, event_id="n1", recorded_at=now.isoformat(), lat=12.97),
        format="json",
    )
    res = client.post(
        "/api/v1/tracking/locations",
        _payload(
            vehicle,
            event_id="n2",
            recorded_at=(now - timedelta(seconds=5)).isoformat(),
            lat=13.5,
        ),
        format="json",
    )
    assert res.status_code == 202
    assert res.data.get("ignored") is True
    data = fake_redis.hgetall(rs.vehicle_key(tenant, vehicle.id))
    assert float(data["lat"]) == pytest.approx(12.97)


def test_gps_rate_limit_per_vehicle(db):
    _, vehicle = _seed()
    client = APIClient()
    token = login(client)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    a = client.post("/api/v1/tracking/locations", _payload(vehicle, event_id="r1"), format="json")
    b = client.post("/api/v1/tracking/locations", _payload(vehicle, event_id="r2"), format="json")
    assert a.status_code == 202
    assert b.status_code == 429


def test_ingest_does_not_leak_across_tenants(db):
    _, vehicle = _seed()
    beta = beta_tenant()
    make_ops_user(beta, email="ops@beta.example", full_name="Beta Ops")
    client = APIClient()
    token = login(client, email="ops@beta.example", tenant="beta-freight")
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    res = client.post("/api/v1/tracking/locations", _payload(vehicle), format="json")
    assert res.status_code == 404


def test_driver_cannot_spoof_other_vehicle(db):
    tenant, vehicle = _seed()
    other = vehicles(tenant).tenant_qs().exclude(id=vehicle.id).first()
    driver_user = users(tenant).create(
        email="driver@acme.example",
        full_name="Solo Driver",
        hashed_password=make_password("password"),
    )
    role = RoleRepository(tenant).get_or_none(name="driver")
    UserRoleRepository(tenant).create(user=driver_user, role=role)
    drivers(tenant).create(
        user=driver_user,
        employee_code="DRV-SPOOF",
        full_name="Solo Driver",
    )
    client = APIClient()
    token = login(client, email="driver@acme.example")
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    res = client.post("/api/v1/tracking/locations", _payload(other), format="json")
    assert res.status_code == 403


def test_ingest_redis_down_is_503(db, monkeypatch):
    _, vehicle = _seed()
    client = APIClient()
    token = login(client)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    def boom():
        raise redis.ConnectionError("down")

    monkeypatch.setattr("apps.tracking.redis_state.get_redis", boom)
    res = client.post("/api/v1/tracking/locations", _payload(vehicle), format="json")
    assert res.status_code == 503
    assert res.data["code"] == "UNAVAILABLE"


def test_expired_ttl_surfaces_offline(db, fake_redis):
    tenant, vehicle = _seed()
    client = APIClient()
    token = login(client)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    client.post("/api/v1/tracking/locations", _payload(vehicle), format="json")
    fake_redis.delete(rs.vehicle_key(tenant, vehicle.id))
    snap = client.get("/api/v1/tracking/vehicles")
    assert snap.status_code == 200
    row = next(v for v in snap.data["vehicles"] if v["id"] == str(vehicle.id))
    assert row["status"] == "offline"
    assert snap.data["counts"]["offline"] >= 1


def test_assign_route_lock_conflict(db, fake_redis):
    tenant, _ = _seed()
    route = routes(tenant).qs().get(route_number="RT-101")
    fake_redis.set(rs.route_lock_key(tenant, route.id), "held")
    with pytest.raises(Conflict):
        assign_route(
            tenant=tenant,
            route_id=route.id,
            driver_id=route.assignment.driver_id,
            vehicle_id=route.assignment.vehicle_id,
        )


def test_lock_release_requires_matching_token(db, fake_redis):
    tenant, _ = _seed()
    key = rs.order_lock_key(tenant, "order-1")
    assert rs.acquire(key, "alpha") is True
    rs.release(key, "beta")
    assert fake_redis.get(key) == "alpha"
    rs.release(key, "alpha")
    assert fake_redis.get(key) is None


def test_graphql_live_fields(db):
    tenant, vehicle = _seed()
    client = APIClient()
    token = login(client)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    client.post("/api/v1/tracking/locations", _payload(vehicle, event_id="gql-1"), format="json")
    query = """
      query($id: ID!) {
        dashboard { liveCounts { active delivering delayed offline } }
        vehicle(id: $id) { id live { lat lng status speedKmh } }
      }
    """
    res = client.post(
        "/graphql",
        {"query": query, "variables": {"id": str(vehicle.id)}},
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )
    body = res.json()
    assert "errors" not in body, body
    live = body["data"]["vehicle"]["live"]
    assert live["lat"] == pytest.approx(12.9716)
    assert live["status"] in ("ACTIVE", "DELIVERING", "STOPPED", "DELAYED")
    counts = body["data"]["dashboard"]["liveCounts"]
    assert counts["active"] + counts["delivering"] + counts["offline"] >= 1


def test_simulate_gps_once(db, fake_redis):
    from django.core.management import call_command

    tenant, _ = _seed()
    call_command("simulate_gps", tenant="acme-logistics", once=True)
    assert fake_redis.scard(rs.seen_key(tenant)) >= 1


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_ws_snapshot_and_tenant_room():
    from channels.layers import get_channel_layer
    from channels.testing import WebsocketCommunicator
    from asgiref.sync import sync_to_async

    from config.asgi import application

    tenant, vehicle = await sync_to_async(_seed)()
    client = APIClient()
    acme_token = await sync_to_async(login)(client)
    beta = await sync_to_async(beta_tenant)()
    await sync_to_async(make_ops_user)(beta, email="ops@beta.example", full_name="Beta Ops")
    beta_token = await sync_to_async(login)(client, email="ops@beta.example", tenant="beta-freight")

    acme = WebsocketCommunicator(application, f"/ws/fleet?token={acme_token}")
    beta_ws = WebsocketCommunicator(application, f"/ws/fleet?token={beta_token}")
    ok, _ = await acme.connect()
    assert ok
    ok, _ = await beta_ws.connect()
    assert ok
    snap = await acme.receive_json_from(timeout=2)
    assert snap["type"] == "snapshot"
    beta_snap = await beta_ws.receive_json_from(timeout=2)
    assert beta_snap["type"] == "snapshot"

    layer = get_channel_layer()
    await layer.group_send(
        f"tenant.{tenant.id}.fleet",
        {
            "type": "fleet.update",
            "payload": {"type": "vehicle.updated", "vehicle": {"id": str(vehicle.id), "lat": 1}},
        },
    )
    msg = await acme.receive_json_from(timeout=2)
    assert msg["type"] == "vehicle.updated"
    assert msg["vehicle"]["id"] == str(vehicle.id)
    assert await beta_ws.receive_nothing(timeout=0.3)
    await acme.disconnect()
    await beta_ws.disconnect()
