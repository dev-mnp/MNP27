from __future__ import annotations

"""URL routes for the dashboard business module."""

from django.urls import path

from .views import DashboardView

urlpatterns = [
    path("", DashboardView.as_view(), name="landing"),
    path("dashboard/", DashboardView.as_view(), name="dashboard"),
]
