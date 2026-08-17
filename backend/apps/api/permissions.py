from rest_framework.permissions import SAFE_METHODS, BasePermission

WRITE_ROLES = {"owner", "ops_manager", "dispatcher"}
READ_ROLES = WRITE_ROLES | {"viewer", "driver"}
ASSIGN_PERMS = {"fleet.vehicle.assign", "dispatch.route.assign"}


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
        return bool(_roles(request.user) & READ_ROLES)


class CanWriteOps(BasePermission):
    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return bool(_roles(request.user) & READ_ROLES)
        return bool(_roles(request.user) & WRITE_ROLES)


class CanAssign(BasePermission):
    def has_permission(self, request, view):
        roles = _roles(request.user)
        if roles & {"owner", "ops_manager", "dispatcher"}:
            return True
        return bool(_perms(request.user) & ASSIGN_PERMS)
