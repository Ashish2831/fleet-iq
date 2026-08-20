import pytest
from django.contrib.auth.hashers import make_password
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.api.rest.batch import _allowed, _normalize_path, batch
from apps.common.errors import BadRequest
from apps.common.repositories import RoleRepository, TenantRepository, UserRoleRepository
from helpers import users


def test_batch_path_guards():
    assert _allowed("/api/v1/me")
    assert _allowed("/api/v1/orders/?status=created")
    assert not _allowed("/api/v1/batch")
    assert not _allowed("/api/v1/auth/login")
    with pytest.raises(BadRequest):
        _normalize_path("https://evil.example/api/v1/me")


@pytest.fixture
def tenants(db):
    a = TenantRepository().create(name="Acme", slug="acme-batch")
    b = TenantRepository().create(name="Beta", slug="beta-batch")
    return a, b


@pytest.mark.django_db
def test_batch_get_me(tenants):
    tenant = tenants[0]
    user = users(tenant).create(
        email="batch@acme.test",
        full_name="Batch User",
        hashed_password=make_password("x"),
        is_active=True,
    )
    role = RoleRepository(tenant).create(name="ops_manager")
    UserRoleRepository(tenant).create(user=user, role=role)
    user._token_roles = ["ops_manager"]
    user._token_perms = []

    factory = APIRequestFactory()
    req = factory.post(
        "/api/v1/batch",
        {
            "requests": [
                {"id": "me", "path": "/api/v1/me", "method": "GET"},
                {"id": "bad", "path": "/api/v1/batch", "method": "GET"},
                {"id": "post", "path": "/api/v1/me", "method": "POST"},
            ]
        },
        format="json",
    )
    force_authenticate(req, user=user)
    req.tenant = tenant
    response = batch(req)
    assert response.status_code == 200
    by_id = {r["id"]: r for r in response.data["responses"]}
    assert by_id["me"]["success"] is True
    assert by_id["me"]["data"]["email"] == "batch@acme.test"
    assert by_id["bad"]["success"] is False
    assert by_id["post"]["success"] is False
