from datetime import datetime, timedelta, timezone

import jwt
from django.conf import settings

from apps.common.errors import Unauthorized


def _encode(payload: dict, ttl: timedelta) -> str:
    now = datetime.now(timezone.utc)
    payload = {**payload, "iat": now, "exp": now + ttl}
    return jwt.encode(
        payload,
        settings.JWT_SECRET,
        algorithm="HS256",
        headers={"kid": getattr(settings, "JWT_KID", "fleetiq-hs256")},
    )


def access_token(user) -> str:
    return _encode(
        {
            "sub": str(user.id),
            "tid": str(user.tenant_id),
            "typ": "access",
            "roles": user.role_names(),
            "perms": user.permission_codenames(),
        },
        timedelta(minutes=settings.JWT_ACCESS_MINUTES),
    )


def refresh_token(user) -> str:
    return _encode(
        {"sub": str(user.id), "tid": str(user.tenant_id), "typ": "refresh"},
        timedelta(days=settings.JWT_REFRESH_DAYS),
    )


def decode(token: str, expected_typ: str) -> dict:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise Unauthorized("Invalid token") from exc
    if payload.get("typ") != expected_typ:
        raise Unauthorized("Wrong token type")
    return payload
