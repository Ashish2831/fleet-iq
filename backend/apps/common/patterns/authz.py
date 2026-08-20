"""Authorization strategies — Role / permission checks (DIP for permissions)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class AuthorizationStrategy(ABC):
    @abstractmethod
    def allows(self, user: Any, *, action: str = "read") -> bool:
        ...


class RoleBasedAuthorizationStrategy(AuthorizationStrategy):
    def __init__(self, allowed_roles: set[str]):
        self.allowed_roles = allowed_roles

    def allows(self, user: Any, *, action: str = "read") -> bool:
        cached = getattr(user, "_token_roles", None)
        roles = set(cached) if cached is not None else set(user.role_names())
        return bool(roles & self.allowed_roles)


class PermissionAuthorizationStrategy(AuthorizationStrategy):
    def __init__(self, allowed_perms: set[str]):
        self.allowed_perms = allowed_perms

    def allows(self, user: Any, *, action: str = "read") -> bool:
        cached = getattr(user, "_token_perms", None)
        perms = set(cached) if cached is not None else set(user.permission_codenames())
        return bool(perms & self.allowed_perms)


class AnyOfAuthorizationStrategy(AuthorizationStrategy):
    def __init__(self, *strategies: AuthorizationStrategy):
        self.strategies = strategies

    def allows(self, user: Any, *, action: str = "read") -> bool:
        return any(s.allows(user, action=action) for s in self.strategies)
