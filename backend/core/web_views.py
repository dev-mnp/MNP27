from __future__ import annotations

import csv
import uuid
import io
import os
import mimetypes
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib import messages
from django.db import transaction
from django.db.models import Q
from django.http import FileResponse, Http404, HttpResponse, HttpResponseRedirect
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    FormView,
    ListView,
    TemplateView,
    UpdateView,
)
from django.shortcuts import get_object_or_404
from django.forms import inlineformset_factory

from . import models
from . import services
from .forms import (
    ArticleForm,
    ApplicationAttachmentUploadForm,
    FundRequestDocumentUploadForm,
    FundRequestForm,
    FundRequestArticleForm,
    FundRequestRecipientForm,
    MasterDataUploadForm,
)

FEMALE_STATUS_DESCRIPTIONS = {
    "Single": "A woman who is unmarried and not currently in a marital relationship.",
    "Married": "A woman who is currently married.",
    "Widowed": "A woman whose spouse has died.",
    "Divorced": "A woman whose marriage has been legally dissolved.",
    "Separated": "A woman living apart from her spouse without a finalized divorce.",
    "Deserted": "A woman abandoned by her spouse without support.",
    "Single Mother": "A woman raising one or more children without a partner in the household.",
    "Destitute Woman (no income/support)": "A woman without stable income, family support, or financial security.",
    "Female Head of Household": "A woman who is the primary decision-maker and provider for the household.",
    "Victim of Domestic Violence": "A woman currently affected by violence or abuse within the home.",
    "Survivor of Abuse": "A woman who has survived physical, emotional, or sexual abuse.",
    "Elderly Woman (60+)": "A woman aged 60 or above, often needing age-related support.",
    "Homeless": "A woman without secure or permanent housing.",
    "Orphan / No Family Support": "A woman with no dependable family support structure.",
    "Migrant Woman": "A woman who has moved for work, safety, marriage, or survival and may lack local support.",
    "Caregiver (children / elderly / disabled)": "A woman responsible for regular care of children, elderly persons, or persons with disabilities.",
    "Employed": "A woman currently working in a salaried or wage-based role.",
    "Self-employed": "A woman earning independently through business, trade, farming, or service work.",
    "Unemployed": "A woman currently without paid work and seeking or needing livelihood support.",
    "Student": "A woman currently pursuing school, college, or vocational education.",
}


class RoleRequiredMixin(UserPassesTestMixin):
    allowed_roles = {"admin", "editor", "viewer"}

    def test_func(self):
        user = self.request.user
        return bool(
            user
            and user.is_authenticated
            and user.status == "active"
            and user.role in self.allowed_roles
        )


class WriteRoleMixin(RoleRequiredMixin):
    allowed_roles = {"admin", "editor"}


class ArticleListView(LoginRequiredMixin, RoleRequiredMixin, ListView):
    model = models.Article
    template_name = "dashboard/article_list.html"
    context_object_name = "articles"
    paginate_by = 20

    def get_queryset(self):
        queryset = models.Article.objects.order_by("article_name")
        if q := self.request.GET.get("q"):
            queryset = queryset.filter(article_name__icontains=q)
        return queryset


class ArticleCreateView(LoginRequiredMixin, WriteRoleMixin, CreateView):
    model = models.Article
    form_class = ArticleForm
    template_name = "dashboard/article_form.html"
    success_url = reverse_lazy("ui:article-list")

    def form_valid(self, form):
        messages.success(self.request, "Article created.")
        return super().form_valid(form)


class ArticleUpdateView(LoginRequiredMixin, WriteRoleMixin, UpdateView):
    model = models.Article
    form_class = ArticleForm
    template_name = "dashboard/article_form.html"
    success_url = reverse_lazy("ui:article-list")

    def form_valid(self, form):
        messages.success(self.request, "Article updated.")
        return super().form_valid(form)


class AdminRequiredMixin(RoleRequiredMixin):
    allowed_roles = {"admin"}


class ArticleDeleteView(LoginRequiredMixin, AdminRequiredMixin, DeleteView):
    model = models.Article
    template_name = "dashboard/article_confirm_delete.html"
    success_url = reverse_lazy("ui:article-list")

    def post(self, request, *args, **kwargs):
        messages.warning(self.request, "Article deleted.")
        return super().post(request, *args, **kwargs)


class MasterEntryView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    template_name = "dashboard/module_master_entry.html"

    def get(self, request, *args, **kwargs):
        export_scope = (request.GET.get("export_scope") or "").strip().lower()
        if export_scope:
            return _export_master_entry_csv(request, export_scope=export_scope)
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        beneficiary_type = self.request.GET.get("type", "district")
        search_query = (self.request.GET.get("q") or "").strip()
        date_from = (self.request.GET.get("date_from") or "").strip()
        date_to = (self.request.GET.get("date_to") or "").strip()
        status_filter = (self.request.GET.get("status") or "").strip().lower()
        sort_by = (self.request.GET.get("sort") or "").strip()
        sort_dir = "asc" if (self.request.GET.get("dir") or "desc").lower() == "asc" else "desc"

        district_groups = _filter_sort_district_summaries(
            _build_district_entry_summaries(),
            search_query=search_query,
            date_from=date_from,
            date_to=date_to,
            status_filter=status_filter,
            sort_by=sort_by,
            sort_dir=sort_dir,
        )
        public_entries = _filter_sort_public_entries(
            models.PublicBeneficiaryEntry.objects.select_related("article").all(),
            search_query=search_query,
            date_from=date_from,
            date_to=date_to,
            status_filter=status_filter,
            sort_by=sort_by,
            sort_dir=sort_dir,
        )
        public_entries = list(public_entries)
        public_attachment_map = _public_attachment_preview_map([entry.id for entry in public_entries])
        for entry in public_entries:
            attachment = public_attachment_map.get(entry.id)
            entry.attachment_id = attachment.id if attachment else None
            entry.attachment_preview_url = reverse("ui:application-attachment-download", kwargs={"attachment_id": attachment.id}) if attachment else ""
            entry.attachment_source = (attachment.file.name or "").lower() if attachment and attachment.file else ""
            entry.attachment_title = _attachment_preview_title(attachment)
        institution_groups = _filter_sort_institution_summaries(
            _build_institution_entry_summaries(),
            search_query=search_query,
            date_from=date_from,
            date_to=date_to,
            status_filter=status_filter,
            sort_by=sort_by,
            sort_dir=sort_dir,
        )

        context["beneficiary_type"] = beneficiary_type
        context["search_query"] = search_query
        context["date_from"] = date_from
        context["date_to"] = date_to
        context["status_filter"] = status_filter
        context["status_choices"] = [
            ("", "All Statuses"),
            (models.BeneficiaryStatusChoices.DRAFT, "Draft"),
            (models.BeneficiaryStatusChoices.SUBMITTED, "Submitted"),
        ]
        context["sort_by"] = sort_by
        context["sort_dir"] = sort_dir
        context["district_groups"] = district_groups
        context["district_count"] = models.DistrictBeneficiaryEntry.objects.values("district_id").distinct().count()
        context["public_count"] = models.PublicBeneficiaryEntry.objects.count()
        context["institution_count"] = models.InstitutionsBeneficiaryEntry.objects.values("application_number").distinct().count()
        context["public_entries"] = public_entries
        context["institution_groups"] = institution_groups
        context["public_total_accrued"] = sum((entry.total_amount or 0) for entry in public_entries)
        context["institution_total_accrued"] = sum((row["total_value"] or 0) for row in institution_groups)
        context["public_submit_popup"] = self.request.session.pop("public_submit_popup", None)
        context["institution_submit_popup"] = self.request.session.pop("institution_submit_popup", None)
        return context


class ApplicationAuditLogListView(LoginRequiredMixin, AdminRequiredMixin, ListView):
    model = models.AuditLog
    template_name = "dashboard/application_audit_logs.html"
    context_object_name = "audit_logs"
    paginate_by = 50

    def get_queryset(self):
        queryset = models.AuditLog.objects.select_related("user").filter(
            entity_type__in=[
                "district_application",
                "public_application",
                "institution_application",
            ]
        ).order_by("-created_at")
        q = (self.request.GET.get("q") or "").strip()
        application_type = (self.request.GET.get("application_type") or "").strip()
        user_id = (self.request.GET.get("user_id") or "").strip()
        date_from = (self.request.GET.get("date_from") or "").strip()
        date_to = (self.request.GET.get("date_to") or "").strip()
        if q:
            queryset = queryset.filter(
                Q(entity_type__icontains=q)
                | Q(entity_id__icontains=q)
                | Q(action_type__icontains=q)
                | Q(user__email__icontains=q)
                | Q(user__first_name__icontains=q)
            )
        if application_type:
            queryset = queryset.filter(entity_type=application_type)
        if user_id:
            queryset = queryset.filter(user_id=user_id)
        if date_from:
            queryset = queryset.filter(created_at__date__gte=date_from)
        if date_to:
            queryset = queryset.filter(created_at__date__lte=date_to)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["search_query"] = (self.request.GET.get("q") or "").strip()
        context["application_type"] = (self.request.GET.get("application_type") or "").strip()
        context["selected_user_id"] = (self.request.GET.get("user_id") or "").strip()
        context["date_from"] = (self.request.GET.get("date_from") or "").strip()
        context["date_to"] = (self.request.GET.get("date_to") or "").strip()
        context["application_type_choices"] = [
            ("district_application", "District Application"),
            ("public_application", "Public Application"),
            ("institution_application", "Institution Application"),
        ]
        context["audit_users"] = (
            models.AppUser.objects.filter(
                audit_logs__entity_type__in=[
                    "district_application",
                    "public_application",
                    "institution_application",
                ]
            )
            .distinct()
            .order_by("first_name", "email")
        )
        context["audit_rows"] = [
            {
                "log": log,
                "application_label": _application_audit_label(log),
                "change_lines": _application_audit_change_lines(log),
                "user_label": _audit_user_label(log.user),
            }
            for log in context["audit_logs"]
        ]
        return context



EXPORT_COLUMNS = [
    "Application Number",
    "Beneficiary Name",
    "Requested Item",
    "Quantity",
    "Cost Per Unit",
    "Total Value",
    "Address",
    "Mobile",
    "Aadhar Number",
    "Handicapped Status",
    "Gender",
    "Gender Category",
    "Beneficiary Type",
    "Item Type",
    "Article Category",
    "Super Category Article",
    "Token Name",
    "Comments",
]


def _request_audit_meta(request):
    return {
        "ip_address": request.META.get("REMOTE_ADDR"),
        "user_agent": request.META.get("HTTP_USER_AGENT", ""),
    }


def _attachment_upload_context(*, attachments=None, enabled=False, upload_url="", helper_text="Attachments can be added after the application is first saved."):
    return {
        "application_attachments": attachments or [],
        "attachment_upload_form": ApplicationAttachmentUploadForm(),
        "attachments_enabled": enabled,
        "attachment_upload_url": upload_url,
        "attachment_helper_text": helper_text,
        "attachment_constraints_text": (
            "Allowed files: PDF, JPG, JPEG, PNG, WEBP, DOC, DOCX, XLS, XLSX, CSV. "
            "Maximum file size: 10 MB. Maximum 2 files per application."
        ),
    }


def _prefixed_attachment_name(application_reference, uploaded_name, custom_name=""):
    prefix = (application_reference or "").strip()
    original_name = (uploaded_name or "").strip()
    chosen_name = (custom_name or "").strip() or original_name or "attachment"
    chosen_root, chosen_ext = os.path.splitext(chosen_name)
    _, original_ext = os.path.splitext(original_name)
    final_name = chosen_name if chosen_ext else f"{chosen_name}{original_ext}"
    if prefix:
        normalized_prefix = f"{prefix}_"
        if final_name.startswith(normalized_prefix):
            return final_name
        return f"{prefix}_{final_name}"
    return final_name


def _district_attachment_context(district):
    has_saved_application = bool(district and models.DistrictBeneficiaryEntry.objects.filter(district=district).exists())
    attachments = []
    upload_url = ""
    if has_saved_application:
        attachments = list(models.ApplicationAttachment.objects.filter(district=district).select_related("uploaded_by").order_by("-created_at"))
        upload_url = reverse("ui:district-attachment-upload", kwargs={"district_id": district.id})
    return _attachment_upload_context(
        attachments=attachments,
        enabled=has_saved_application,
        upload_url=upload_url,
        helper_text="Save the district application first to upload attachments." if not has_saved_application else "Upload files related to this district application. You can rename the file before upload.",
    )


def _public_attachment_context(entry):
    has_saved_application = bool(entry and entry.pk)
    attachments = []
    upload_url = ""
    if has_saved_application:
        attachments = list(models.ApplicationAttachment.objects.filter(public_entry=entry).select_related("uploaded_by").order_by("-created_at"))
        upload_url = reverse("ui:public-attachment-upload", kwargs={"pk": entry.pk})
    context = _attachment_upload_context(
        attachments=attachments,
        enabled=has_saved_application,
        upload_url=upload_url,
        helper_text="Save the public application first to upload attachments." if not has_saved_application else "Upload files related to this public application. You can rename the file before upload.",
    )
    context["entry_id"] = entry.pk if has_saved_application else None
    return context


def _institution_attachment_context(application_number):
    has_saved_application = bool(application_number)
    attachments = []
    upload_url = ""
    if has_saved_application:
        attachments = list(
            models.ApplicationAttachment.objects.filter(
                application_type=models.ApplicationAttachmentTypeChoices.INSTITUTION,
                institution_application_number=application_number,
            ).select_related("uploaded_by").order_by("-created_at")
        )
        upload_url = reverse("ui:institution-attachment-upload", kwargs={"application_number": application_number})
    return _attachment_upload_context(
        attachments=attachments,
        enabled=has_saved_application,
        upload_url=upload_url,
        helper_text="Save the institution application first to upload attachments." if not has_saved_application else "Upload files related to this institution application. You can rename the file before upload.",
    )


def _district_attachment_preview_map(district_ids):
    if not district_ids:
        return {}
    attachments = (
        models.ApplicationAttachment.objects.filter(
            application_type=models.ApplicationAttachmentTypeChoices.DISTRICT,
            district_id__in=district_ids,
        )
        .order_by("district_id", "-created_at", "-id")
    )
    preview_map = {}
    for attachment in attachments:
        if attachment.district_id not in preview_map:
            preview_map[attachment.district_id] = attachment
    return preview_map


def _public_attachment_preview_map(entry_ids):
    if not entry_ids:
        return {}
    attachments = (
        models.ApplicationAttachment.objects.filter(
            application_type=models.ApplicationAttachmentTypeChoices.PUBLIC,
            public_entry_id__in=entry_ids,
        )
        .order_by("public_entry_id", "-created_at", "-id")
    )
    preview_map = {}
    for attachment in attachments:
        if attachment.public_entry_id not in preview_map:
            preview_map[attachment.public_entry_id] = attachment
    return preview_map


def _institution_attachment_preview_map(application_numbers):
    if not application_numbers:
        return {}
    attachments = (
        models.ApplicationAttachment.objects.filter(
            application_type=models.ApplicationAttachmentTypeChoices.INSTITUTION,
            institution_application_number__in=application_numbers,
        )
        .order_by("institution_application_number", "-created_at", "-id")
    )
    preview_map = {}
    for attachment in attachments:
        key = attachment.institution_application_number
        if key and key not in preview_map:
            preview_map[key] = attachment
    return preview_map


def _attachment_preview_title(attachment):
    if not attachment:
        return ""
    if attachment.file_name:
        return attachment.file_name
    if attachment.file:
        return os.path.basename(attachment.file.name)
    return ""


def _district_audit_snapshot(district):
    entries = list(
        models.DistrictBeneficiaryEntry.objects.filter(district=district).select_related("article").order_by("id")
    )
    total_accrued = sum((entry.total_amount or 0) for entry in entries)
    return {
        "district_id": str(district.id),
        "application_number": district.application_number or "",
        "district_name": district.district_name or "",
        "president_name": district.president_name or "",
        "mobile_number": district.mobile_number or "",
        "allotted_budget": str(district.allotted_budget or 0),
        "status": entries[0].status if entries else "",
        "total_accrued": str(total_accrued or 0),
        "item_count": len(entries),
        "items": [
            {
                "id": str(entry.id),
                "article_id": str(entry.article_id),
                "article_name": entry.article.article_name,
                "item_type": entry.article.item_type,
                "quantity": entry.quantity,
                "unit_cost": str(entry.article_cost_per_unit or 0),
                "total_amount": str(entry.total_amount or 0),
                "notes": entry.notes or "",
            }
            for entry in entries
        ],
    }


def _public_audit_snapshot(entry):
    return {
        "id": str(entry.id),
        "application_number": entry.application_number or "",
        "name": entry.name or "",
        "aadhar_number": entry.aadhar_number or "",
        "is_handicapped": bool(entry.is_handicapped),
        "gender": entry.gender or "",
        "female_status": entry.female_status or "",
        "address": entry.address or "",
        "mobile": entry.mobile or "",
        "article_id": str(entry.article_id),
        "article_name": entry.article.article_name,
        "item_type": entry.article.item_type,
        "quantity": entry.quantity,
        "unit_cost": str(entry.article_cost_per_unit or 0),
        "total_amount": str(entry.total_amount or 0),
        "notes": entry.notes or "",
        "status": entry.status or "",
    }


def _institution_audit_snapshot(application_number):
    entries = list(
        models.InstitutionsBeneficiaryEntry.objects.filter(application_number=application_number).select_related("article").order_by("id")
    )
    if not entries:
        return {"application_number": application_number, "item_count": 0, "items": []}
    first = entries[0]
    total_value = sum((entry.total_amount or 0) for entry in entries)
    return {
        "application_number": application_number,
        "institution_name": first.institution_name or "",
        "institution_type": first.institution_type or "",
        "status": first.status or "",
        "address": first.address or "",
        "mobile": first.mobile or "",
        "total_value": str(total_value or 0),
        "item_count": len(entries),
        "items": [
            {
                "id": str(entry.id),
                "article_id": str(entry.article_id),
                "article_name": entry.article.article_name,
                "item_type": entry.article.item_type,
                "quantity": entry.quantity,
                "unit_cost": str(entry.article_cost_per_unit or 0),
                "total_amount": str(entry.total_amount or 0),
                "notes": entry.notes or "",
            }
            for entry in entries
        ],
    }


AUDIT_FIELD_LABELS = {
    "district_name": "District",
    "president_name": "President",
    "mobile_number": "Mobile Number",
    "allotted_budget": "Allotted Budget",
    "name": "Name",
    "aadhar_number": "Aadhaar Number",
    "is_handicapped": "Handicapped",
    "gender": "Gender",
    "female_status": "Gender Category",
    "address": "Address",
    "mobile": "Mobile Number",
    "article_name": "Requested Item",
    "item_type": "Item Type",
    "quantity": "Quantity",
    "unit_cost": "Unit Price",
    "total_amount": "Total Value",
    "notes": "Comments",
    "institution_name": "Institution Name",
    "institution_type": "Institution Type",
    "total_value": "Total Value",
}


def _application_audit_label(log):
    details = log.details or {}
    after = details.get("after") or {}
    before = details.get("before") or {}
    snapshot = after or before
    if log.entity_type == "district_application":
        return snapshot.get("application_number") or snapshot.get("district_name") or log.entity_id or "-"
    if log.entity_type == "public_application":
        application_number = snapshot.get("application_number") or log.entity_id or "-"
        name = snapshot.get("name") or ""
        return f"{application_number} - {name}".strip(" -")
    if log.entity_type == "institution_application":
        application_number = snapshot.get("application_number") or log.entity_id or "-"
        name = snapshot.get("institution_name") or ""
        return f"{application_number} - {name}".strip(" -")
    return log.entity_id or "-"


def _format_audit_value(value):
    if value is None or value == "":
        return "-"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    return str(value)


def _audit_user_label(user):
    if not user:
        return "System"
    if user.first_name:
        return user.first_name
    return user.email


def _audit_item_key(item):
    if item.get("id"):
        return ("id", str(item.get("id")))
    return ("article", item.get("article_id") or "", item.get("article_name") or "")


def _application_audit_change_lines(log):
    details = log.details or {}
    before = details.get("before") or {}
    after = details.get("after") or {}

    if log.action_type == models.ActionTypeChoices.CREATE:
        item_count = after.get("item_count")
        if item_count is not None:
            return [f"Created with {item_count} item(s)."]
        return ["Created application."]

    if log.action_type == models.ActionTypeChoices.DELETE:
        item_count = before.get("item_count")
        if item_count is not None:
            return [f"Deleted application with {item_count} item(s)."]
        return ["Deleted application."]

    change_lines = []
    for key, label in AUDIT_FIELD_LABELS.items():
        if key in {"article_name", "item_type", "quantity", "unit_cost", "total_amount", "notes"}:
            continue
        before_value = before.get(key)
        after_value = after.get(key)
        if before_value != after_value and (before_value is not None or after_value is not None):
            change_lines.append(f"{label}: {_format_audit_value(before_value)} -> {_format_audit_value(after_value)}")

    before_items = before.get("items") or []
    after_items = after.get("items") or []
    before_map = {_audit_item_key(item): item for item in before_items}
    after_map = {_audit_item_key(item): item for item in after_items}

    shared_keys = [key for key in before_map.keys() if key in after_map]
    added = [item for key, item in after_map.items() if key not in before_map]
    removed = [item for key, item in before_map.items() if key not in after_map]

    for key in shared_keys:
        before_item = before_map[key]
        after_item = after_map[key]
        item_changes = []
        for field in ["quantity", "unit_cost", "total_amount", "notes"]:
            if before_item.get(field) != after_item.get(field):
                item_changes.append(
                    f"{AUDIT_FIELD_LABELS[field]}: {_format_audit_value(before_item.get(field))} -> {_format_audit_value(after_item.get(field))}"
                )
        if item_changes:
            change_lines.append(f'{after_item.get("article_name")}: ' + "; ".join(item_changes))

    for item in added:
        change_lines.append(f'Added item: {item.get("article_name")} ({item.get("quantity")} x {_format_audit_value(item.get("unit_cost"))})')
    for item in removed:
        change_lines.append(f'Removed item: {item.get("article_name")}')

    return change_lines or ["No visible field changes recorded."]


def _master_entry_filters_from_request(request):
    return {
        "search_query": (request.GET.get("q") or "").strip(),
        "date_from": (request.GET.get("date_from") or "").strip(),
        "date_to": (request.GET.get("date_to") or "").strip(),
        "status_filter": (request.GET.get("status") or "").strip().lower(),
        "sort_by": (request.GET.get("sort") or "").strip(),
        "sort_dir": "asc" if (request.GET.get("dir") or "desc").lower() == "asc" else "desc",
        "beneficiary_type": (request.GET.get("type") or "district").strip(),
    }


def _decimal_to_csv(value):
    if value is None:
        return ""
    if isinstance(value, Decimal):
        normalized = value.quantize(Decimal("0.01"))
        if normalized == normalized.to_integral():
            return str(int(normalized))
        return format(normalized.normalize(), "f")
    return str(value)


def _district_export_rows(filtered_summaries):
    district_ids = [row["district_id"] for row in filtered_summaries]
    if not district_ids:
        return []
    entries = models.DistrictBeneficiaryEntry.objects.select_related("district", "article").filter(district_id__in=district_ids).order_by("district__application_number", "created_at", "id")
    rows = []
    for entry in entries:
        rows.append({
            "Application Number": entry.district.application_number or entry.application_number or "",
            "Beneficiary Name": entry.district.district_name or "",
            "Requested Item": entry.article.article_name or "",
            "Quantity": str(entry.quantity or 0),
            "Cost Per Unit": _decimal_to_csv(entry.article_cost_per_unit),
            "Total Value": _decimal_to_csv(entry.total_amount),
            "Address": entry.district.district_name or "",
            "Mobile": entry.district.mobile_number or "",
            "Aadhar Number": "",
            "Handicapped Status": "",
            "Gender": "",
            "Gender Category": "",
            "Beneficiary Type": "District",
            "Item Type": entry.article.item_type or "",
            "Article Category": entry.article.category or "",
            "Super Category Article": entry.article.master_category or "",
            "Token Name": entry.article.article_name_tk or "",
            "Comments": entry.notes or "",
        })
    return rows


def _public_export_rows(filtered_entries):
    rows = []
    for entry in filtered_entries:
        rows.append({
            "Application Number": entry.application_number or "",
            "Beneficiary Name": entry.name or "",
            "Requested Item": entry.article.article_name or "",
            "Quantity": str(entry.quantity or 0),
            "Cost Per Unit": _decimal_to_csv(entry.article_cost_per_unit),
            "Total Value": _decimal_to_csv(entry.total_amount),
            "Address": entry.address or "",
            "Mobile": entry.mobile or "",
            "Aadhar Number": entry.aadhar_number or "",
            "Handicapped Status": "Yes" if entry.is_handicapped else "No",
            "Gender": entry.gender or "",
            "Gender Category": entry.female_status or entry.gender or "",
            "Beneficiary Type": "Public",
            "Item Type": entry.article.item_type or "",
            "Article Category": entry.article.category or "",
            "Super Category Article": entry.article.master_category or "",
            "Token Name": entry.article.article_name_tk or "",
            "Comments": entry.notes or "",
        })
    return rows


def _institution_export_rows(filtered_summaries):
    application_numbers = [row["application_number"] for row in filtered_summaries]
    if not application_numbers:
        return []
    entries = models.InstitutionsBeneficiaryEntry.objects.select_related("article").filter(application_number__in=application_numbers).order_by("application_number", "created_at", "id")
    rows = []
    for entry in entries:
        rows.append({
            "Application Number": entry.application_number or "",
            "Beneficiary Name": entry.institution_name or "",
            "Requested Item": entry.article.article_name or "",
            "Quantity": str(entry.quantity or 0),
            "Cost Per Unit": _decimal_to_csv(entry.article_cost_per_unit),
            "Total Value": _decimal_to_csv(entry.total_amount),
            "Address": entry.address or "",
            "Mobile": entry.mobile or "",
            "Aadhar Number": "",
            "Handicapped Status": "",
            "Gender": "",
            "Gender Category": "",
            "Beneficiary Type": "Institutions",
            "Item Type": entry.article.item_type or "",
            "Article Category": entry.article.category or "",
            "Super Category Article": entry.article.master_category or "",
            "Token Name": entry.article.article_name_tk or "",
            "Comments": entry.notes or "",
        })
    return rows


def _export_master_entry_csv(request, *, export_scope):
    filters = _master_entry_filters_from_request(request)
    district_rows = []
    public_rows = []
    institution_rows = []

    if export_scope in {"all", "district"}:
        filtered_district_summaries = _filter_sort_district_summaries(
            _build_district_entry_summaries(),
            search_query=filters["search_query"],
            date_from=filters["date_from"],
            date_to=filters["date_to"],
            status_filter=filters["status_filter"],
            sort_by=filters["sort_by"],
            sort_dir=filters["sort_dir"],
        )
        district_rows = _district_export_rows(filtered_district_summaries)

    if export_scope in {"all", "public"}:
        filtered_public_entries = _filter_sort_public_entries(
            models.PublicBeneficiaryEntry.objects.select_related("article").all(),
            search_query=filters["search_query"],
            date_from=filters["date_from"],
            date_to=filters["date_to"],
            status_filter=filters["status_filter"],
            sort_by=filters["sort_by"],
            sort_dir=filters["sort_dir"],
        )
        public_rows = _public_export_rows(filtered_public_entries)

    if export_scope in {"all", "institutions"}:
        filtered_institution_summaries = _filter_sort_institution_summaries(
            _build_institution_entry_summaries(),
            search_query=filters["search_query"],
            date_from=filters["date_from"],
            date_to=filters["date_to"],
            status_filter=filters["status_filter"],
            sort_by=filters["sort_by"],
            sort_dir=filters["sort_dir"],
        )
        institution_rows = _institution_export_rows(filtered_institution_summaries)

    rows = district_rows + public_rows + institution_rows
    response = HttpResponse(content_type="text/csv")
    timestamp = timezone.localtime().strftime("%Y_%m_%d_%I_%M_%p")
    response["Content-Disposition"] = f'attachment; filename="master-entry-{export_scope}_{timestamp}.csv"'
    writer = csv.DictWriter(response, fieldnames=EXPORT_COLUMNS)
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return response


def _build_district_entry_summaries():
    entries = list(
        models.DistrictBeneficiaryEntry.objects.select_related("district", "article").order_by("-created_at")
    )
    grouped = {}
    for entry in entries:
        key = entry.district_id
        grouped.setdefault(key, []).append(entry)

    attachment_map = _district_attachment_preview_map(list(grouped.keys()))
    summaries = []
    for district_id, district_entries in grouped.items():
        first = district_entries[0]
        total_accrued = sum((entry.total_amount or 0) for entry in district_entries)
        total_quantity = sum((entry.quantity or 0) for entry in district_entries)
        remaining = (first.district.allotted_budget or 0) - total_accrued
        attachment = attachment_map.get(district_id)
        summaries.append(
            {
                "district_id": district_id,
                "application_number": first.district.application_number or first.application_number or "-",
                "district_name": first.district.district_name,
                "article_names": ", ".join(sorted({entry.article.article_name for entry in district_entries})),
                "article_count": len(district_entries),
                "total_quantity": total_quantity,
                "total_accrued": total_accrued,
                "remaining_fund": remaining,
                "status": first.status,
                "created_at": max(entry.created_at for entry in district_entries),
                "attachment_id": attachment.id if attachment else None,
                "attachment_preview_url": reverse("ui:application-attachment-download", kwargs={"attachment_id": attachment.id}) if attachment else "",
                "attachment_source": (attachment.file.name or "").lower() if attachment and attachment.file else "",
                "attachment_title": _attachment_preview_title(attachment),
                "detail_items": [
                    {
                        "article_name": entry.article.article_name,
                        "quantity": entry.quantity,
                        "unit_cost": entry.article_cost_per_unit,
                        "total_amount": entry.total_amount,
                        "notes": entry.notes,
                        "changed_at": entry.updated_at,
                    }
                    for entry in district_entries
                ],
            }
        )
    summaries.sort(key=lambda row: row["application_number"])
    return summaries


def _filter_sort_district_summaries(summaries, *, search_query="", date_from="", date_to="", status_filter="", sort_by="", sort_dir="desc"):
    if search_query:
        query = search_query.lower()
        summaries = [
            row for row in summaries
            if query in (row["application_number"] or "").lower()
            or query in (row["district_name"] or "").lower()
            or query in (row.get("article_names") or "").lower()
        ]

    if date_from:
        summaries = [row for row in summaries if row["created_at"].date().isoformat() >= date_from]
    if date_to:
        summaries = [row for row in summaries if row["created_at"].date().isoformat() <= date_to]
    if status_filter:
        summaries = [row for row in summaries if (row.get("status") or "") == status_filter]

    reverse = sort_dir == "desc"
    sort_map = {
        "application_number": lambda row: row["application_number"] or "",
        "district_name": lambda row: row["district_name"] or "",
        "total_accrued": lambda row: row["total_accrued"] or 0,
        "remaining_fund": lambda row: row["remaining_fund"] or 0,
        "status": lambda row: row.get("status") or "",
        "created_at": lambda row: row["created_at"],
    }
    if sort_by in sort_map:
        summaries = sorted(summaries, key=sort_map[sort_by], reverse=reverse)
    return summaries


def _district_form_context(district=None, entries=None, errors=None):
    articles = list(models.Article.objects.filter(is_active=True).order_by("article_name"))
    districts_queryset = models.DistrictMaster.objects.filter(is_active=True)
    if district is None:
        used_district_ids = models.DistrictBeneficiaryEntry.objects.values_list("district_id", flat=True).distinct()
        districts_queryset = districts_queryset.exclude(id__in=used_district_ids)
    districts = list(districts_queryset.order_by("district_name"))
    return {
        "district_master_list": districts,
        "articles_master_list": articles,
        "selected_district": district,
        "entry_rows": entries or [],
        "form_errors": errors or [],
        "form_successes": [],
        "application_status": (entries[0]["status"] if entries and isinstance(entries[0], dict) and entries[0].get("status") else ""),
    }


def _parse_district_rows(post_data):
    article_ids = post_data.getlist("article_id")
    quantities = post_data.getlist("quantity")
    unit_costs = post_data.getlist("unit_cost")
    notes_list = post_data.getlist("notes")
    rows = []
    max_len = max(len(article_ids), len(quantities), len(unit_costs), len(notes_list), 0)
    for idx in range(max_len):
        rows.append(
            {
                "article_id": (article_ids[idx] if idx < len(article_ids) else "").strip(),
                "quantity": (quantities[idx] if idx < len(quantities) else "").strip(),
                "unit_cost": (unit_costs[idx] if idx < len(unit_costs) else "").strip(),
                "notes": (notes_list[idx] if idx < len(notes_list) else "").strip(),
            }
        )
    return [row for row in rows if any(row.values())]


def _validate_and_build_district_entries(district, raw_rows):
    errors = []
    built_rows = []
    seen_articles = set()

    if not raw_rows:
        errors.append("Add at least one article or aid item.")
        return built_rows, errors

    article_map = {
        str(article.id): article
        for article in models.Article.objects.filter(id__in=[row["article_id"] for row in raw_rows if row["article_id"]])
    }

    for index, row in enumerate(raw_rows, start=1):
        article = article_map.get(row["article_id"])
        if not article:
            errors.append(f"Row {index}: select a valid article.")
            continue

        try:
            quantity = int(row["quantity"])
            if quantity <= 0:
                raise ValueError
        except (TypeError, ValueError):
            errors.append(f"Row {index}: quantity must be greater than 0.")
            continue

        if article.item_type != models.ItemTypeChoices.AID and article.id in seen_articles:
            errors.append(f"Row {index}: {article.article_name} can be added only once.")
            continue

        if article.item_type == models.ItemTypeChoices.AID and not row["notes"]:
            errors.append(f"Row {index}: comment is mandatory for aid items.")
            continue

        if article.cost_per_unit and article.cost_per_unit > 0:
            unit_cost = article.cost_per_unit
        else:
            try:
                unit_cost = Decimal(row["unit_cost"])
                if unit_cost < 0:
                    raise ValueError
            except (InvalidOperation, TypeError, ValueError):
                errors.append(f"Row {index}: enter a valid price for {article.article_name}.")
                continue

        total_amount = unit_cost * quantity
        built_rows.append(
            {
                "district": district,
                "application_number": district.application_number,
                "article": article,
                "article_cost_per_unit": unit_cost,
                "quantity": quantity,
                "total_amount": total_amount,
                "notes": row["notes"] or None,
                "status": models.BeneficiaryStatusChoices.PENDING,
            }
        )
        if article.item_type != models.ItemTypeChoices.AID:
            seen_articles.add(article.id)

    return built_rows, errors


class DistrictMasterEntryBaseView(LoginRequiredMixin, WriteRoleMixin, TemplateView):
    template_name = "dashboard/master_entry_district_form.html"

    def get_district(self):
        district_id = self.kwargs.get("district_id")
        if district_id:
            return models.DistrictMaster.objects.get(pk=district_id, is_active=True)
        return None

    def _render_form(self, district=None, entries=None, errors=None):
        context = self.get_context_data(**_district_form_context(district=district, entries=entries, errors=errors))
        context.update(_district_attachment_context(district))
        return self.render_to_response(context)

    def _save_entries(self, district, rows, *, replace=False):
        action = (self.request.POST.get("action") or "draft").strip().lower()
        target_status = models.BeneficiaryStatusChoices.SUBMITTED if action == "submit" else models.BeneficiaryStatusChoices.DRAFT
        built_rows, errors = _validate_and_build_district_entries(district, rows)
        for built in built_rows:
            built["status"] = target_status
        if errors:
            hydrated_rows = []
            article_lookup = {str(article.id): article for article in models.Article.objects.filter(is_active=True)}
            for row in rows:
                article = article_lookup.get(row["article_id"])
                hydrated_rows.append(
                    {
                        "article_id": row["article_id"],
                        "quantity": row["quantity"],
                        "unit_cost": row["unit_cost"],
                        "notes": row["notes"],
                        "article_name": article.article_name if article else "",
                        "item_type": article.item_type if article else "",
                    }
                )
            return self._render_form(district=district, entries=hydrated_rows, errors=errors)

        with transaction.atomic():
            if replace:
                existing_entries = list(
                    models.DistrictBeneficiaryEntry.objects.filter(district=district).select_related("article").order_by("id")
                )
                previous_status = existing_entries[0].status if existing_entries else None
                before_snapshot = _district_audit_snapshot(district)
                _sync_district_entries(existing_entries, built_rows, self.request.user)
                after_snapshot = _district_audit_snapshot(district)
                services.log_audit(
                    user=self.request.user,
                    action_type=models.ActionTypeChoices.UPDATE,
                    entity_type="district_application",
                    entity_id=str(district.id),
                    details={"before": before_snapshot, "after": after_snapshot},
                    **_request_audit_meta(self.request),
                )
                if previous_status != target_status:
                    services.log_audit(
                        user=self.request.user,
                        action_type=models.ActionTypeChoices.STATUS_CHANGE,
                        entity_type="district_application",
                        entity_id=str(district.id),
                        details={"from": previous_status, "to": target_status},
                        **_request_audit_meta(self.request),
                    )
            else:
                for built in built_rows:
                    models.DistrictBeneficiaryEntry.objects.create(created_by=self.request.user, **built)
                services.log_audit(
                    user=self.request.user,
                    action_type=models.ActionTypeChoices.CREATE,
                    entity_type="district_application",
                    entity_id=str(district.id),
                    details={"after": _district_audit_snapshot(district)},
                    **_request_audit_meta(self.request),
                )
                services.log_audit(
                    user=self.request.user,
                    action_type=models.ActionTypeChoices.STATUS_CHANGE,
                    entity_type="district_application",
                    entity_id=str(district.id),
                    details={"from": None, "to": target_status},
                    **_request_audit_meta(self.request),
                )
        return None


class DistrictMasterEntryCreateView(DistrictMasterEntryBaseView):
    def get(self, request, *args, **kwargs):
        return self._render_form()

    def post(self, request, *args, **kwargs):
        district_id = request.POST.get("district_id")
        if not district_id:
            return self._render_form(errors=["Select a district."])
        try:
            district = models.DistrictMaster.objects.get(pk=district_id, is_active=True)
        except models.DistrictMaster.DoesNotExist:
            return self._render_form(errors=["Select a valid district."])

        if models.DistrictBeneficiaryEntry.objects.filter(district=district).exists():
            return self._render_form(district=district, errors=["This district already has an entry. Use modify instead."])

        rows = _parse_district_rows(request.POST)
        response = self._save_entries(district, rows, replace=False)
        if response is not None:
            return response
        action = (request.POST.get("action") or "draft").strip().lower()
        if action == "submit":
            messages.success(request, "District application submitted.")
            return HttpResponseRedirect(reverse("ui:master-entry"))
        else:
            messages.success(request, "District application saved as draft.")
            return HttpResponseRedirect(reverse("ui:master-entry-district-edit", kwargs={"district_id": district.id}))


class DistrictMasterEntryUpdateView(DistrictMasterEntryBaseView):
    def get(self, request, *args, **kwargs):
        district = self.get_district()
        entries = list(models.DistrictBeneficiaryEntry.objects.filter(district=district).select_related("article").order_by("id"))
        if entries and entries[0].status == models.BeneficiaryStatusChoices.SUBMITTED:
            messages.error(request, "This district application is submitted and locked. Reopen it first.")
            return HttpResponseRedirect(reverse("ui:master-entry"))
        hydrated = [
            {
                "article_id": str(entry.article_id),
                "quantity": entry.quantity,
                "unit_cost": entry.article_cost_per_unit,
                "notes": entry.notes or "",
                "article_name": entry.article.article_name,
                "item_type": entry.article.item_type,
                "status": entry.status,
            }
            for entry in entries
        ]
        return self._render_form(district=district, entries=hydrated)

    def post(self, request, *args, **kwargs):
        district = self.get_district()
        locked_entries = list(models.DistrictBeneficiaryEntry.objects.filter(district=district).order_by("id"))
        if locked_entries and locked_entries[0].status == models.BeneficiaryStatusChoices.SUBMITTED:
            messages.error(request, "This district application is submitted and locked. Reopen it first.")
            return HttpResponseRedirect(reverse("ui:master-entry"))
        rows = _parse_district_rows(request.POST)
        response = self._save_entries(district, rows, replace=True)
        if response is not None:
            return response
        action = (request.POST.get("action") or "draft").strip().lower()
        if action == "submit":
            messages.success(request, "District application submitted.")
            return HttpResponseRedirect(reverse("ui:master-entry"))
        else:
            messages.success(request, "District application saved as draft.")
            return HttpResponseRedirect(reverse("ui:master-entry-district-edit", kwargs={"district_id": district.id}))


class DistrictMasterEntryDetailView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    template_name = "dashboard/master_entry_district_detail.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        district = models.DistrictMaster.objects.get(pk=self.kwargs["district_id"], is_active=True)
        entries = list(models.DistrictBeneficiaryEntry.objects.filter(district=district).select_related("article").order_by("id"))
        total_accrued = sum((entry.total_amount or 0) for entry in entries)
        total_quantity = sum((entry.quantity or 0) for entry in entries)
        context.update(
            {
                "district": district,
                "entries": entries,
                "total_accrued": total_accrued,
                "total_quantity": total_quantity,
                "remaining_fund": (district.allotted_budget or 0) - total_accrued,
            }
        )
        return context


class DistrictMasterEntryDeleteView(LoginRequiredMixin, AdminRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        district = models.DistrictMaster.objects.get(pk=kwargs["district_id"], is_active=True)
        snapshot = _district_audit_snapshot(district)
        models.DistrictBeneficiaryEntry.objects.filter(district=district).delete()
        services.log_audit(
            user=request.user,
            action_type=models.ActionTypeChoices.DELETE,
            entity_type="district_application",
            entity_id=str(district.id),
            details={"before": snapshot},
            **_request_audit_meta(request),
        )
        messages.warning(request, "District entry deleted.")
        return HttpResponseRedirect(reverse("ui:master-entry"))


class DistrictMasterEntryReopenView(LoginRequiredMixin, AdminRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        district = models.DistrictMaster.objects.get(pk=kwargs["district_id"], is_active=True)
        models.DistrictBeneficiaryEntry.objects.filter(district=district).update(status=models.BeneficiaryStatusChoices.DRAFT)
        services.log_audit(
            user=request.user,
            action_type=models.ActionTypeChoices.STATUS_CHANGE,
            entity_type="district_application",
            entity_id=str(district.id),
            details={"from": models.BeneficiaryStatusChoices.SUBMITTED, "to": models.BeneficiaryStatusChoices.DRAFT},
            **_request_audit_meta(request),
        )
        messages.success(request, "District application reopened as draft.")
        return HttpResponseRedirect(reverse("ui:master-entry"))


def _public_history_matches(aadhar_number):
    if not aadhar_number:
        return []
    return list(
        models.PublicBeneficiaryHistory.objects.filter(
            Q(aadhar_number=aadhar_number) | Q(aadhar_number_sp=aadhar_number)
        ).order_by("-year", "name")[:10]
    )


def _public_current_match(aadhar_number, *, exclude_pk=None):
    if not aadhar_number:
        return None
    queryset = models.PublicBeneficiaryEntry.objects.select_related("article").filter(aadhar_number=aadhar_number)
    if exclude_pk:
        queryset = queryset.exclude(pk=exclude_pk)
    return queryset.order_by("-created_at").first()


def _public_form_context(entry=None, form_data=None, history_matches=None, current_match=None, warnings=None, errors=None, successes=None, allow_duplicate_save=False):
    entry = entry or {}
    return {
        "public_entry": entry,
        "public_form_data": form_data or {},
        "history_matches": history_matches or [],
        "current_match": current_match,
        "form_warnings": warnings or [],
        "form_errors": errors or [],
        "form_successes": [],
        "allow_duplicate_save": allow_duplicate_save,
        "articles_master_list": list(models.Article.objects.filter(is_active=True).order_by("article_name")),
        "gender_choices": models.GenderChoices.choices,
        "female_status_choices": models.FemaleStatusChoices.choices,
        "female_status_descriptions": FEMALE_STATUS_DESCRIPTIONS,
        "application_status": getattr(entry, "status", ""),
    }


def _build_public_form_data(post_data):
    return {
        "aadhar_number": (post_data.get("aadhar_number") or "").strip(),
        "name": (post_data.get("name") or "").strip(),
        "is_handicapped": post_data.get("is_handicapped", "false"),
        "gender": (post_data.get("gender") or "").strip(),
        "female_status": (post_data.get("female_status") or "").strip(),
        "address": (post_data.get("address") or "").strip(),
        "mobile": (post_data.get("mobile") or "").strip(),
        "article_id": (post_data.get("article_id") or "").strip(),
        "article_cost_per_unit": (post_data.get("article_cost_per_unit") or "").strip(),
        "quantity": (post_data.get("quantity") or "").strip(),
        "notes": (post_data.get("notes") or "").strip(),
    }


def _validate_public_form(form_data, *, require_complete=True):
    errors = []
    article = None

    aadhar_number = form_data["aadhar_number"]
    if require_complete:
        if not (aadhar_number.isdigit() and len(aadhar_number) == 12):
            errors.append("Aadhaar number must be a valid 12-digit number.")
    elif aadhar_number and not (aadhar_number.isdigit() and len(aadhar_number) == 12):
        errors.append("Aadhaar number must be a valid 12-digit number.")

    if require_complete and not form_data["name"]:
        errors.append("Name is required.")

    if require_complete and not form_data["gender"]:
        errors.append("Gender is required.")
    elif form_data["gender"] == models.GenderChoices.FEMALE and require_complete and not form_data["female_status"]:
        errors.append("Gender Category is required when gender is Female.")

    if require_complete and not form_data["address"]:
        errors.append("Address is required.")

    if require_complete and not form_data["mobile"]:
        errors.append("Mobile number is required.")
    elif form_data["mobile"]:
        mobile_numbers = [value.strip() for value in form_data["mobile"].split("&") if value.strip()]
        if not mobile_numbers and require_complete:
            errors.append("Mobile number is required.")
        elif mobile_numbers and any((not number.isdigit()) or len(number) != 10 for number in mobile_numbers):
            errors.append("Each mobile number must be exactly 10 digits.")

    if require_complete and not form_data["article_id"]:
        errors.append("Select an article or aid.")
    elif form_data["article_id"]:
        try:
            article = models.Article.objects.get(pk=form_data["article_id"], is_active=True)
        except models.Article.DoesNotExist:
            errors.append("Select a valid article or aid.")

    quantity = 1
    quantity_raw = form_data["quantity"]
    if require_complete or form_data["article_id"] or quantity_raw:
        try:
            quantity = int(quantity_raw or 0)
            if quantity <= 0:
                raise ValueError
        except (TypeError, ValueError):
            errors.append("Quantity must be greater than 0.")
            quantity = 0

    unit_cost = None
    if article:
        if article.cost_per_unit and article.cost_per_unit > 0:
            unit_cost = article.cost_per_unit
        else:
            try:
                unit_cost = Decimal(form_data["article_cost_per_unit"])
                if unit_cost < 0:
                    raise ValueError
            except (InvalidOperation, TypeError, ValueError):
                errors.append("Enter a valid cost per unit.")

    return article, quantity, unit_cost, errors


def _build_institution_entry_summaries():
    entries = list(
        models.InstitutionsBeneficiaryEntry.objects.select_related("article").order_by("-created_at")
    )
    grouped = {}
    for entry in entries:
        key = entry.application_number or str(entry.pk)
        grouped.setdefault(key, []).append(entry)

    attachment_map = _institution_attachment_preview_map(list(grouped.keys()))
    summaries = []
    for application_number, group_entries in grouped.items():
        first = group_entries[0]
        attachment = attachment_map.get(application_number)
        summaries.append(
            {
                "application_number": application_number,
                "institution_name": first.institution_name,
                "institution_type": first.get_institution_type_display(),
                "article_names": ", ".join(sorted({entry.article.article_name for entry in group_entries})),
                "article_count": len(group_entries),
                "total_quantity": sum((row.quantity or 0) for row in group_entries),
                "total_value": sum((row.total_amount or 0) for row in group_entries),
                "status": first.status,
                "created_at": max(row.created_at for row in group_entries),
                "address": first.address,
                "mobile": first.mobile,
                "attachment_id": attachment.id if attachment else None,
                "attachment_preview_url": reverse("ui:application-attachment-download", kwargs={"attachment_id": attachment.id}) if attachment else "",
                "attachment_source": (attachment.file.name or "").lower() if attachment and attachment.file else "",
                "attachment_title": _attachment_preview_title(attachment),
                "detail_items": [
                    {
                        "article_name": entry.article.article_name,
                        "quantity": entry.quantity,
                        "unit_cost": entry.article_cost_per_unit,
                        "total_amount": entry.total_amount,
                        "notes": entry.notes,
                        "changed_at": entry.updated_at,
                    }
                    for entry in group_entries
                ],
            }
        )
    summaries.sort(key=lambda row: row["application_number"])
    return summaries


def _filter_sort_public_entries(queryset, *, search_query="", date_from="", date_to="", status_filter="", sort_by="", sort_dir="desc"):
    if search_query:
        queryset = queryset.filter(
            Q(application_number__icontains=search_query)
            | Q(name__icontains=search_query)
            | Q(aadhar_number__icontains=search_query)
            | Q(mobile__icontains=search_query)
            | Q(article__article_name__icontains=search_query)
        )
    if date_from:
        queryset = queryset.filter(created_at__date__gte=date_from)
    if date_to:
        queryset = queryset.filter(created_at__date__lte=date_to)
    if status_filter:
        queryset = queryset.filter(status=status_filter)

    ordering_map = {
        "application_number": "application_number",
        "name": "name",
        "aadhar_number": "aadhar_number",
        "total_amount": "total_amount",
        "status": "status",
        "created_at": "created_at",
    }
    ordering = ordering_map.get(sort_by, "created_at")
    if sort_dir == "desc":
        ordering = f"-{ordering}"
    return queryset.order_by(ordering)


def _filter_sort_institution_summaries(summaries, *, search_query="", date_from="", date_to="", status_filter="", sort_by="", sort_dir="desc"):
    if search_query:
        query = search_query.lower()
        summaries = [
            row for row in summaries
            if query in (row["application_number"] or "").lower()
            or query in (row["institution_name"] or "").lower()
            or query in (row.get("article_names") or "").lower()
        ]

    if date_from:
        summaries = [row for row in summaries if row["created_at"].date().isoformat() >= date_from]
    if date_to:
        summaries = [row for row in summaries if row["created_at"].date().isoformat() <= date_to]
    if status_filter:
        summaries = [row for row in summaries if (row.get("status") or "") == status_filter]

    reverse = sort_dir == "desc"
    sort_map = {
        "application_number": lambda row: row["application_number"] or "",
        "institution_name": lambda row: row["institution_name"] or "",
        "total_value": lambda row: row["total_value"] or 0,
        "status": lambda row: row.get("status") or "",
        "created_at": lambda row: row["created_at"],
    }
    if sort_by in sort_map:
        summaries = sorted(summaries, key=sort_map[sort_by], reverse=reverse)
    return summaries


def _institution_form_context(form_data=None, rows=None, errors=None, application_number=None):
    return {
        "institution_form_data": form_data or {},
        "institution_rows": rows or [],
        "form_errors": errors or [],
        "articles_master_list": list(models.Article.objects.filter(is_active=True).order_by("article_name")),
        "institution_type_choices": models.InstitutionTypeChoices.choices,
        "institution_application_number": application_number,
        "application_status": (rows[0]["status"] if rows and isinstance(rows[0], dict) and rows[0].get("status") else ""),
    }


def _build_institution_form_data(post_data):
    return {
        "institution_name": (post_data.get("institution_name") or "").strip(),
        "institution_type": (post_data.get("institution_type") or "").strip(),
        "address": (post_data.get("address") or "").strip(),
        "mobile": (post_data.get("mobile") or "").strip(),
    }


def _validate_institution_rows(raw_rows, *, require_complete=True):
    errors = []
    built_rows = []
    seen_articles = set()
    if not raw_rows:
        errors.append("Add at least one article or aid item.")
        return built_rows, errors

    article_map = {
        str(article.id): article
        for article in models.Article.objects.filter(id__in=[row["article_id"] for row in raw_rows if row["article_id"]])
    }

    for index, row in enumerate(raw_rows, start=1):
        article = article_map.get(row["article_id"])
        if not article:
            errors.append(f"Row {index}: select a valid article.")
            continue

        try:
            quantity = int(row["quantity"])
            if quantity <= 0:
                raise ValueError
        except (TypeError, ValueError):
            errors.append(f"Row {index}: quantity must be greater than 0.")
            continue

        if article.item_type != models.ItemTypeChoices.AID and article.id in seen_articles:
            errors.append(f"Row {index}: {article.article_name} can be added only once.")
            continue

        if article.cost_per_unit and article.cost_per_unit > 0:
            unit_cost = article.cost_per_unit
        else:
            try:
                unit_cost = Decimal(row["unit_cost"])
                if unit_cost < 0:
                    raise ValueError
            except (InvalidOperation, TypeError, ValueError):
                errors.append(f"Row {index}: enter a valid price for {article.article_name}.")
                continue

        if require_complete and article.item_type == models.ItemTypeChoices.AID and not (row["notes"] or "").strip():
            errors.append(f"Row {index}: comment is required for aid items.")
            continue

        built_rows.append(
            {
                "article": article,
                "article_cost_per_unit": unit_cost,
                "quantity": quantity,
                "total_amount": unit_cost * quantity,
                "notes": row["notes"] or None,
            }
        )
        if article.item_type != models.ItemTypeChoices.AID:
            seen_articles.add(article.id)
    return built_rows, errors


def _sync_district_entries(existing_entries, built_rows, user):
    by_article = {}
    for entry in existing_entries:
        by_article.setdefault(entry.article_id, []).append(entry)

    used_ids = set()
    for built in built_rows:
        candidates = by_article.get(built["article"].id, [])
        match = next((entry for entry in candidates if entry.id not in used_ids), None)
        if match is None:
            models.DistrictBeneficiaryEntry.objects.create(created_by=user, **built)
            continue

        changed = False
        if match.application_number != built["application_number"]:
            match.application_number = built["application_number"]
            changed = True
        if match.article_id != built["article"].id:
            match.article = built["article"]
            changed = True
        if match.article_cost_per_unit != built["article_cost_per_unit"]:
            match.article_cost_per_unit = built["article_cost_per_unit"]
            changed = True
        if match.quantity != built["quantity"]:
            match.quantity = built["quantity"]
            changed = True
        if match.total_amount != built["total_amount"]:
            match.total_amount = built["total_amount"]
            changed = True
        if match.notes != built["notes"]:
            match.notes = built["notes"]
            changed = True
        if match.status != built["status"]:
            match.status = built["status"]
            changed = True
        if not match.created_by_id:
            match.created_by = user
            changed = True
        if changed:
            match.save()
        used_ids.add(match.id)

    for entry in existing_entries:
        if entry.id not in used_ids:
            entry.delete()


def _sync_institution_entries(existing_entries, built_rows, user, *, application_number, form_data):
    by_article = {}
    for entry in existing_entries:
        by_article.setdefault(entry.article_id, []).append(entry)

    used_ids = set()
    for built in built_rows:
        candidates = by_article.get(built["article"].id, [])
        match = next((entry for entry in candidates if entry.id not in used_ids), None)
        if match is None:
            models.InstitutionsBeneficiaryEntry.objects.create(
                created_by=user,
                application_number=application_number,
                institution_name=form_data["institution_name"],
                institution_type=form_data["institution_type"],
                address=form_data["address"] or None,
                mobile=form_data["mobile"] or None,
                **built,
            )
            continue

        changed = False
        if match.application_number != application_number:
            match.application_number = application_number
            changed = True
        if match.institution_name != form_data["institution_name"]:
            match.institution_name = form_data["institution_name"]
            changed = True
        if match.institution_type != form_data["institution_type"]:
            match.institution_type = form_data["institution_type"]
            changed = True
        address = form_data["address"] or None
        if match.address != address:
            match.address = address
            changed = True
        mobile = form_data["mobile"] or None
        if match.mobile != mobile:
            match.mobile = mobile
            changed = True
        if match.article_id != built["article"].id:
            match.article = built["article"]
            changed = True
        if match.article_cost_per_unit != built["article_cost_per_unit"]:
            match.article_cost_per_unit = built["article_cost_per_unit"]
            changed = True
        if match.quantity != built["quantity"]:
            match.quantity = built["quantity"]
            changed = True
        if match.total_amount != built["total_amount"]:
            match.total_amount = built["total_amount"]
            changed = True
        if match.notes != built["notes"]:
            match.notes = built["notes"]
            changed = True
        if match.status != built["status"]:
            match.status = built["status"]
            changed = True
        if not match.created_by_id:
            match.created_by = user
            changed = True
        if changed:
            match.save()
        used_ids.add(match.id)

    for entry in existing_entries:
        if entry.id not in used_ids:
            entry.delete()


class PublicMasterEntryBaseView(LoginRequiredMixin, WriteRoleMixin, TemplateView):
    template_name = "dashboard/master_entry_public_form.html"

    def get_entry(self):
        pk = self.kwargs.get("pk")
        if pk:
            return models.PublicBeneficiaryEntry.objects.select_related("article").get(pk=pk)
        return None

    def _render_form(self, *, entry=None, form_data=None, history_matches=None, current_match=None, warnings=None, errors=None, successes=None, allow_duplicate_save=False):
        context = self.get_context_data(
            **_public_form_context(
                entry=entry,
                form_data=form_data,
                history_matches=history_matches,
                current_match=current_match,
                warnings=warnings,
                errors=errors,
                successes=successes,
                allow_duplicate_save=allow_duplicate_save,
            )
        )
        context.update(_public_attachment_context(entry))
        return self.render_to_response(context)

    def _save_entry(self, *, entry=None, form_data=None):
        action = (self.request.POST.get("action") or "draft").strip().lower()
        target_status = models.BeneficiaryStatusChoices.SUBMITTED if action == "submit" else models.BeneficiaryStatusChoices.DRAFT
        require_complete = target_status == models.BeneficiaryStatusChoices.SUBMITTED
        article, quantity, unit_cost, errors = _validate_public_form(form_data, require_complete=require_complete)
        if not require_complete and article is None:
            errors.append("Select an article or aid before saving draft.")
        history_matches = _public_history_matches(form_data["aadhar_number"])
        current_match = _public_current_match(form_data["aadhar_number"], exclude_pk=getattr(entry, "pk", None))
        warnings = ["This Aadhaar number exists in past beneficiary history."] if history_matches else []
        if current_match:
            warnings.append("Duplicate found in current applications.")
        if errors:
            return self._render_form(
                entry=entry,
                form_data=form_data,
                history_matches=history_matches,
                current_match=current_match,
                warnings=warnings,
                errors=errors,
            ), None

        if current_match:
            return self._render_form(
                entry=entry,
                form_data=form_data,
                history_matches=history_matches,
                current_match=current_match,
                warnings=warnings + ["Duplicate found in current applications. Review the existing record below and use Modify if you want to update it."],
            ), None

        if entry is None:
            entry = models.PublicBeneficiaryEntry(application_number=f"DRAFT-PUB-{uuid.uuid4().hex[:12].upper()}")
            action_type = models.ActionTypeChoices.CREATE
            before_snapshot = None
            previous_status = None
        else:
            action_type = models.ActionTypeChoices.UPDATE
            before_snapshot = _public_audit_snapshot(entry)
            previous_status = entry.status

        entry.name = form_data["name"]
        entry.aadhar_number = form_data["aadhar_number"]
        entry.is_handicapped = form_data["is_handicapped"] == "true"
        entry.gender = form_data["gender"]
        entry.female_status = form_data["female_status"] or None
        entry.address = form_data["address"] or None
        entry.mobile = form_data["mobile"]
        entry.article = article
        entry.article_cost_per_unit = unit_cost
        entry.quantity = quantity
        entry.total_amount = unit_cost * quantity
        entry.notes = form_data["notes"] or None
        if target_status == models.BeneficiaryStatusChoices.SUBMITTED and (not entry.application_number or str(entry.application_number).startswith("DRAFT-PUB-")):
            entry.application_number = services.next_public_application_number()
        entry.status = target_status
        if not entry.created_by_id:
            entry.created_by = self.request.user
        entry.save()
        services.log_audit(
            user=self.request.user,
            action_type=action_type,
            entity_type="public_application",
            entity_id=str(entry.id),
            details={"before": before_snapshot, "after": _public_audit_snapshot(entry)},
            **_request_audit_meta(self.request),
        )
        if previous_status != target_status:
            services.log_audit(
                user=self.request.user,
                action_type=models.ActionTypeChoices.STATUS_CHANGE,
                entity_type="public_application",
                entity_id=str(entry.id),
                details={"from": previous_status, "to": target_status},
                **_request_audit_meta(self.request),
            )
        return None, entry


class PublicMasterEntryCreateView(PublicMasterEntryBaseView):
    def get(self, request, *args, **kwargs):
        return self._render_form(form_data={"quantity": "1"})

    def post(self, request, *args, **kwargs):
        form_data = _build_public_form_data(request.POST)
        if request.POST.get("action") == "verify":
            if not (form_data["aadhar_number"].isdigit() and len(form_data["aadhar_number"]) == 12):
                return self._render_form(
                    form_data=form_data,
                    errors=["Aadhaar number must be a valid 12-digit number."],
                )
            history_matches = _public_history_matches(form_data["aadhar_number"])
            current_match = _public_current_match(form_data["aadhar_number"])
            warnings = ["This Aadhaar number exists in past beneficiary history."] if history_matches else []
            successes = ["Verification passed."] if not history_matches and not current_match else []
            if current_match:
                warnings.append("Duplicate found in current applications.")
            return self._render_form(
                form_data=form_data,
                history_matches=history_matches,
                current_match=current_match,
                warnings=warnings,
                successes=successes,
                allow_duplicate_save=bool(current_match),
            )

        response, saved_entry = self._save_entry(form_data=form_data)
        if response is not None:
            return response
        action = (request.POST.get("action") or "draft").strip().lower()
        if action == "submit":
            request.session["public_submit_popup"] = {"application_number": saved_entry.application_number, "name": saved_entry.name}
            messages.success(request, "Public application submitted.")
            return HttpResponseRedirect(reverse("ui:master-entry") + "?type=public")
        else:
            messages.success(request, "Public application saved as draft.")
            return HttpResponseRedirect(reverse("ui:master-entry-public-edit", kwargs={"pk": saved_entry.pk}))


class PublicMasterEntryUpdateView(PublicMasterEntryBaseView):
    def get(self, request, *args, **kwargs):
        entry = self.get_entry()
        if entry.status == models.BeneficiaryStatusChoices.SUBMITTED:
            messages.error(request, "This public application is submitted and locked. Reopen it first.")
            return HttpResponseRedirect(reverse("ui:master-entry") + "?type=public")
        return self._render_form(
            entry=entry,
            form_data={
                "aadhar_number": entry.aadhar_number,
                "name": entry.name,
                "is_handicapped": "true" if entry.is_handicapped else "false",
                "gender": entry.gender or "",
                "female_status": entry.female_status or "",
                "address": entry.address or "",
                "mobile": entry.mobile or "",
                "article_id": str(entry.article_id),
                "article_cost_per_unit": str(entry.article_cost_per_unit),
                "quantity": str(entry.quantity),
                "notes": entry.notes or "",
            },
            history_matches=_public_history_matches(entry.aadhar_number),
        )

    def post(self, request, *args, **kwargs):
        entry = self.get_entry()
        if entry.status == models.BeneficiaryStatusChoices.SUBMITTED:
            messages.error(request, "This public application is submitted and locked. Reopen it first.")
            return HttpResponseRedirect(reverse("ui:master-entry") + "?type=public")
        form_data = _build_public_form_data(request.POST)
        if request.POST.get("action") == "verify":
            if not (form_data["aadhar_number"].isdigit() and len(form_data["aadhar_number"]) == 12):
                return self._render_form(
                    entry=entry,
                    form_data=form_data,
                    errors=["Aadhaar number must be a valid 12-digit number."],
                )
            history_matches = _public_history_matches(form_data["aadhar_number"])
            current_match = _public_current_match(form_data["aadhar_number"], exclude_pk=entry.pk)
            warnings = ["This Aadhaar number exists in past beneficiary history."] if history_matches else []
            successes = ["Verification passed."] if not history_matches and not current_match else []
            if current_match:
                warnings.append("Duplicate found in current applications.")
            return self._render_form(
                entry=entry,
                form_data=form_data,
                history_matches=history_matches,
                current_match=current_match,
                warnings=warnings,
                successes=successes,
                allow_duplicate_save=bool(current_match),
            )

        response, saved_entry = self._save_entry(entry=entry, form_data=form_data)
        if response is not None:
            return response
        action = (request.POST.get("action") or "draft").strip().lower()
        if action == "submit":
            request.session["public_submit_popup"] = {"application_number": saved_entry.application_number, "name": saved_entry.name}
            messages.success(request, "Public application submitted.")
            return HttpResponseRedirect(reverse("ui:master-entry") + "?type=public")
        else:
            messages.success(request, "Public application saved as draft.")
            return HttpResponseRedirect(reverse("ui:master-entry-public-edit", kwargs={"pk": saved_entry.pk}))


class PublicMasterEntryDetailView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    template_name = "dashboard/master_entry_public_detail.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        entry = models.PublicBeneficiaryEntry.objects.select_related("article").get(pk=self.kwargs["pk"])
        context["entry"] = entry
        context["history_matches"] = _public_history_matches(entry.aadhar_number)
        return context


class PublicMasterEntryDeleteView(LoginRequiredMixin, AdminRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        entry = models.PublicBeneficiaryEntry.objects.get(pk=kwargs["pk"])
        snapshot = _public_audit_snapshot(entry)
        entry.delete()
        services.log_audit(
            user=request.user,
            action_type=models.ActionTypeChoices.DELETE,
            entity_type="public_application",
            entity_id=str(kwargs["pk"]),
            details={"before": snapshot},
            **_request_audit_meta(request),
        )
        messages.warning(request, "Public entry deleted.")
        return HttpResponseRedirect(reverse("ui:master-entry") + "?type=public")


class PublicMasterEntryReopenView(LoginRequiredMixin, AdminRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        entry = models.PublicBeneficiaryEntry.objects.get(pk=kwargs["pk"])
        previous_status = entry.status
        entry.status = models.BeneficiaryStatusChoices.DRAFT
        entry.save(update_fields=["status"])
        services.log_audit(
            user=request.user,
            action_type=models.ActionTypeChoices.STATUS_CHANGE,
            entity_type="public_application",
            entity_id=str(entry.id),
            details={"from": previous_status, "to": models.BeneficiaryStatusChoices.DRAFT},
            **_request_audit_meta(request),
        )
        messages.success(request, "Public application reopened as draft.")
        return HttpResponseRedirect(reverse("ui:master-entry") + "?type=public")


class InstitutionsMasterEntryBaseView(LoginRequiredMixin, WriteRoleMixin, TemplateView):
    template_name = "dashboard/master_entry_institution_form.html"

    def _render_form(self, *, form_data=None, rows=None, errors=None, application_number=None):
        context = self.get_context_data(
            **_institution_form_context(
                form_data=form_data,
                rows=rows,
                errors=errors,
                application_number=application_number,
            )
        )
        context.update(_institution_attachment_context(application_number))
        return self.render_to_response(context)

    def _save_group(self, *, application_number=None, form_data=None, raw_rows=None, replace=False):
        action = (self.request.POST.get("action") or "draft").strip().lower()
        require_complete = action == "submit"
        errors = []
        if require_complete and not form_data["institution_name"]:
            errors.append("Institution name is required.")
        if require_complete and not form_data["institution_type"]:
            errors.append("Institution type is required.")
        if require_complete and not form_data["address"]:
            errors.append("Address is required.")
        if require_complete and not form_data["mobile"]:
            errors.append("Mobile number is required.")
        elif form_data["mobile"]:
            mobile_numbers = [value.strip() for value in form_data["mobile"].split("&") if value.strip()]
            if mobile_numbers and any((not number.isdigit()) or len(number) != 10 for number in mobile_numbers):
                errors.append("Each mobile number must be exactly 10 digits.")

        built_rows, row_errors = _validate_institution_rows(raw_rows, require_complete=require_complete)
        errors.extend(row_errors)

        if errors:
            article_lookup = {str(article.id): article for article in models.Article.objects.filter(is_active=True)}
            hydrated_rows = []
            for row in raw_rows:
                article = article_lookup.get(row["article_id"])
                hydrated_rows.append(
                    {
                        "article_id": row["article_id"],
                        "quantity": row["quantity"],
                        "unit_cost": row["unit_cost"],
                        "notes": row["notes"],
                        "article_name": article.article_name if article else "",
                        "item_type": article.item_type if article else "",
                    }
                )
            return self._render_form(
                form_data=form_data,
                rows=hydrated_rows,
                errors=errors,
                application_number=application_number,
            )

        source_application_number = application_number
        is_draft_placeholder = bool(application_number and application_number.startswith("DRAFT-INS-"))
        if action == "submit":
            if not application_number or is_draft_placeholder:
                application_number = services.next_institution_application_number()
        elif not application_number:
            application_number = f"DRAFT-INS-{uuid.uuid4().hex[:12].upper()}"
        target_status = models.BeneficiaryStatusChoices.SUBMITTED if action == "submit" else models.BeneficiaryStatusChoices.DRAFT
        for built in built_rows:
            built["status"] = target_status

        with transaction.atomic():
            if replace:
                lookup_application_number = source_application_number or application_number
                before_snapshot = _institution_audit_snapshot(lookup_application_number)
                existing_entries = list(
                    models.InstitutionsBeneficiaryEntry.objects.filter(application_number=lookup_application_number).select_related("article").order_by("id")
                )
                previous_status = existing_entries[0].status if existing_entries else None
                _sync_institution_entries(
                    existing_entries,
                    built_rows,
                    self.request.user,
                    application_number=application_number,
                    form_data=form_data,
                )
                if lookup_application_number != application_number:
                    models.ApplicationAttachment.objects.filter(
                        application_type=models.ApplicationAttachmentTypeChoices.INSTITUTION,
                        institution_application_number=lookup_application_number,
                    ).update(institution_application_number=application_number)
                services.log_audit(
                    user=self.request.user,
                    action_type=models.ActionTypeChoices.UPDATE,
                    entity_type="institution_application",
                    entity_id=application_number,
                    details={"before": before_snapshot, "after": _institution_audit_snapshot(application_number)},
                    **_request_audit_meta(self.request),
                )
                if previous_status != target_status:
                    services.log_audit(
                        user=self.request.user,
                        action_type=models.ActionTypeChoices.STATUS_CHANGE,
                        entity_type="institution_application",
                        entity_id=application_number,
                        details={"from": previous_status, "to": target_status},
                        **_request_audit_meta(self.request),
                    )
            else:
                for built in built_rows:
                    models.InstitutionsBeneficiaryEntry.objects.create(
                        created_by=self.request.user,
                        application_number=application_number,
                        institution_name=form_data["institution_name"],
                        institution_type=form_data["institution_type"],
                        address=form_data["address"] or None,
                        mobile=form_data["mobile"] or None,
                        **built,
                    )
                services.log_audit(
                    user=self.request.user,
                    action_type=models.ActionTypeChoices.CREATE,
                    entity_type="institution_application",
                    entity_id=application_number,
                    details={"after": _institution_audit_snapshot(application_number)},
                    **_request_audit_meta(self.request),
                )
                services.log_audit(
                    user=self.request.user,
                    action_type=models.ActionTypeChoices.STATUS_CHANGE,
                    entity_type="institution_application",
                    entity_id=application_number,
                    details={"from": None, "to": target_status},
                    **_request_audit_meta(self.request),
                )
        self._saved_institution_application_number = application_number
        return None


class InstitutionsMasterEntryCreateView(InstitutionsMasterEntryBaseView):
    def get(self, request, *args, **kwargs):
        return self._render_form()

    def post(self, request, *args, **kwargs):
        form_data = _build_institution_form_data(request.POST)
        rows = _parse_district_rows(request.POST)
        action = (request.POST.get("action") or "draft").strip().lower()
        response = self._save_group(form_data=form_data, raw_rows=rows)
        if response is not None:
            return response
        saved_application_number = getattr(self, "_saved_institution_application_number", None)
        if action == "submit":
            popup_entry = models.InstitutionsBeneficiaryEntry.objects.filter(application_number=saved_application_number).order_by("-updated_at").first()
            if popup_entry:
                request.session["institution_submit_popup"] = {
                    "application_number": popup_entry.application_number,
                    "name": popup_entry.institution_name,
                }
            messages.success(request, "Institution application submitted.")
            return HttpResponseRedirect(reverse("ui:master-entry") + "?type=institutions")
        else:
            messages.success(request, "Institution application saved as draft.")
            return HttpResponseRedirect(reverse("ui:master-entry-institution-edit", kwargs={"application_number": saved_application_number}))


class InstitutionsMasterEntryUpdateView(InstitutionsMasterEntryBaseView):
    def get(self, request, *args, **kwargs):
        application_number = kwargs["application_number"]
        entries = list(
            models.InstitutionsBeneficiaryEntry.objects.filter(application_number=application_number).select_related("article").order_by("id")
        )
        if entries and entries[0].status == models.BeneficiaryStatusChoices.SUBMITTED:
            messages.error(request, "This institution application is submitted and locked. Reopen it first.")
            return HttpResponseRedirect(reverse("ui:master-entry") + "?type=institutions")
        first = entries[0]
        rows = [
            {
                "article_id": str(entry.article_id),
                "quantity": entry.quantity,
                "unit_cost": entry.article_cost_per_unit,
                "notes": entry.notes or "",
                "article_name": entry.article.article_name,
                "item_type": entry.article.item_type,
                "status": entry.status,
            }
            for entry in entries
        ]
        form_data = {
            "institution_name": first.institution_name,
            "institution_type": first.institution_type,
            "address": first.address or "",
            "mobile": first.mobile or "",
        }
        return self._render_form(form_data=form_data, rows=rows, application_number=application_number)

    def post(self, request, *args, **kwargs):
        application_number = kwargs["application_number"]
        existing_entries = list(models.InstitutionsBeneficiaryEntry.objects.filter(application_number=application_number).order_by("id"))
        if existing_entries and existing_entries[0].status == models.BeneficiaryStatusChoices.SUBMITTED:
            messages.error(request, "This institution application is submitted and locked. Reopen it first.")
            return HttpResponseRedirect(reverse("ui:master-entry") + "?type=institutions")
        form_data = _build_institution_form_data(request.POST)
        rows = _parse_district_rows(request.POST)
        action = (request.POST.get("action") or "draft").strip().lower()
        response = self._save_group(application_number=application_number, form_data=form_data, raw_rows=rows, replace=True)
        if response is not None:
            return response
        saved_application_number = getattr(self, "_saved_institution_application_number", application_number)
        if action == "submit":
            popup_entry = models.InstitutionsBeneficiaryEntry.objects.filter(application_number=saved_application_number).order_by("-updated_at").first()
            if popup_entry:
                request.session["institution_submit_popup"] = {
                    "application_number": popup_entry.application_number,
                    "name": popup_entry.institution_name,
                }
            messages.success(request, "Institution application submitted.")
            return HttpResponseRedirect(reverse("ui:master-entry") + "?type=institutions")
        else:
            messages.success(request, "Institution application saved as draft.")
            return HttpResponseRedirect(reverse("ui:master-entry-institution-edit", kwargs={"application_number": saved_application_number}))


class InstitutionsMasterEntryDetailView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    template_name = "dashboard/master_entry_institution_detail.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        application_number = self.kwargs["application_number"]
        entries = list(
            models.InstitutionsBeneficiaryEntry.objects.filter(application_number=application_number).select_related("article").order_by("id")
        )
        first = entries[0]
        context.update(
            {
                "application_number": application_number,
                "entry_header": first,
                "entries": entries,
                "total_quantity": sum((row.quantity or 0) for row in entries),
                "total_value": sum((row.total_amount or 0) for row in entries),
            }
        )
        return context


class InstitutionsMasterEntryDeleteView(LoginRequiredMixin, AdminRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        application_number = kwargs["application_number"]
        snapshot = _institution_audit_snapshot(application_number)
        models.InstitutionsBeneficiaryEntry.objects.filter(application_number=application_number).delete()
        services.log_audit(
            user=request.user,
            action_type=models.ActionTypeChoices.DELETE,
            entity_type="institution_application",
            entity_id=application_number,
            details={"before": snapshot},
            **_request_audit_meta(request),
        )
        messages.warning(request, "Institution entry deleted.")
        return HttpResponseRedirect(reverse("ui:master-entry") + "?type=institutions")


class InstitutionsMasterEntryReopenView(LoginRequiredMixin, AdminRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        application_number = kwargs["application_number"]
        models.InstitutionsBeneficiaryEntry.objects.filter(application_number=application_number).update(
            status=models.BeneficiaryStatusChoices.DRAFT
        )
        services.log_audit(
            user=request.user,
            action_type=models.ActionTypeChoices.STATUS_CHANGE,
            entity_type="institution_application",
            entity_id=application_number,
            details={"from": models.BeneficiaryStatusChoices.SUBMITTED, "to": models.BeneficiaryStatusChoices.DRAFT},
            **_request_audit_meta(request),
        )
        messages.success(request, "Institution application reopened as draft.")
        return HttpResponseRedirect(reverse("ui:master-entry") + "?type=institutions")


class ApplicationAttachmentDownloadView(LoginRequiredMixin, RoleRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        attachment = get_object_or_404(models.ApplicationAttachment.objects.select_related("uploaded_by"), pk=kwargs["attachment_id"])
        if not attachment.file:
            raise Http404("File not found.")
        stored_name = os.path.basename(attachment.file.name)
        if attachment.application_type == models.ApplicationAttachmentTypeChoices.DISTRICT and attachment.district_id:
            application_reference = attachment.district.application_number
        elif attachment.application_type == models.ApplicationAttachmentTypeChoices.PUBLIC and attachment.public_entry_id:
            application_reference = attachment.public_entry.application_number or f"PUBLIC-{attachment.public_entry_id}"
        elif attachment.application_type == models.ApplicationAttachmentTypeChoices.INSTITUTION:
            application_reference = attachment.institution_application_number
        else:
            application_reference = ""
        display_name = _prefixed_attachment_name(application_reference, stored_name, attachment.file_name or stored_name)
        as_attachment = (request.GET.get("download") or "").strip() == "1"
        content_type, _ = mimetypes.guess_type(stored_name)
        if as_attachment:
            display_root, display_ext = os.path.splitext(display_name)
            _, stored_ext = os.path.splitext(stored_name)
            download_name = display_name if display_ext else f"{display_name}{stored_ext}"
            return FileResponse(
                attachment.file.open("rb"),
                as_attachment=True,
                filename=download_name,
                content_type=content_type or "application/octet-stream",
            )
        response = FileResponse(
            attachment.file.open("rb"),
            as_attachment=False,
            content_type=content_type or "application/octet-stream",
        )
        response["Content-Disposition"] = "inline"
        return response


class DistrictApplicationAttachmentUploadView(LoginRequiredMixin, WriteRoleMixin, View):
    def post(self, request, *args, **kwargs):
        district = get_object_or_404(models.DistrictMaster, pk=kwargs["district_id"], is_active=True)
        form = ApplicationAttachmentUploadForm(request.POST, request.FILES)
        if not form.is_valid():
            messages.error(request, "; ".join(form.errors.get("file", []) + form.errors.get("file_name", [])) or "Choose a valid file before uploading.")
            return HttpResponseRedirect(reverse("ui:master-entry-district-edit", kwargs={"district_id": district.id}))

        existing_count = models.ApplicationAttachment.objects.filter(
            application_type=models.ApplicationAttachmentTypeChoices.DISTRICT,
            district=district,
        ).count()
        if existing_count >= ApplicationAttachmentUploadForm.MAX_FILES_PER_APPLICATION:
            messages.error(request, f"Maximum {ApplicationAttachmentUploadForm.MAX_FILES_PER_APPLICATION} files are allowed for one application.")
            return HttpResponseRedirect(reverse("ui:master-entry-district-edit", kwargs={"district_id": district.id}))

        uploaded = form.cleaned_data["file"]
        display_name = _prefixed_attachment_name(district.application_number, uploaded.name, form.cleaned_data.get("file_name") or "")
        models.ApplicationAttachment.objects.create(
            application_type=models.ApplicationAttachmentTypeChoices.DISTRICT,
            district=district,
            file=uploaded,
            file_name=display_name,
            uploaded_by=request.user,
        )
        messages.success(request, "Attachment uploaded.")
        return HttpResponseRedirect(reverse("ui:master-entry-district-edit", kwargs={"district_id": district.id}))


class DistrictApplicationAttachmentDeleteView(LoginRequiredMixin, WriteRoleMixin, View):
    def post(self, request, *args, **kwargs):
        district = get_object_or_404(models.DistrictMaster, pk=kwargs["district_id"], is_active=True)
        attachment = get_object_or_404(
            models.ApplicationAttachment,
            pk=kwargs["attachment_id"],
            application_type=models.ApplicationAttachmentTypeChoices.DISTRICT,
            district=district,
        )
        if attachment.file:
            attachment.file.delete(save=False)
        attachment.delete()
        messages.success(request, "Attachment removed.")
        return HttpResponseRedirect(reverse("ui:master-entry-district-edit", kwargs={"district_id": district.id}))


class PublicApplicationAttachmentUploadView(LoginRequiredMixin, WriteRoleMixin, View):
    def post(self, request, *args, **kwargs):
        entry = get_object_or_404(models.PublicBeneficiaryEntry, pk=kwargs["pk"])
        form = ApplicationAttachmentUploadForm(request.POST, request.FILES)
        if not form.is_valid():
            messages.error(request, "; ".join(form.errors.get("file", []) + form.errors.get("file_name", [])) or "Choose a valid file before uploading.")
            return HttpResponseRedirect(reverse("ui:master-entry-public-edit", kwargs={"pk": entry.pk}))

        existing_count = models.ApplicationAttachment.objects.filter(
            application_type=models.ApplicationAttachmentTypeChoices.PUBLIC,
            public_entry=entry,
        ).count()
        if existing_count >= ApplicationAttachmentUploadForm.MAX_FILES_PER_APPLICATION:
            messages.error(request, f"Maximum {ApplicationAttachmentUploadForm.MAX_FILES_PER_APPLICATION} files are allowed for one application.")
            return HttpResponseRedirect(reverse("ui:master-entry-public-edit", kwargs={"pk": entry.pk}))

        uploaded = form.cleaned_data["file"]
        application_reference = entry.application_number or f"PUBLIC-{entry.pk}"
        display_name = _prefixed_attachment_name(application_reference, uploaded.name, form.cleaned_data.get("file_name") or "")
        models.ApplicationAttachment.objects.create(
            application_type=models.ApplicationAttachmentTypeChoices.PUBLIC,
            public_entry=entry,
            file=uploaded,
            file_name=display_name,
            uploaded_by=request.user,
        )
        messages.success(request, "Attachment uploaded.")
        return HttpResponseRedirect(reverse("ui:master-entry-public-edit", kwargs={"pk": entry.pk}))


class PublicApplicationAttachmentDeleteView(LoginRequiredMixin, WriteRoleMixin, View):
    def post(self, request, *args, **kwargs):
        entry = get_object_or_404(models.PublicBeneficiaryEntry, pk=kwargs["pk"])
        attachment = get_object_or_404(
            models.ApplicationAttachment,
            pk=kwargs["attachment_id"],
            application_type=models.ApplicationAttachmentTypeChoices.PUBLIC,
            public_entry=entry,
        )
        if attachment.file:
            attachment.file.delete(save=False)
        attachment.delete()
        messages.success(request, "Attachment removed.")
        return HttpResponseRedirect(reverse("ui:master-entry-public-edit", kwargs={"pk": entry.pk}))


class InstitutionApplicationAttachmentUploadView(LoginRequiredMixin, WriteRoleMixin, View):
    def post(self, request, *args, **kwargs):
        application_number = kwargs["application_number"]
        if not models.InstitutionsBeneficiaryEntry.objects.filter(application_number=application_number).exists():
            raise Http404("Institution application not found.")
        form = ApplicationAttachmentUploadForm(request.POST, request.FILES)
        if not form.is_valid():
            messages.error(request, "; ".join(form.errors.get("file", []) + form.errors.get("file_name", [])) or "Choose a valid file before uploading.")
            return HttpResponseRedirect(reverse("ui:master-entry-institution-edit", kwargs={"application_number": application_number}))

        existing_count = models.ApplicationAttachment.objects.filter(
            application_type=models.ApplicationAttachmentTypeChoices.INSTITUTION,
            institution_application_number=application_number,
        ).count()
        if existing_count >= ApplicationAttachmentUploadForm.MAX_FILES_PER_APPLICATION:
            messages.error(request, f"Maximum {ApplicationAttachmentUploadForm.MAX_FILES_PER_APPLICATION} files are allowed for one application.")
            return HttpResponseRedirect(reverse("ui:master-entry-institution-edit", kwargs={"application_number": application_number}))

        uploaded = form.cleaned_data["file"]
        display_name = _prefixed_attachment_name(application_number, uploaded.name, form.cleaned_data.get("file_name") or "")
        models.ApplicationAttachment.objects.create(
            application_type=models.ApplicationAttachmentTypeChoices.INSTITUTION,
            institution_application_number=application_number,
            file=uploaded,
            file_name=display_name,
            uploaded_by=request.user,
        )
        messages.success(request, "Attachment uploaded.")
        return HttpResponseRedirect(reverse("ui:master-entry-institution-edit", kwargs={"application_number": application_number}))


class InstitutionApplicationAttachmentDeleteView(LoginRequiredMixin, WriteRoleMixin, View):
    def post(self, request, *args, **kwargs):
        application_number = kwargs["application_number"]
        attachment = get_object_or_404(
            models.ApplicationAttachment,
            pk=kwargs["attachment_id"],
            application_type=models.ApplicationAttachmentTypeChoices.INSTITUTION,
            institution_application_number=application_number,
        )
        if attachment.file:
            attachment.file.delete(save=False)
        attachment.delete()
        messages.success(request, "Attachment removed.")
        return HttpResponseRedirect(reverse("ui:master-entry-institution-edit", kwargs={"application_number": application_number}))


def _is_editable_by_user(user, fr):
    if not user or not user.is_authenticated:
        return False
    if user.role == "admin":
        return True
    return fr.status == models.FundRequestStatusChoices.DRAFT


FundRequestRecipientFormSet = inlineformset_factory(
    models.FundRequest,
    models.FundRequestRecipient,
    form=FundRequestRecipientForm,
    extra=2,
    can_delete=True,
)

FundRequestArticleFormSet = inlineformset_factory(
    models.FundRequest,
    models.FundRequestArticle,
    form=FundRequestArticleForm,
    extra=3,
    can_delete=True,
)


class FundRequestListView(LoginRequiredMixin, RoleRequiredMixin, ListView):
    model = models.FundRequest
    template_name = "dashboard/fund_request_list.html"
    context_object_name = "fund_requests"
    paginate_by = 20

    def get_queryset(self):
        queryset = (
            models.FundRequest.objects.select_related("created_by")
            .prefetch_related("recipients", "articles", "documents")
            .order_by("-created_at")
        )
        if q := self.request.GET.get("q"):
            queryset = queryset.filter(fund_request_number__icontains=q)
        return queryset


class FundRequestCreateUpdateMixin(WriteRoleMixin):
    form_class = FundRequestForm
    template_name = "dashboard/fund_request_form.html"
    model = models.FundRequest
    success_url = reverse_lazy("ui:fund-request-list")

    def _build_formsets(self, instance: models.FundRequest | None = None):
        recipient_formset = FundRequestRecipientFormSet(self.request.POST or None, prefix="recipients", instance=instance)
        article_formset = FundRequestArticleFormSet(self.request.POST or None, prefix="articles", instance=instance)
        return recipient_formset, article_formset

    def _can_edit(self, fr: models.FundRequest):
        return _is_editable_by_user(self.request.user, fr)

    def dispatch(self, request, *args, **kwargs):
        self.object = getattr(self, "object", None)
        if self.object and not self._can_edit(self.object):
            messages.error(request, "Only admins can edit non-draft fund requests.")
            return HttpResponseRedirect(reverse("ui:fund-request-detail", args=[self.object.pk]))
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["recipient_formset"] = kwargs.get("recipient_formset", None) or self._build_formsets(self.object)[0]
        context["article_formset"] = kwargs.get("article_formset", None) or self._build_formsets(self.object)[1]
        context["status_choices"] = models.FundRequestStatusChoices.choices
        return context

    def _collect_totals(self, instance: models.FundRequest):
        for article in instance.articles.all():
            article.recompute_totals(unit_price=article.unit_price, quantity=article.quantity)
        services.sync_fund_request_totals(instance)

    def _finalize_status(self, fr: models.FundRequest, action: str):
        if action == "submit":
            fr.status = models.FundRequestStatusChoices.SUBMITTED
            if not fr.fund_request_number:
                fr.fund_request_number = services.next_fund_request_number()
        elif not fr.status:
            fr.status = models.FundRequestStatusChoices.DRAFT

    def form_valid(self, form):
        action = self.request.POST.get("action", "draft")
        if action == "submit" and self.object and self.object.status != models.FundRequestStatusChoices.DRAFT:
            messages.error(self.request, "Only draft fund requests can be submitted.")
            return HttpResponseRedirect(self.get_success_url())
        with transaction.atomic():
            fr = form.save(commit=False)
            if not fr.created_by:
                fr.created_by = self.request.user
            self._finalize_status(fr, action)
            fr.save()
            recipient_formset, article_formset = self._build_formsets(fr)
            if recipient_formset.is_valid() and article_formset.is_valid():
                recipient_formset.instance = fr
                article_formset.instance = fr
                recipient_formset.save()
                article_formset.save()
                self._collect_totals(fr)
                if action == "submit":
                    services.log_audit(
                        user=self.request.user,
                        action_type=models.ActionTypeChoices.STATUS_CHANGE,
                        entity_type="fund_request",
                        entity_id=str(fr.id),
                        details={"status": models.FundRequestStatusChoices.SUBMITTED},
                        ip_address=self.request.META.get("REMOTE_ADDR"),
                        user_agent=self.request.META.get("HTTP_USER_AGENT", ""),
                    )
                if action == "submit":
                    messages.success(self.request, "Fund request submitted.")
                else:
                    messages.success(self.request, "Fund request saved as draft.")
                return HttpResponseRedirect(self.get_success_url())
            messages.error(self.request, "Please fix errors in recipients/articles before saving.")
            return self.render_to_response(self.get_context_data(form=form, recipient_formset=recipient_formset, article_formset=article_formset))


class FundRequestCreateView(LoginRequiredMixin, FundRequestCreateUpdateMixin, CreateView):
    pass


class FundRequestUpdateView(LoginRequiredMixin, FundRequestCreateUpdateMixin, UpdateView):
    pass


class FundRequestDetailView(LoginRequiredMixin, RoleRequiredMixin, DetailView):
    model = models.FundRequest
    template_name = "dashboard/fund_request_detail.html"
    context_object_name = "fund_request"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["media_url"] = settings.MEDIA_URL
        context["can_edit"] = self.request.user.role in {"admin", "editor"} and (
            self.request.user.role == "admin" or self.object.status == models.FundRequestStatusChoices.DRAFT
        )
        return context


class FundRequestDeleteView(LoginRequiredMixin, AdminRequiredMixin, DeleteView):
    model = models.FundRequest
    template_name = "dashboard/fund_request_confirm_delete.html"
    success_url = reverse_lazy("ui:fund-request-list")

    def post(self, request, *args, **kwargs):
        messages.warning(self.request, "Fund request deleted.")
        return super().post(request, *args, **kwargs)


class FundRequestSubmitView(LoginRequiredMixin, WriteRoleMixin, View):
    allowed_roles = {"admin", "editor"}

    def post(self, request, pk):
        fr = models.FundRequest.objects.get(pk=pk)
        if not _is_editable_by_user(request.user, fr) or request.user.role == "viewer":
            return HttpResponse("Forbidden", status=403)
        if fr.status != models.FundRequestStatusChoices.DRAFT:
            messages.error(request, "Only draft fund requests can be submitted.")
            return HttpResponseRedirect(reverse("ui:fund-request-detail", args=[fr.pk]))
        fr.status = models.FundRequestStatusChoices.SUBMITTED
        if not fr.fund_request_number:
            fr.fund_request_number = services.next_fund_request_number()
        fr.save(update_fields=["status", "fund_request_number"])
        services.log_audit(
            user=request.user,
            action_type=models.ActionTypeChoices.STATUS_CHANGE,
            entity_type="fund_request",
            entity_id=str(fr.id),
            details={"status": models.FundRequestStatusChoices.SUBMITTED},
            ip_address=request.META.get("REMOTE_ADDR"),
            user_agent=request.META.get("HTTP_USER_AGENT", ""),
        )
        services.sync_fund_request_totals(fr)
        messages.success(request, "Fund request submitted.")
        return HttpResponseRedirect(reverse("ui:fund-request-detail", args=[fr.pk]))


class FundRequestDocumentUploadView(LoginRequiredMixin, WriteRoleMixin, FormView):
    template_name = "dashboard/fund_request_upload_document.html"
    form_class = FundRequestDocumentUploadForm

    def dispatch(self, request, *args, **kwargs):
        self.fund_request = models.FundRequest.objects.get(pk=kwargs["pk"])
        if not _is_editable_by_user(request.user, self.fund_request):
            return HttpResponse("Forbidden", status=403)
        return super().dispatch(request, *args, **kwargs)

    def get_success_url(self):
        return reverse("ui:fund-request-detail", args=[self.fund_request.pk])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["fund_request"] = self.fund_request
        return context

    def form_valid(self, form):
        uploaded_file = form.cleaned_data["file"]
        upload_dir = os.path.join("fund-request-docs", str(self.fund_request.pk))
        relative_path = os.path.join(upload_dir, uploaded_file.name)
        from django.core.files.storage import default_storage

        stored_path = default_storage.save(relative_path, uploaded_file)
        models.FundRequestDocument.objects.create(
            fund_request=self.fund_request,
            document_type=form.cleaned_data["document_type"],
            file_path=stored_path,
            file_name=uploaded_file.name,
            generated_by=self.request.user,
        )
        messages.success(self.request, "Document uploaded.")
        return HttpResponseRedirect(self.get_success_url())


class MasterDataBaseView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    template_name = "dashboard/module_master_data.html"
    data_key = None
    page_title = "Master Data"
    upload_help = "Upload a CSV file to refresh the stored records."

    def dispatch(self, request, *args, **kwargs):
        if not self.data_key:
            raise ValueError("MasterDataBaseView requires data_key")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "active_data_key": self.data_key,
                "page_title": self.page_title,
                "upload_help": self.upload_help,
                "upload_form": kwargs.get("upload_form") or MasterDataUploadForm(),
                "records": kwargs.get("records") if kwargs.get("records") is not None else self.get_records(),
                "summary": self.get_summary(),
                "replace_supported": self.data_key == "history",
            }
        )
        return context

    def get_records(self):
        if self.data_key == "districts":
            return list(models.DistrictMaster.objects.order_by("district_name")[:100])
        if self.data_key == "articles":
            return list(models.Article.objects.order_by("article_name")[:100])
        return list(models.PublicBeneficiaryHistory.objects.order_by("-year", "-created_at")[:100])

    def get_summary(self):
        return {
            "districts": models.DistrictMaster.objects.count(),
            "articles": models.Article.objects.count(),
            "history": models.PublicBeneficiaryHistory.objects.count(),
        }

    def post(self, request, *args, **kwargs):
        if request.user.role not in {models.RoleChoices.ADMIN, models.RoleChoices.EDITOR}:
            messages.error(request, "You do not have permission to upload master data files.")
            return HttpResponseRedirect(request.path)

        form = MasterDataUploadForm(request.POST, request.FILES)
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(upload_form=form))

        uploaded = form.cleaned_data["file"]
        replace_existing = bool(form.cleaned_data.get("replace_existing"))
        inserted, updated = self.import_rows(uploaded, replace_existing=replace_existing)
        messages.success(request, f"{self.page_title} import complete. inserted={inserted}, updated={updated}")
        return HttpResponseRedirect(request.path)

    def import_rows(self, uploaded_file, *, replace_existing=False):
        if self.data_key == "districts":
            return _import_district_master_csv(uploaded_file)
        if self.data_key == "articles":
            return _import_article_master_csv(uploaded_file)
        return _import_public_history_csv(uploaded_file, replace_existing=replace_existing)


class MasterDataDistrictView(MasterDataBaseView):
    data_key = "districts"
    page_title = "District Master"
    upload_help = "Upload the yearly district president file. The district code, president, budget, and mobile number will be updated in place."


class MasterDataArticleView(MasterDataBaseView):
    data_key = "articles"
    page_title = "Article Price List"
    upload_help = "Upload the latest article price list. Existing article names are updated; new article names are added."


class MasterDataHistoryView(MasterDataBaseView):
    data_key = "history"
    page_title = "Past Beneficiary History"
    upload_help = "Upload the past district/public beneficiary file. This is used for Aadhaar warnings and reference checks during entry."


def _csv_reader_from_upload(uploaded_file):
    uploaded_file.seek(0)
    return csv.DictReader(io.StringIO(uploaded_file.read().decode("utf-8-sig")))


def _import_district_master_csv(uploaded_file):
    inserted = 0
    updated = 0
    for row in _csv_reader_from_upload(uploaded_file):
        district_name = (row.get("district_name") or "").strip()
        if not district_name:
            continue
        budget_raw = (row.get("allotted_budget") or "0").strip().replace(",", "")
        allotted_budget = Decimal(budget_raw or "0")
        _, created = models.DistrictMaster.objects.update_or_create(
            district_name=district_name,
            defaults={
                "application_number": (row.get("application_number") or "").strip(),
                "allotted_budget": allotted_budget,
                "president_name": (row.get("president_name") or "").strip(),
                "mobile_number": (row.get("mobile_number") or "").strip(),
                "is_active": True,
            },
        )
        inserted += int(created)
        updated += int(not created)
    return inserted, updated


def _import_article_master_csv(uploaded_file):
    inserted = 0
    updated = 0
    valid_item_types = {choice for choice, _ in models.ItemTypeChoices.choices}
    for row in _csv_reader_from_upload(uploaded_file):
        article_name = (row.get("article_name") or "").strip()
        if not article_name:
            continue
        cost_raw = (row.get("cost_per_unit") or "0").strip().replace(",", "")
        cost_per_unit = Decimal(cost_raw or "0")
        item_type = (row.get("item_type") or models.ItemTypeChoices.ARTICLE).strip()
        if item_type not in valid_item_types:
            item_type = models.ItemTypeChoices.ARTICLE
        is_active_value = (row.get("is_active") or "").strip().lower()
        is_active = is_active_value in {"active", "true", "1", "yes"}
        _, created = models.Article.objects.update_or_create(
            article_name=article_name,
            defaults={
                "cost_per_unit": cost_per_unit,
                "item_type": item_type,
                "category": (row.get("category") or "").strip() or None,
                "master_category": (row.get("master_category") or "").strip() or None,
                "is_active": is_active,
            },
        )
        inserted += int(created)
        updated += int(not created)
    return inserted, updated


def _import_public_history_csv(uploaded_file, *, replace_existing=False):
    inserted = 0
    if replace_existing:
        models.PublicBeneficiaryHistory.objects.all().delete()
    for row in _csv_reader_from_upload(uploaded_file):
        year_raw = (row.get("year") or "").strip()
        if not year_raw:
            continue
        models.PublicBeneficiaryHistory.objects.create(
            aadhar_number=(row.get("aadhar_number") or "").strip(),
            name=(row.get("name") or "").strip(),
            year=int(year_raw),
            article_name=(row.get("article_name") or "").strip() or None,
            application_number=(row.get("application_number") or "").strip() or None,
            comments=(row.get("comments") or "").strip() or None,
            is_handicapped=_parse_bool(row.get("is_handicapped")),
            address=(row.get("address") or "").strip() or None,
            mobile=(row.get("mobile") or "").strip() or None,
            aadhar_number_sp=(row.get("aadhar_number_sp") or "").strip() or None,
            is_selected=_parse_bool(row.get("is_selected")),
            category=(row.get("category") or "").strip() or None,
        )
        inserted += 1
    return inserted, 0


def _parse_bool(value):
    text = str(value or "").strip().lower()
    if text in {"true", "1", "yes"}:
        return True
    if text in {"false", "0", "no"}:
        return False
    return None
