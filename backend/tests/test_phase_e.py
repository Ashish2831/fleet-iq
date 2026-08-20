from datetime import datetime, timedelta, timezone

from rest_framework.test import APIClient

from apps.events.consumers import consume_once
from apps.events.envelopes import envelope
from apps.events.topics import DLQ, LOCATION
from apps.telemetry.queries import downsample_window, vehicle_track
from apps.telemetry.store import get_store
from helpers import acme_tenant, beta_tenant, first_vehicle, login, make_ops_user, seed_bangalore


def _seed():
    seed_bangalore()
    return acme_tenant()


def _gps(vehicle, **overrides):
    body = {
        "vehicle_id": str(vehicle.id),
        "event_id": "evt-e-1",
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "lat": 12.9716,
        "lng": 77.5946,
        "speed_kmh": 22,
        "heading": 80,
    }
    body.update(overrides)
    return body


def _ping(client, vehicle, **overrides):
    token = login(client)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    res = client.post("/api/v1/tracking/locations", _gps(vehicle, **overrides), format="json")
    assert res.status_code == 202, res.content
    return consume_once("fleetiq-location")


def test_location_consumer_writes_history(db, memory_bus, memory_telemetry):
    tenant = _seed()
    vehicle = first_vehicle(tenant)
    client = APIClient()
    result = _ping(client, vehicle, event_id="hist-1", lat=12.97, lng=77.59)
    assert result["ok"] >= 1
    store = get_store()
    assert store.raw_count(tenant_id=tenant.id) == 1
    now = datetime.now(timezone.utc)
    points = vehicle_track(
        tenant_id=tenant.id,
        vehicle_id=vehicle.id,
        start=now - timedelta(hours=1),
        end=now + timedelta(minutes=1),
    )
    assert len(points) == 1
    assert points[0]["lat"] == 12.97


def test_duplicate_event_id_is_skipped(db, memory_bus, memory_telemetry):
    tenant = _seed()
    vehicle = first_vehicle(tenant)
    client = APIClient()
    _ping(client, vehicle, event_id="dup-e", lat=12.97, lng=77.59)
    memory_bus.reset_group("fleetiq-location")
    again = consume_once("fleetiq-location")
    assert again["ok"] >= 1
    assert get_store().raw_count(tenant_id=tenant.id) == 1


def test_rest_track_and_tenant_isolation(db, memory_bus, memory_telemetry):
    tenant = _seed()
    vehicle = first_vehicle(tenant)
    client = APIClient()
    _ping(client, vehicle, event_id="iso-1", lat=12.96, lng=77.60)
    token = login(client)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    now = datetime.now(timezone.utc)
    res = client.get(
        f"/api/v1/vehicles/{vehicle.id}/track/",
        {"from": (now - timedelta(hours=1)).isoformat(), "to": (now + timedelta(minutes=1)).isoformat()},
    )
    assert res.status_code == 200, res.content
    assert len(res.data["points"]) == 1

    wide = client.get(
        f"/api/v1/vehicles/{vehicle.id}/track/",
        {"from": (now - timedelta(hours=7)).isoformat(), "to": now.isoformat(), "source": "raw"},
    )
    assert wide.status_code == 400

    beta = beta_tenant()
    make_ops_user(beta, email="ops@beta.example", full_name="Beta Ops")
    beta_token = login(client, email="ops@beta.example", tenant="beta-freight")
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {beta_token}")
    leak = client.get(f"/api/v1/vehicles/{vehicle.id}/track/")
    assert leak.status_code == 404


def test_graphql_track(db, memory_bus, memory_telemetry):
    tenant = _seed()
    vehicle = first_vehicle(tenant)
    client = APIClient()
    _ping(client, vehicle, event_id="gql-1", lat=12.95, lng=77.61)
    token = login(client)
    now = datetime.now(timezone.utc)
    query = """
      query($id: ID!, $from: DateTime!, $to: DateTime!) {
        vehicle(id: $id) { track(from: $from, to: $to) { lat lng speedKmh } }
      }
    """
    res = client.post(
        "/graphql",
        {
            "query": query,
            "variables": {
                "id": str(vehicle.id),
                "from": (now - timedelta(hours=1)).isoformat(),
                "to": (now + timedelta(minutes=1)).isoformat(),
            },
        },
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )
    body = res.json()
    assert "errors" not in body, body
    pts = body["data"]["vehicle"]["track"]
    assert len(pts) == 1
    assert pts[0]["lat"] == 12.95


def test_downsample_and_expire(db, memory_telemetry):
    tenant = _seed()
    vehicle = first_vehicle(tenant)
    now = datetime.now(timezone.utc)
    store = get_store()
    store.claim_event("old-1")
    store.insert_raw(
        [
            {
                "event_id": "old-1",
                "recorded_at": now - timedelta(minutes=1),
                "meta": {"tenant_id": str(tenant.id), "vehicle_id": str(vehicle.id)},
                "loc": {"type": "Point", "coordinates": [77.59, 12.97]},
                "speed_kmh": 10,
            }
        ]
    )
    n = downsample_window(now - timedelta(minutes=5), now)
    assert n == 1
    minute = store.track(
        tenant_id=str(tenant.id),
        vehicle_id=str(vehicle.id),
        start=now - timedelta(minutes=5),
        end=now,
        source="minute",
    )
    assert len(minute) == 1
    dropped = store.expire_raw(now)
    assert dropped == 1
    assert store.raw_count(tenant_id=tenant.id) == 0


def test_poison_location_goes_to_dlq(db, memory_bus):
    tenant = _seed()
    vehicle = first_vehicle(tenant)
    memory_bus.produce(
        LOCATION,
        str(vehicle.id),
        envelope(
            event_type="VehicleLocationUpdated",
            tenant_id=tenant.id,
            aggregate_type="vehicle",
            aggregate_id=vehicle.id,
            payload={"recorded_at": datetime.now(timezone.utc).isoformat()},
            event_id="poison-gps",
        ),
    )
    result = consume_once("fleetiq-location")
    assert result["dlq"] >= 1
    assert memory_bus.records(DLQ)


def test_ingest_still_202_without_waiting_on_history(db, memory_bus):
    tenant = _seed()
    vehicle = first_vehicle(tenant)
    client = APIClient()
    token = login(client)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    res = client.post("/api/v1/tracking/locations", _gps(vehicle, event_id="live-1"), format="json")
    assert res.status_code == 202
    from apps.tracking import redis_state as rs

    pin = rs.get_redis().hgetall(rs.vehicle_key(tenant, vehicle.id))
    assert pin.get("lat")
