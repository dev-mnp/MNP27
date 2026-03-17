from __future__ import annotations

from rest_framework.permissions import SAFE_METHODS, BasePermission


class RoleChoices:
    ADMIN = "admin"
    EDITOR = "editor"
    VIEWER = "viewer"


class IsActiveUser(BasePermission):
    message = "Inactive account."

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        return getattr(user, "status", "active") == "active"


class IsAdmin(BasePermission):
    message = "Admin role is required."

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.role == RoleChoices.ADMIN)


class IsAdminOrEditor(BasePermission):
    message = "Admin or editor role is required."

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        return user.role in {RoleChoices.ADMIN, RoleChoices.EDITOR}


class ModelRolePermission(BasePermission):
    """
    Default permission used by all API viewsets.
    - viewers: read only
    - editors: read + create/update, no delete
    - admins: full access
    """

    message = "Permission denied."

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.status != "active":
            return False

        if user.role == RoleChoices.ADMIN:
            return True
        if user.role == RoleChoices.EDITOR and request.method in SAFE_METHODS | {"POST", "PUT", "PATCH"}:
            return True
        if request.method in SAFE_METHODS:
            return True
        return False

    def has_object_permission(self, request, view, obj):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.role == RoleChoices.ADMIN:
            return True
        if user.role == RoleChoices.EDITOR and request.method not in {"DELETE"}:
            return True
        if user.role == RoleChoices.VIEWER:
            return request.method in SAFE_METHODS
        return False

