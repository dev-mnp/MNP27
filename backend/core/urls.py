from __future__ import annotations

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register(r"users", views.AppUserViewSet, basename="users")
router.register(r"articles", views.ArticleViewSet, basename="articles")
router.register(r"district-masters", views.DistrictMasterViewSet, basename="district-masters")
router.register(r"district-beneficiaries", views.DistrictBeneficiaryEntryViewSet, basename="district-beneficiaries")
router.register(r"public-beneficiaries", views.PublicBeneficiaryEntryViewSet, basename="public-beneficiaries")
router.register(r"institutions-beneficiaries", views.InstitutionsBeneficiaryEntryViewSet, basename="institutions-beneficiaries")
router.register(r"fund-requests", views.FundRequestViewSet, basename="fund-requests")
router.register(r"fund-request-recipients", views.FundRequestRecipientViewSet, basename="fund-request-recipients")
router.register(r"fund-request-articles", views.FundRequestArticleViewSet, basename="fund-request-articles")
router.register(r"fund-request-documents", views.FundRequestDocumentViewSet, basename="fund-request-documents")
router.register(r"order-entries", views.OrderEntryViewSet, basename="order-entries")
router.register(r"beneficiary-history", views.PublicBeneficiaryHistoryViewSet, basename="beneficiary-history")
router.register(r"audit-logs", views.AuditLogViewSet, basename="audit-logs")

urlpatterns = [
    path("auth/me/", views.MeView.as_view(), name="auth-me"),
    path("", include(router.urls)),
]
