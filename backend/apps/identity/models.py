import uuid

from django.db import models

from apps.common.models import TenantModel, status_constraint


class Tenant(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active"
        SUSPENDED = "suspended"
        TRIAL = "trial"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=80, unique=True)
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "tenants"
        constraints = [status_constraint("status", ("active", "suspended", "trial"), "tenant_status_valid")]

    def __str__(self):
        return self.slug


class User(TenantModel):
    email = models.EmailField()
    full_name = models.CharField(max_length=255)
    hashed_password = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)
    roles = models.ManyToManyField("Role", through="UserRole", related_name="users")

    class Meta:
        db_table = "users"
        constraints = [
            models.UniqueConstraint(fields=["tenant", "email"], name="uq_users_tenant_email")
        ]
        indexes = [models.Index(fields=["tenant"], name="idx_users_tenant")]

    def __str__(self):
        return self.email

    @property
    def is_authenticated(self):
        return True

    @property
    def is_anonymous(self):
        return False

    def role_names(self) -> list[str]:
        return list(self.roles.values_list("name", flat=True))

    def permission_codenames(self) -> list[str]:
        return list(
            Permission.objects.filter(roles__users=self).distinct().values_list("codename", flat=True)
        )


class Permission(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    codename = models.CharField(max_length=128, unique=True)
    description = models.TextField(blank=True)

    class Meta:
        db_table = "permissions"

    def __str__(self):
        return self.codename


class Role(TenantModel):
    name = models.CharField(max_length=64)
    permissions = models.ManyToManyField(
        Permission, through="RolePermission", related_name="roles"
    )

    class Meta:
        db_table = "roles"
        constraints = [
            models.UniqueConstraint(fields=["tenant", "name"], name="uq_roles_tenant_name")
        ]


class RolePermission(models.Model):
    role = models.ForeignKey(Role, on_delete=models.CASCADE)
    permission = models.ForeignKey(Permission, on_delete=models.CASCADE)

    class Meta:
        db_table = "role_permissions"
        constraints = [
            models.UniqueConstraint(fields=["role", "permission"], name="uq_role_permission")
        ]


class UserRole(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    role = models.ForeignKey(Role, on_delete=models.CASCADE)

    class Meta:
        db_table = "user_roles"
        constraints = [
            models.UniqueConstraint(fields=["user", "role"], name="uq_user_role")
        ]
