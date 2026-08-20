from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from apps.api import jwt as jwt_mod
from apps.common.errors import Unauthorized
from apps.common.repositories import UserRepository
from apps.identity.models import User


def user_from_access(token: str) -> User:
    payload = jwt_mod.decode(token, "access")
    user = UserRepository.by_id_in_tenant(payload["sub"], payload["tid"])
    if not user:
        raise Unauthorized("User not found")
    user._token_roles = payload.get("roles") or []
    user._token_perms = payload.get("perms") or []
    return user


def bearer_from_request(request) -> str | None:
    header = request.headers.get("Authorization", "")
    if header.startswith("Bearer "):
        return header[7:].strip()
    return request.COOKIES.get("fq_access")


class JWTAuthentication(BaseAuthentication):
    def authenticate(self, request):
        token = bearer_from_request(request)
        if not token:
            return None
        try:
            user = user_from_access(token)
        except Unauthorized as exc:
            raise AuthenticationFailed(exc.detail) from exc
        request.tenant = user.tenant
        return (user, token)
