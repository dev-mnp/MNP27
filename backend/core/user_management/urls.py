from __future__ import annotations

"""Route map for user management pages."""

from django.urls import path

from .views import (
    UserManagementCreateView,
    UserManagementDeleteView,
    UserManagementListView,
    UserManagementPasswordResetView,
    UserManagementUpdateView,
)

urlpatterns = [
    path("users/", UserManagementListView.as_view(), name="user-list"),
    path("users/new/", UserManagementCreateView.as_view(), name="user-create"),
    path("users/<uuid:pk>/edit/", UserManagementUpdateView.as_view(), name="user-edit"),
    path("users/<uuid:pk>/reset-password/", UserManagementPasswordResetView.as_view(), name="user-reset-password"),
    path("users/<uuid:pk>/delete/", UserManagementDeleteView.as_view(), name="user-delete"),
]
