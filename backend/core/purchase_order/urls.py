from __future__ import annotations

"""URL routes for the purchase order business module."""

from django.urls import path

from .views import (
    PurchaseOrderCreateView,
    PurchaseOrderDeleteView,
    PurchaseOrderListView,
    PurchaseOrderPDFView,
    PurchaseOrderReopenView,
    PurchaseOrderSubmitView,
    PurchaseOrderUpdateView,
)

urlpatterns = [
    path("purchase-orders/", PurchaseOrderListView.as_view(), name="purchase-order-list"),
    path("purchase-orders/new/", PurchaseOrderCreateView.as_view(), name="purchase-order-create"),
    path("purchase-orders/<int:pk>/edit/", PurchaseOrderUpdateView.as_view(), name="purchase-order-edit"),
    path("purchase-orders/<int:pk>/pdf/", PurchaseOrderPDFView.as_view(), name="purchase-order-pdf"),
    path("purchase-orders/<int:pk>/submit/", PurchaseOrderSubmitView.as_view(), name="purchase-order-submit"),
    path("purchase-orders/<int:pk>/reopen/", PurchaseOrderReopenView.as_view(), name="purchase-order-reopen"),
    path("purchase-orders/<int:pk>/delete/", PurchaseOrderDeleteView.as_view(), name="purchase-order-delete"),
]

