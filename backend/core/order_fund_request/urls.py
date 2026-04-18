from __future__ import annotations

"""URL routes for the order fund request business module."""

from django.urls import path

from .views import (
    FundRequestAidOptionsView,
    FundRequestCreateView,
    FundRequestDeleteView,
    FundRequestDetailView,
    FundRequestDocumentUploadView,
    FundRequestListView,
    FundRequestPDFView,
    FundRequestReopenView,
    FundRequestSubmitView,
    FundRequestUpdateView,
)

urlpatterns = [
    path("fund-requests/", FundRequestListView.as_view(), name="fund-request-list"),
    path("fund-requests/new/", FundRequestCreateView.as_view(), name="fund-request-create"),
    path("fund-requests/aid-options/", FundRequestAidOptionsView.as_view(), name="fund-request-aid-options"),
    path("fund-requests/<int:pk>/", FundRequestDetailView.as_view(), name="fund-request-detail"),
    path("fund-requests/<int:pk>/edit/", FundRequestUpdateView.as_view(), name="fund-request-edit"),
    path("fund-requests/<int:pk>/pdf/", FundRequestPDFView.as_view(), name="fund-request-pdf"),
    path("fund-requests/<int:pk>/delete/", FundRequestDeleteView.as_view(), name="fund-request-delete"),
    path("fund-requests/<int:pk>/submit/", FundRequestSubmitView.as_view(), name="fund-request-submit"),
    path("fund-requests/<int:pk>/reopen/", FundRequestReopenView.as_view(), name="fund-request-reopen"),
    path("fund-requests/<int:pk>/documents/new/", FundRequestDocumentUploadView.as_view(), name="fund-request-upload"),
]

