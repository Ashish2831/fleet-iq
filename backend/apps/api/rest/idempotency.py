import hashlib

from django.core.serializers.json import DjangoJSONEncoder
import json

from rest_framework.response import Response

from apps.common.errors import Conflict
from apps.common.repositories import IdempotencyKeyRepository


def _jsonable(data):
    return json.loads(json.dumps(data, cls=DjangoJSONEncoder))


def idempotent_post(request, handler):
    key = request.headers.get("Idempotency-Key")
    if not key:
        return handler()
    digest = hashlib.sha256(request.body or b"").hexdigest()
    keys = IdempotencyKeyRepository(request.user.tenant)
    existing = keys.by_key(key)
    if existing:
        if existing.request_hash != digest:
            raise Conflict("Idempotency-Key reused with a different body")
        return Response(existing.response_body, status=existing.response_code)
    response = handler()
    if 200 <= response.status_code < 300:
        keys.create(
            key=key,
            method=request.method,
            path=request.path,
            request_hash=digest,
            response_code=response.status_code,
            response_body=_jsonable(response.data),
        )
    return response
