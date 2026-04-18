from __future__ import annotations

"""Route map for reports workflow."""

from django.urls import path

from .views import ReportsView

urlpatterns = [
    path("reports/", ReportsView.as_view(), name="reports"),
]
