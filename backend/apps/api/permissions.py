from rest_framework.permissions import SAFE_METHODS, BasePermission

from apps.common.patterns.authz import (
    AnyOfAuthorizationStrategy,
    PermissionAuthorizationStrategy,
    RoleBasedAuthorizationStrategy,
)

WRITE_ROLES = {"owner", "ops_manager", "dispatcher"}
READ_ROLES = WRITE_ROLES | {"viewer", "driver"}
ASSIGN_PERMS = {"fleet.vehicle.assign", "dispatch.route.assign"}

_read = RoleBasedAuthorizationStrategy(READ_ROLES)
_write = RoleBasedAuthorizationStrategy(WRITE_ROLES)
_assign = AnyOfAuthorizationStrategy(
    RoleBasedAuthorizationStrategy({"owner", "ops_manager", "dispatcher"}),
    PermissionAuthorizationStrategy(ASSIGN_PERMS),
)


def _roles(user) -> set[str]:
    cached = getattr(user, "_token_roles", None)
    if cached is not None:
        return set(cached)
    return set(user.role_names())


def _perms(user) -> set[str]:
    cached = getattr(user, "_token_perms", None)
    if cached is not None:
        return set(cached)
    return set(user.permission_codenames())


class IsTenantAuthenticated(BasePermission):
    def has_permission(self, request, view):
        return bool(getattr(request.user, "is_authenticated", False) and getattr(request.user, "tenant_id", None))


class CanReadOps(BasePermission):
    def has_permission(self, request, view):
        return _read.allows(request.user, action="read")


class CanWriteOps(BasePermission):
    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return _read.allows(request.user, action="read")
        return _write.allows(request.user, action="write")


class CanAssign(BasePermission):
    def has_permission(self, request, view):
        return _assign.allows(request.user, action="assign")
