import json
import logging

import pytest
from rest_framework.test import APIRequestFactory

from apps.common.logging import JsonFormatter, RequestContextFilter
from apps.common.pagination import StandardLimitOffsetPagination
from apps.common.repositories import (
    AddressRepository,
    CustomerRepository,
    OrderRepository,
    TenantRepository,
    WarehouseRepository,
)
from apps.common.sanitize import sanitize_errors, sanitize_text
from apps.common.utils import as_uuid, chunked, parse_bool, slugify
from apps.orders.services import create_order


@pytest.fixture
def tenants(db):
    a = TenantRepository().create(name="Acme", slug="acme-bp")
    b = TenantRepository().create(name="Beta", slug="beta-bp")
    return a, b


def test_sanitize_strips_html_and_scripts():
    dirty = '<script>alert(1)</script>Hello <b>world</b> javascript:void(0)'
    clean = sanitize_text(dirty, max_len=200)
    assert "<" not in clean
    assert "Hello" in clean
    assert "world" in clean
    assert "javascript:" not in clean.lower()


def test_sanitize_errors_hides_internals_when_not_debug():
    assert "unexpected" in sanitize_errors("OperationalError: connection refused", debug=False).lower()
    assert "OperationalError" in sanitize_errors("OperationalError: connection refused", debug=True)


def test_utils_helpers():
    assert parse_bool("yes") is True
    assert parse_bool("0") is False
    assert as_uuid("not-a-uuid") is None
    assert slugify("Hello World!!") == "hello-world"
    assert list(chunked([1, 2, 3, 4, 5], 2)) == [[1, 2], [3, 4], [5]]


def test_json_formatter_includes_request_id():
    record = logging.LogRecord(
        name="apps.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hello",
        args=(),
        exc_info=None,
    )
    record.request_id = "req-1"
    out = json.loads(JsonFormatter().format(record))
    assert out["message"] == "hello"
    assert out["request_id"] == "req-1"


def test_request_context_filter_from_correlation():
    from apps.events.context import set_correlation_id

    set_correlation_id("corr-42")
    record = logging.LogRecord("apps.test", logging.INFO, __file__, 1, "x", (), None)
    assert RequestContextFilter().filter(record) is True
    assert record.request_id == "corr-42"


@pytest.mark.django_db
def test_order_repository_and_sanitized_create(tenants):
    tenant = tenants[0]
    addr = AddressRepository(tenant).create(
        line1="1 Main", city="BLR", state="KA", postal_code="560001", lat=12.9, lng=77.6
    )
    customer = CustomerRepository(tenant).create(name="Acme", email="a@x.com")
    warehouse = WarehouseRepository(tenant).create(code="W1", name="WH", address=addr)
    order = create_order(
        tenant=tenant,
        customer=customer,
        warehouse=warehouse,
        order_number='ORD-<b>1</b>',
        notes='Safe <script>x</script> note',
        items=[{"sku": "SKU1", "description": "<i>box</i>", "quantity": 1, "weight_kg": 2}],
    )
    assert "<" not in order.order_number
    assert "<" not in order.notes
    assert "script" not in order.notes.lower()
    repo = OrderRepository(tenant)
    assert repo.get(order.id) is not None
    assert repo.by_number(order.order_number).id == order.id


def test_pagination_envelope_keys():
    paginator = StandardLimitOffsetPagination()
    factory = APIRequestFactory()
    request = factory.get("/api/v1/orders/?limit=10&offset=0")
    # DRF pagination needs a request with query params via paginator.paginate_queryset
    from rest_framework.request import Request

    drf_request = Request(request)
    qs = list(range(3))

    class _QS(list):
        def count(self):
            return len(self)

    page = paginator.paginate_queryset(_QS(qs), drf_request)
    response = paginator.get_paginated_response(page)
    assert set(response.data.keys()) >= {"count", "next", "previous", "limit", "offset", "results"}
