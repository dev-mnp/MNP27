from __future__ import annotations

"""Shared role-based mixins used by multiple server-rendered UI modules."""

from django.contrib.auth.mixins import UserPassesTestMixin

from core import models


class RoleRequiredMixin(UserPassesTestMixin):
    """Base role and module-permission guard for authenticated UI views."""

    allowed_roles = {"admin", "editor", "viewer"}
    module_key = None
    permission_action = "view"

    def test_func(self):
        user = self.request.user
        if not (user and user.is_authenticated and user.status == models.StatusChoices.ACTIVE):
            return False
        if self.module_key:
            return user.has_module_permission(self.module_key, self.permission_action)
        return user.role in self.allowed_roles


class WriteRoleMixin(RoleRequiredMixin):
    """Shared write-permission guard for edit/create/delete operations."""

    allowed_roles = {"admin", "editor"}



class AdminRequiredMixin(RoleRequiredMixin):
    """Shared admin-only guard for sensitive operations."""

    allowed_roles = {"admin"}
