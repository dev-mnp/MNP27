from __future__ import annotations

"""
REST API layer for the Django backend.

These viewsets power the `/api/` routes and should be updated when mobile/web
clients need CRUD or workflow changes outside the server-rendered UI.
"""

from django.db import transaction
from rest_framework import status, viewsets
from rest_framework.views import APIView
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from . import models, serializers, services
from .permissions import IsAdmin, IsAdminOrEditor, ModelRolePermission


class AppUserViewSet(viewsets.ModelViewSet):
    queryset = models.AppUser.objects.all().order_by("-date_joined")
    serializer_class = serializers.AppUserSerializer
    permission_classes = [IsAuthenticated, IsAdmin]
    lookup_field = "id"


class ArticleViewSet(viewsets.ModelViewSet):
    queryset = models.Article.objects.all().order_by("article_name")
    serializer_class = serializers.ArticleSerializer
    permission_classes = [IsAuthenticated, ModelRolePermission]
    filterset_fields = ["is_active", "item_type", "category"]
    search_fields = ["article_name", "category", "master_category", "article_name_tk"]

    def perform_create(self, serializer):
        serializer.save()


class DistrictMasterViewSet(viewsets.ModelViewSet):
    queryset = models.DistrictMaster.objects.all().order_by("district_name")
    serializer_class = serializers.DistrictMasterSerializer
    permission_classes = [IsAuthenticated, ModelRolePermission]


class DistrictBeneficiaryEntryViewSet(viewsets.ModelViewSet):
    queryset = models.DistrictBeneficiaryEntry.objects.select_related("district", "article").order_by("-created_at")
    serializer_class = serializers.DistrictBeneficiaryEntrySerializer
    permission_classes = [IsAuthenticated, ModelRolePermission]
    filterset_fields = ["district", "article", "status", "fund_request"]


class PublicBeneficiaryEntryViewSet(viewsets.ModelViewSet):
    queryset = models.PublicBeneficiaryEntry.objects.select_related("article").order_by("-created_at")
    serializer_class = serializers.PublicBeneficiaryEntrySerializer
    permission_classes = [IsAuthenticated, ModelRolePermission]
    filterset_fields = ["status", "article", "fund_request"]


class InstitutionsBeneficiaryEntryViewSet(viewsets.ModelViewSet):
    queryset = models.InstitutionsBeneficiaryEntry.objects.select_related("article").order_by("-created_at")
    serializer_class = serializers.InstitutionsBeneficiaryEntrySerializer
    permission_classes = [IsAuthenticated, ModelRolePermission]
    filterset_fields = ["institution_type", "status", "article", "fund_request"]


class FundRequestViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, ModelRolePermission]
    filterset_fields = ["fund_request_type", "status", "fund_request_number", "purchase_order_number"]
    search_fields = ["fund_request_number", "aid_type", "notes"]
    queryset = models.FundRequest.objects.prefetch_related("recipients", "articles", "documents").order_by("-created_at")

    def get_serializer_class(self):
        if self.action in {"create", "update", "partial_update"}:
            return serializers.FundRequestWriteSerializer
        return serializers.FundRequestSerializer

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user, fund_request_number=self._ensure_request_number(serializer.validated_data))
        services.sync_fund_request_totals(serializer.instance)

    def _ensure_request_number(self, validated_data):
        if validated_data.get("fund_request_number"):
            return validated_data["fund_request_number"]
        return services.next_fund_request_number()

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.status != models.FundRequestStatusChoices.DRAFT and request.user.role != "admin":
            return Response(
                {"detail": "Only admins can edit a submitted fund request."},
                status=status.HTTP_403_FORBIDDEN,
            )
        return super().update(request, *args, **kwargs)

    def perform_update(self, serializer):
        serializer.save()
        services.sync_fund_request_totals(serializer.instance)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.status != models.FundRequestStatusChoices.DRAFT and request.user.role != "admin":
            return Response(
                {"detail": "Only admins can delete non-draft fund requests."},
                status=status.HTTP_403_FORBIDDEN,
            )
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated, IsAdminOrEditor], url_path="submit")
    @transaction.atomic
    def submit(self, request, pk=None):
        fr = self.get_object()
        if fr.status != models.FundRequestStatusChoices.DRAFT:
            return Response({"detail": "Only draft records can be submitted."}, status=status.HTTP_400_BAD_REQUEST)
        if not fr.fund_request_number:
            fr.fund_request_number = services.next_fund_request_number()
        fr.status = models.FundRequestStatusChoices.SUBMITTED
        fr.save(update_fields=["fund_request_number", "status"])
        services.log_audit(
            user=request.user,
            action_type=models.ActionTypeChoices.STATUS_CHANGE,
            entity_type="fund_request",
            entity_id=str(fr.id),
            details={"status": models.FundRequestStatusChoices.SUBMITTED},
            ip_address=self._client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", ""),
        )
        return Response({"detail": "Fund request submitted.", "id": fr.id, "fund_request_number": fr.fund_request_number})

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated, IsAdminOrEditor], url_path="set-status")
    @transaction.atomic
    def set_status(self, request, pk=None):
        fr = self.get_object()
        target = request.data.get("status")
        allowed = {c.value for c in models.FundRequestStatusChoices}
        if target not in allowed:
            return Response({"detail": "Invalid status."}, status=status.HTTP_400_BAD_REQUEST)
        prev = fr.status
        fr.status = target
        fr.save(update_fields=["status"])
        services.log_audit(
            user=request.user,
            action_type=models.ActionTypeChoices.STATUS_CHANGE,
            entity_type="fund_request",
            entity_id=str(fr.id),
            details={"from": prev, "to": target},
            ip_address=self._client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", ""),
        )
        return Response({"detail": "Fund request status updated", "status": target})

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated, IsAdminOrEditor], url_path="allocate-po")
    def allocate_purchase_order(self, request, pk=None):
        fr = self.get_object()
        if request.user.role not in {"admin", "editor"}:
            return Response({"detail": "Permission denied."}, status=status.HTTP_403_FORBIDDEN)
        if not fr.purchase_order_number:
            fr.purchase_order_number = services.next_purchase_order_number()
            fr.save(update_fields=["purchase_order_number"])
        return Response({"purchase_order_number": fr.purchase_order_number})

    @staticmethod
    def _client_ip(request):
        xff = request.META.get("HTTP_X_FORWARDED_FOR")
        if xff:
            return str(xff.split(",")[0]).strip()
        return request.META.get("REMOTE_ADDR")


class FundRequestRecipientViewSet(viewsets.ModelViewSet):
    queryset = models.FundRequestRecipient.objects.all().order_by("-created_at")
    serializer_class = serializers.FundRequestRecipientSerializer
    permission_classes = [IsAuthenticated, ModelRolePermission]
    filterset_fields = ["fund_request", "beneficiary_type"]


class FundRequestArticleViewSet(viewsets.ModelViewSet):
    queryset = models.FundRequestArticle.objects.select_related("article").order_by("-created_at")
    serializer_class = serializers.FundRequestArticleSerializer
    permission_classes = [IsAuthenticated, ModelRolePermission]
    filterset_fields = ["fund_request", "article"]


class FundRequestDocumentViewSet(viewsets.ModelViewSet):
    queryset = models.FundRequestDocument.objects.select_related("fund_request").order_by("-created_at")
    serializer_class = serializers.FundRequestDocumentSerializer
    permission_classes = [IsAuthenticated, ModelRolePermission]
    filterset_fields = ["fund_request", "document_type"]


class OrderEntryViewSet(viewsets.ModelViewSet):
    queryset = models.OrderEntry.objects.select_related("article", "fund_request").order_by("-created_at")
    serializer_class = serializers.OrderEntrySerializer
    permission_classes = [IsAuthenticated, ModelRolePermission]
    filterset_fields = ["article", "status", "fund_request"]


class PublicBeneficiaryHistoryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = models.PublicBeneficiaryHistory.objects.all().order_by("-created_at")
    serializer_class = serializers.PublicBeneficiaryHistorySerializer
    permission_classes = [IsAuthenticated, IsAdminOrEditor]


class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = models.AuditLog.objects.select_related("user").order_by("-created_at")
    serializer_class = serializers.AuditLogSerializer
    permission_classes = [IsAuthenticated, IsAdminOrEditor]
    filterset_fields = ["action_type", "entity_type", "user"]


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(serializers.AppUserSerializer(request.user).data)
