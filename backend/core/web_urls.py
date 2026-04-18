from __future__ import annotations

"""Route map for the server-rendered UI under `/ui/`."""

from django.urls import include, path

app_name = "ui"

urlpatterns = [
    path("", include("core.dashboard.urls")),
    path("", include("core.application_entry.urls")),
    path("", include("core.article_management.urls")),
    path("", include("core.vendors.urls")),
    path("", include("core.inventory_planning.urls")),
    path("", include("core.order_fund_request.urls")),
    path("", include("core.purchase_order.urls")),
    path("", include("core.seat_allocation.urls")),
    path("", include("core.sequence_list.urls")),
    path("", include("core.token_generation.urls")),
    path("", include("core.labels.urls")),
    path("", include("core.reports.urls")),
    path("", include("core.user_guide.urls")),
    path("", include("core.audit_logs.urls")),
    path("", include("core.user_management.urls")),
    path("", include("core.base_files.urls")),
]
