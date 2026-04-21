from __future__ import annotations

"""Route map for base-files pages."""

from django.urls import path

from .views import (
    AidRecipientTemplateDownloadView,
    MasterDataArticleView,
    MasterDataDistrictView,
    MasterDataHistoryView,
    UpdatedPastBeneficiaryExportView,
)

urlpatterns = [
    path("master-data/districts/", MasterDataDistrictView.as_view(), name="master-data-districts"),
    path("master-data/articles/", MasterDataArticleView.as_view(), name="master-data-articles"),
    path("master-data/history/", MasterDataHistoryView.as_view(), name="master-data-history"),
    path(
        "master-data/history/export-updated-past-beneficiaries/",
        UpdatedPastBeneficiaryExportView.as_view(),
        name="master-data-history-export-updated",
    ),
    path("master-data/templates/aid-recipients/", AidRecipientTemplateDownloadView.as_view(), name="aid-recipient-template"),
]
