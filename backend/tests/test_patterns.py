from apps.common.patterns.authz import RoleBasedAuthorizationStrategy
from apps.common.patterns.circuit_breaker import CircuitOpenError, SimpleCircuitBreaker
from apps.common.patterns.factory import ServiceFactory
from apps.common.patterns.observer import DomainEvent, domain_events
from apps.common.patterns.rate_limit import MemoryRateLimitStore, allow_request
from apps.common.patterns.retry import ExponentialBackoffStrategy, FixedRetryStrategy, with_retry


def test_observer_emit_and_clear():
    seen = []
    domain_events.clear()

    def handler(event: DomainEvent):
        seen.append(event.type)

    domain_events.on("OrderCreated", handler)
    domain_events.emit("OrderCreated", {"x": 1}, tenant_id="t1")
    assert seen == ["OrderCreated"]
    domain_events.clear()


def test_retry_eventually_succeeds():
    attempts = {"n": 0}

    def flaky():
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise ValueError("nope")
        return "ok"

    assert with_retry(flaky, strategy=FixedRetryStrategy(attempts=3, delay=0), sleeper=lambda _: None) == "ok"
    assert attempts["n"] == 3


def test_exponential_delays_increase():
    delays = ExponentialBackoffStrategy(attempts=3, base=0.1, factor=2, jitter=0).delays()
    assert delays[0] == 0.1
    assert delays[1] == 0.2
    assert delays[2] == 0.4


def test_circuit_opens_after_threshold():
    breaker = SimpleCircuitBreaker(failure_threshold=2, reset_seconds=60)
    breaker.record_failure()
    assert breaker.allow() is True
    breaker.record_failure()
    assert breaker.allow() is False
    try:
        breaker.call(lambda: 1)
        assert False, "expected CircuitOpenError"
    except CircuitOpenError:
        pass


def test_rate_limit_memory_store():
    store = MemoryRateLimitStore()
    assert allow_request(store, "gps:v1", limit=2, window_seconds=60) is True
    assert allow_request(store, "gps:v1", limit=2, window_seconds=60) is True
    assert allow_request(store, "gps:v1", limit=2, window_seconds=60) is False


def test_authz_role_strategy():
    class U:
        def role_names(self):
            return ["viewer"]

    assert RoleBasedAuthorizationStrategy({"viewer"}).allows(U()) is True
    assert RoleBasedAuthorizationStrategy({"owner"}).allows(U()) is False


def test_service_factory_rate_limit_store():
    store = ServiceFactory.rate_limit_store(prefer_cache=False)
    assert allow_request(store, "k", limit=1, window_seconds=10)


def test_csv_json_export_import_roundtrip():
    from apps.common.patterns.io_formats import get_export_strategy, get_import_strategy

    rows = [{"order_number": "A-1", "status": "created"}, {"order_number": "A-2", "status": "confirmed"}]
    csv_bytes = get_export_strategy("csv").export(rows, fieldnames=["order_number", "status"])
    assert b"order_number" in csv_bytes
    parsed = get_import_strategy("csv").parse(csv_bytes)
    assert parsed[0]["order_number"] == "A-1"
    json_bytes = get_export_strategy("json").export(rows)
    assert get_import_strategy("json").parse(json_bytes)[1]["status"] == "confirmed"


def test_session_memory_roundtrip():
    from apps.common.patterns.session import MemorySessionStorage

    store = MemorySessionStorage()
    sid = store.create({"user_id": "u1"})
    assert store.get(sid)["user_id"] == "u1"
    store.delete(sid)
    assert store.get(sid) is None


def test_validation_strict_and_lenient():
    from apps.common.patterns.validation import LenientValidationStrategy, StrictValidationStrategy, validate_required

    strict = validate_required({"a": ""}, ["a"], StrictValidationStrategy())
    assert strict.ok is False
    lenient = validate_required({"a": ""}, ["a"], LenientValidationStrategy())
    assert lenient.ok is True
    assert lenient.warnings


def test_ttl_cache_decorator():
    from apps.common.patterns.decorator import with_ttl_cache

    n = {"c": 0}

    @with_ttl_cache(ttl_seconds=60)
    def compute():
        n["c"] += 1
        return n["c"]

    assert compute() == 1
    assert compute() == 1


def test_pipeline_chain_requires_bearer():
    from apps.common.patterns.chain import AuthRequiredHandler, PipelineRequest, run_chain

    req = PipelineRequest(path="/graphql", method="POST", headers={})
    try:
        run_chain([AuthRequiredHandler()], req, lambda: "ok")
        assert False, "expected PermissionError"
    except PermissionError:
        pass
    req.headers["Authorization"] = "Bearer x"
    assert run_chain([AuthRequiredHandler()], req, lambda: "ok") == "ok"


def test_fleet_adapters_camel_vs_snake(db):
    from helpers import acme_tenant, first_vehicle, seed_bangalore
    from apps.common.patterns.adapter import GraphQLFleetAdapter, RestFleetAdapter

    seed_bangalore()
    tenant = acme_tenant()
    assert first_vehicle(tenant)
    rest_rows = RestFleetAdapter(tenant).list_vehicles(limit=1)
    gql_rows = GraphQLFleetAdapter(tenant).list_vehicles(limit=1)
    assert "plate_number" in rest_rows[0]
    assert "plateNumber" in gql_rows[0]
