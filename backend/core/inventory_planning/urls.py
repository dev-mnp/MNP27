from __future__ import annotations

"""URL routes for the inventory planning business module."""

from django.urls import path

from .views import OrderManagementView

urlpatterns = [
    path("order-management/", OrderManagementView.as_view(), name="order-management"),
]

