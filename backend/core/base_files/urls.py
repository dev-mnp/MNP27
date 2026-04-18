from __future__ import annotations

"""Route map for base-files pages."""

from django.urls import path

from .views import (
    AidRecipientTemplateDownloadView,
    MasterDataArticleView,
    MasterDataDistrictView,
    MasterDataHistoryView,
)

urlpatterns = [
    path("master-data/districts/", MasterDataDistrictView.as_view(), name="master-data-districts"),
    path("master-data/articles/", MasterDataArticleView.as_view(), name="master-data-articles"),
    path("master-data/history/", MasterDataHistoryView.as_view(), name="master-data-history"),
    path("master-data/templates/aid-recipients/", AidRecipientTemplateDownloadView.as_view(), name="aid-recipient-template"),
]
