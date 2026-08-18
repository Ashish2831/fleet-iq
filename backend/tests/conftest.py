import pytest


@pytest.fixture(autouse=True)
def _phase_c_backends(settings):
    settings.CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}
    settings.REST_FRAMEWORK = {
        **settings.REST_FRAMEWORK,
        "DEFAULT_THROTTLE_CLASSES": [],
        "DEFAULT_THROTTLE_RATES": {"anon": "10000/min", "user": "10000/min", "gps": "10000/min"},
    }
    settings.CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.dummy.DummyCache",
            "LOCATION": "fleetiq-tests",
        }
    }
    from channels.layers import channel_layers

    channel_layers.backends = {}
    yield
    channel_layers.backends = {}


@pytest.fixture(autouse=True)
def fake_redis():
    import fakeredis

    from apps.tracking import redis_state as rs

    rs.reset_client()
    client = fakeredis.FakeRedis(decode_responses=True)
    rs._client = client
    yield client
    rs.reset_client()


@pytest.fixture(autouse=True)
def memory_bus(settings):
    settings.KAFKA_ENABLED = False
    from apps.events.bus import reset_bus

    bus = reset_bus()
    yield bus
    reset_bus()


@pytest.fixture(autouse=True)
def memory_telemetry(settings):
    settings.MONGO_ENABLED = False
    from apps.telemetry.store import reset_store

    store = reset_store()
    yield store
    reset_store()
