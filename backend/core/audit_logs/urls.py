from __future__ import annotations

"""Route map for audit log pages."""

from django.urls import path

from .views import ApplicationAuditLogListView

urlpatterns = [
    path("applications/audit-logs/", ApplicationAuditLogListView.as_view(), name="application-audit-logs"),
]
