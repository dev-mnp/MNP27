from __future__ import annotations

"""Application entry views and helpers for beneficiary entry workflows."""

import base64
import csv
import json
import logging
import mimetypes
import os
import uuid
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.postgres.aggregates import StringAgg
from django.db import transaction
from django.db.models import Count, Max, OuterRef, Q, Subquery, Sum, TextField, Value
from django.db.models.functions import Coalesce
from django.http import FileResponse, Http404, HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView

from core import models
from core.application_entry import google_drive
from core.application_entry.forms import ApplicationAttachmentUploadForm
from core.base_files import services as base_file_services
from core.shared.permissions import AdminRequiredMixin, RoleRequiredMixin, WriteRoleMixin
from core.shared.article_suggestions import get_article_text_suggestions
from core.shared.audit import get_request_audit_meta
from core.shared.audit import log_audit

logger = logging.getLogger(__name__)
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


def _available_attachment_q():
    return Q(drive_file_id__gt="") | ~Q(file="")


def _mark_attachment_unavailable(attachment):
    if not attachment:
        return
    update_fields = []
    if attachment.drive_file_id:
        attachment.drive_file_id = ""
        update_fields.append("drive_file_id")
    if attachment.drive_mime_type:
        attachment.drive_mime_type = ""
        update_fields.append("drive_mime_type")
    if attachment.drive_view_url:
        attachment.drive_view_url = ""
        update_fields.append("drive_view_url")
    if update_fields:
        attachment.save(update_fields=update_fields)


def _is_probably_missing_drive_file_error(exc: Exception) -> bool:
    message = str(exc or "").lower()
    missing_markers = (
        "404",
        "not found",
        "filenotfound",
        "file not found",
        "requested entity was not found",
    )
    return any(marker in message for marker in missing_markers)


def _public_active_queryset():
    return models.PublicBeneficiaryEntry.objects.active()


def _public_any_queryset():
    return models.PublicBeneficiaryEntry.objects.all()


def _public_visible_queryset(status_filter: str = ""):
    normalized = (status_filter or "").strip().lower()
    if normalized == models.BeneficiaryStatusChoices.ARCHIVED:
        return models.PublicBeneficiaryEntry.objects.archived()
    if normalized in {models.BeneficiaryStatusChoices.DRAFT, models.BeneficiaryStatusChoices.SUBMITTED}:
        return _public_active_queryset()
    return _public_any_queryset()

class MasterEntryView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    module_key = models.ModuleKeyChoices.APPLICATION_ENTRY
    permission_action = "view"
    template_name = "application_entry/module_master_entry.html"

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

        # IMPORTANT: This page can get very large (lots of rows + attachment metadata + hidden detail tables).
        # Only build the dataset that is currently selected, and lazy-load expanded row details.
        district_groups = []
        public_entries = []
        institution_groups = []

        context["beneficiary_type"] = beneficiary_type
        context["search_query"] = search_query
        context["date_from"] = date_from
        context["date_to"] = date_to
        context["status_filter"] = status_filter
        context["status_choices"] = [
            ("", "All Statuses"),
            (models.BeneficiaryStatusChoices.DRAFT, "Draft"),
            (models.BeneficiaryStatusChoices.SUBMITTED, "Submitted"),
            (models.BeneficiaryStatusChoices.ARCHIVED, "Archived"),
        ]
        context["sort_by"] = sort_by
        context["sort_dir"] = sort_dir

        district_count = models.DistrictBeneficiaryEntry.objects.values("district_id").distinct().count()
        public_count = _public_active_queryset().count()
        public_archived_count = models.PublicBeneficiaryEntry.objects.archived().count()
        institution_count = models.InstitutionsBeneficiaryEntry.objects.values("application_number").distinct().count()
        district_row_count = models.DistrictBeneficiaryEntry.objects.count()
        public_row_count = _public_active_queryset().count()
        institution_row_count = models.InstitutionsBeneficiaryEntry.objects.count()
        counts = {
            "district_count": district_count,
            "public_count": public_count,
            "institution_count": institution_count,
            "total_material_rows": district_row_count + public_row_count + institution_row_count,
        }

        context.update(counts)
        context["public_archived_count"] = public_archived_count
        context["grouped_material_rows"] = (
            int(counts.get("district_count") or 0)
            + int(counts.get("public_count") or 0)
            + int(counts.get("institution_count") or 0)
        )

        if beneficiary_type == "district":
            district_groups = _filter_sort_district_summaries(
                _build_district_entry_summaries(),
                search_query=search_query,
                date_from=date_from,
                date_to=date_to,
                status_filter=status_filter,
                sort_by=sort_by,
                sort_dir=sort_dir,
            )
        elif beneficiary_type == "public":
            public_entries = _filter_sort_public_entries(
                _public_visible_queryset(status_filter=status_filter).select_related("article").all(),
                search_query=search_query,
                date_from=date_from,
                date_to=date_to,
                status_filter=status_filter,
                sort_by=sort_by,
                sort_dir=sort_dir,
            )
            public_entries = list(public_entries)
            public_attachment_latest, public_attachment_counts = _public_attachment_latest_and_counts(
                [entry.id for entry in public_entries]
            )
            for entry in public_entries:
                attachment = public_attachment_latest.get(entry.id)
                entry.attachment_id = attachment.id if attachment else None
                entry.attachment_preview_url = reverse("ui:application-attachment-download", kwargs={"attachment_id": attachment.id}) if attachment else ""
                entry.attachment_source = _attachment_preview_source(attachment)
                entry.attachment_title = _attachment_preview_title(attachment)
                entry.attachment_count = public_attachment_counts.get(entry.id, 0)
        elif beneficiary_type == "institutions":
            institution_groups = _filter_sort_institution_summaries(
                _build_institution_entry_summaries(),
                search_query=search_query,
                date_from=date_from,
                date_to=date_to,
                status_filter=status_filter,
                sort_by=sort_by,
                sort_dir=sort_dir,
            )

        context["district_groups"] = district_groups
        context["public_entries"] = public_entries
        context["institution_groups"] = institution_groups
        context["district_total_accrued"] = sum((row.get("total_accrued") or 0) for row in district_groups)
        context["public_total_accrued"] = sum((entry.total_amount or 0) for entry in public_entries)
        context["institution_total_accrued"] = sum((row.get("total_value") or 0) for row in institution_groups)
        context["public_submit_popup"] = self.request.session.pop("public_submit_popup", None)
        context["institution_submit_popup"] = self.request.session.pop("institution_submit_popup", None)
        return context


class DistrictMasterEntryInlineSummaryView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    module_key = models.ModuleKeyChoices.APPLICATION_ENTRY
    permission_action = "view"
    template_name = "application_entry/partials/master_entry_district_summary.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        district = models.DistrictMaster.objects.get(pk=self.kwargs["district_id"], is_active=True)
        entries = list(
            models.DistrictBeneficiaryEntry.objects.filter(district=district).select_related("article").order_by("id")
        )
        context["district"] = district
        context["entries"] = entries
        context["internal_notes"] = entries[0].internal_notes if entries else ""
        return context


class PublicMasterEntryInlineSummaryView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    module_key = models.ModuleKeyChoices.APPLICATION_ENTRY
    permission_action = "view"
    template_name = "application_entry/partials/master_entry_public_summary.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        entry = _public_any_queryset().select_related("article").get(pk=self.kwargs["pk"])
        history_summary = _public_history_summary(_public_history_matches(entry.aadhar_number))
        context["entry"] = entry
        context["history_summary"] = history_summary
        return context


class InstitutionsMasterEntryInlineSummaryView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    module_key = models.ModuleKeyChoices.APPLICATION_ENTRY
    permission_action = "view"
    template_name = "application_entry/partials/master_entry_institution_summary.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        application_number = self.kwargs["application_number"]
        entries = list(
            models.InstitutionsBeneficiaryEntry.objects.filter(application_number=application_number).select_related("article").order_by("id")
        )
        context["application_number"] = application_number
        context["entries"] = entries
        context["entry_header"] = entries[0] if entries else None
        context["internal_notes"] = entries[0].internal_notes if entries else ""
        return context


def _public_attachment_latest_and_counts(entry_ids):
    if not entry_ids:
        return {}, {}
    attachments = (
        models.ApplicationAttachment.objects.filter(
            application_type=models.ApplicationAttachmentTypeChoices.PUBLIC,
            public_entry_id__in=entry_ids,
        )
        .filter(_available_attachment_q())
        .order_by("public_entry_id", "-created_at", "-id")
    )
    latest_map = {}
    count_map = {}
    for attachment in attachments:
        entry_id = attachment.public_entry_id
        count_map[entry_id] = count_map.get(entry_id, 0) + 1
        if entry_id not in latest_map:
            latest_map[entry_id] = attachment
    return latest_map, count_map


def _district_attachment_latest_and_counts(district_ids):
    if not district_ids:
        return {}, {}
    attachments = (
        models.ApplicationAttachment.objects.filter(
            application_type=models.ApplicationAttachmentTypeChoices.DISTRICT,
            district_id__in=district_ids,
        )
        .filter(_available_attachment_q())
        .order_by("district_id", "-created_at", "-id")
    )
    latest_map = {}
    count_map = {}
    for attachment in attachments:
        district_id = attachment.district_id
        count_map[district_id] = count_map.get(district_id, 0) + 1
        if district_id not in latest_map:
            latest_map[district_id] = attachment
    return latest_map, count_map


def _institution_attachment_latest_and_counts(application_numbers):
    if not application_numbers:
        return {}, {}
    attachments = (
        models.ApplicationAttachment.objects.filter(
            application_type=models.ApplicationAttachmentTypeChoices.INSTITUTION,
            institution_application_number__in=application_numbers,
        )
        .filter(_available_attachment_q())
        .order_by("institution_application_number", "-created_at", "-id")
    )
    latest_map = {}
    count_map = {}
    for attachment in attachments:
        key = attachment.institution_application_number
        if not key:
            continue
        count_map[key] = count_map.get(key, 0) + 1
        if key not in latest_map:
            latest_map[key] = attachment
    return latest_map, count_map


def _reconciliation_parse_decimal(value):
    raw = str(value or "").replace(",", "").strip()
    try:
        return Decimal(raw or "0")
    except (InvalidOperation, ValueError):
        return Decimal("0")


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
    "Name of Beneficiary",
    "Name of Institution",
    "Cheque / RTGS in Favour",
    "Handicapped Status",
    "Gender",
    "Gender Category",
    "Beneficiary Type",
    "Item Type",
    "Article Category",
    "Super Category Article",
    "Token Name",
    "Internal Notes",
    "Comments",
]

TOKEN_GENERATION_NUMERIC_HEADERS = {
    "Quantity",
    "Cost Per Unit",
    "Total Value",
    "Mobile",
    "Aadhar Number",
    "Waiting Hall Quantity",
    "Token Quantity",
    "Sequence No",
}

TOKEN_GENERATION_BENEFICIARY_ORDER = {
    "Institutions": 0,
    "Public": 1,
    "District": 2,
}

TOKEN_GENERATION_RENAME_MAP = {
    "I001 - Government Leprosy Centre,Chengalpattu.": "I001-Govt Leprosy Centre,CGL",
    "I002 - Athivakkam,Panchayat Union Primary School.": "I002-Athivakkam,Panchayat School",
    "I003 - Thirukazhukundram,Govt Girls Higher Secondary School.": "I003-Thirukazhukundram,Govt Girls School",
    "I004 - Acharapakkam,Govt Girls Higher Secondary School.": "I004-Acharapakkam,Govt Girls School",
    "I005 - Maduranthagam,District Educational Office.": "I005-Maduranthagam,District Edu Off",
    "I006 - Thozhupedu,Govt Higher Secondary School.": "I006-Thozhupedu,Govt School",
    "I007 - Kayappakkam,Government Higher Secondary School.": "I007-Kayappakkam,Government School",
    "I008 - Nolambur Government Higher SecondarySchool": "I008-Nolambur Government School",
    "I009 - Acharapakkam, Govt Boys Higher Secondary School.": "I009-Acharapakkam,Govt Boys School",
    "I010 - Cheyyur Govt Girls Higher Secondary School.": "I010-Cheyyur Govt Girls School",
    "I011 - Chunambedu Govt Higher Secondary School.": "I011-Chunambedu Govt School",
    "I012 - Avanippur Government Higher Secondary School": "I012-Avanippur Government School",
    "I013 - Polambakkam Govt Higher Secondary School.": "I013-Polambakkam Govt School",
}

TOKEN_GENERATION_ARTICLE_PRINT_EXCLUDES = {
    "Plant Sapling",
    "Provision items",
    "Aluminium holed rice strainer with Handle",
    "Goat(1 Pair)",
    "Ortho Caliper",
    "Fishing Net",
    "Grocery Items",
    "Artificial leg",
    "Cow & Calf",
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


def _attachment_name_exists(queryset, final_name):
    normalized = (final_name or "").strip().lower()
    if not normalized:
        return False
    for existing_name in queryset.values_list("file_name", flat=True):
        if (existing_name or "").strip().lower() == normalized:
            return True
    return False


def _attachment_application_reference(attachment):
    if not attachment:
        return ""
    if attachment.application_type == models.ApplicationAttachmentTypeChoices.DISTRICT and attachment.district_id:
        return attachment.district.application_number or ""
    if attachment.application_type == models.ApplicationAttachmentTypeChoices.PUBLIC and attachment.public_entry_id:
        return attachment.public_entry.application_number or f"PUBLIC-{attachment.public_entry_id}"
    if attachment.application_type == models.ApplicationAttachmentTypeChoices.INSTITUTION:
        return attachment.institution_application_number or ""
    return ""


def _save_application_attachment(*, uploaded, display_name, application_type, uploaded_by, district=None, public_entry=None, institution_application_number=None):
    from django.conf import settings

    attachment_kwargs = {
        "application_type": application_type,
        "district": district,
        "public_entry": public_entry,
        "institution_application_number": institution_application_number,
        "file_name": display_name,
        "uploaded_by": uploaded_by,
    }
    application_reference = (
        (district.application_number if district else "")
        or (public_entry.application_number if public_entry else "")
        or institution_application_number
        or ""
    )
    if google_drive.is_configured():
        drive_file = google_drive.upload_application_attachment(
            content=uploaded.read(),
            display_name=display_name,
            content_type=str(getattr(uploaded, "content_type", "") or mimetypes.guess_type(display_name)[0] or "application/octet-stream"),
            application_type=application_type,
            application_reference=application_reference,
        )
        attachment_kwargs.update(
            {
                "drive_file_id": str(drive_file.get("file_id") or "").strip(),
                "drive_mime_type": str(drive_file.get("mime_type") or "").strip(),
                "drive_view_url": str(drive_file.get("view_url") or "").strip(),
            }
        )
    else:
        # In production (Cloud Run), local filesystem uploads are ephemeral and will be lost.
        # Require Google Drive configuration in non-debug environments to avoid false success.
        if settings.DEBUG:
            attachment_kwargs["file"] = uploaded
        else:
            raise RuntimeError("Google Drive is not configured for attachments in this environment.")
    return models.ApplicationAttachment.objects.create(**attachment_kwargs)


def _delete_application_attachment_file(attachment):
    try:
        if attachment.drive_file_id:
            google_drive.delete_file(attachment.drive_file_id)
        elif attachment.file:
            attachment.file.delete(save=False)
    except Exception:
        logger.exception("Failed to delete attachment file (id=%s). Continuing.", getattr(attachment, "id", None))


def _rename_attachment_display_names_for_reference(*, attachments_qs, new_reference):
    for attachment in attachments_qs:
        current_name = (attachment.file_name or "").strip()
        if not current_name:
            continue
        if "_" in current_name:
            _, suffix = current_name.split("_", 1)
        else:
            suffix = current_name
        attachment.file_name = f"{new_reference}_{suffix}" if suffix else new_reference
        attachment.save(update_fields=["file_name"])


def _save_attachment_from_main_form(
    *,
    request,
    application_type,
    application_reference,
    uploaded_by,
    district=None,
    public_entry=None,
    institution_application_number=None,
):
    if "file" not in request.FILES:
        return

    form = ApplicationAttachmentUploadForm(request.POST, request.FILES)
    if not form.is_valid():
        messages.error(
            request,
            "; ".join(form.errors.get("file", []) + form.errors.get("file_name", []))
            or "Choose a valid file before saving.",
        )
        return

    filters = {
        "application_type": application_type,
        "status": models.ApplicationAttachmentStatusChoices.LINKED,
    }
    if district is not None:
        filters["district"] = district
    if public_entry is not None:
        filters["public_entry"] = public_entry
    if institution_application_number is not None:
        filters["institution_application_number"] = institution_application_number

    attachments_qs = models.ApplicationAttachment.objects.filter(**filters)
    existing_count = attachments_qs.count()
    if existing_count >= ApplicationAttachmentUploadForm.MAX_FILES_PER_APPLICATION:
        messages.error(
            request,
            f"Maximum {ApplicationAttachmentUploadForm.MAX_FILES_PER_APPLICATION} files are allowed for one application.",
        )
        return

    uploaded = form.cleaned_data["file"]
    display_name = _prefixed_attachment_name(
        application_reference,
        uploaded.name,
        form.cleaned_data.get("file_name") or "",
    )
    if _attachment_name_exists(attachments_qs, display_name):
        messages.error(
            request,
            "A file with this name already exists for this application. Please rename it before saving.",
        )
        return
    try:
        _save_application_attachment(
            uploaded=uploaded,
            display_name=display_name,
            application_type=application_type,
            uploaded_by=uploaded_by,
            district=district,
            public_entry=public_entry,
            institution_application_number=institution_application_number,
        )
    except Exception:
        logger.exception("Attachment save failed for %s", application_reference)
        if not google_drive.is_configured():
            messages.error(
                request,
                "Google Drive is not configured for uploads in this environment. "
                "Set GOOGLE_DRIVE_APPLICATIONS_FOLDER_ID, GOOGLE_DRIVE_CLIENT_ID, "
                "GOOGLE_DRIVE_CLIENT_SECRET, and GOOGLE_DRIVE_REFRESH_TOKEN.",
            )
        else:
            messages.error(request, "Attachment save failed. Please check Google Drive configuration and try again.")
        return
    messages.success(request, "Attachment saved with application.")


def _attachment_session_token_key(application_type):
    return f"application_attachment_form_token:{application_type}"


def _ensure_attachment_form_token(request, application_type):
    key = _attachment_session_token_key(application_type)
    token = (request.session.get(key) or "").strip()
    if not token:
        token = uuid.uuid4().hex
        request.session[key] = token
        request.session.modified = True
    return token


def _clear_attachment_form_token(request, application_type):
    key = _attachment_session_token_key(application_type)
    if key in request.session:
        del request.session[key]
        request.session.modified = True


def _attachment_temp_expiry():
    return timezone.now() + timedelta(hours=24)


def _cleanup_stale_temp_attachments():
    stale = list(
        models.ApplicationAttachment.objects.filter(
            status=models.ApplicationAttachmentStatusChoices.TEMP,
            temp_expires_at__lt=timezone.now(),
        ).only("id", "drive_file_id", "file")
    )
    if not stale:
        return 0
    deleted = 0
    for attachment in stale:
        _delete_application_attachment_file(attachment)
        attachment.delete()
        deleted += 1
    return deleted


def _temp_attachment_queryset(*, application_type, form_token, user):
    return models.ApplicationAttachment.objects.filter(
        application_type=application_type,
        status=models.ApplicationAttachmentStatusChoices.TEMP,
        form_token=form_token,
        uploaded_by=user,
    ).order_by("-created_at", "-id")


def _linked_attachment_queryset(*, application_type, district=None, public_entry=None, institution_application_number=None):
    filters = {
        "application_type": application_type,
        "status": models.ApplicationAttachmentStatusChoices.LINKED,
    }
    if district is not None:
        filters["district"] = district
    if public_entry is not None:
        filters["public_entry"] = public_entry
    if institution_application_number is not None:
        filters["institution_application_number"] = institution_application_number
    return models.ApplicationAttachment.objects.filter(**filters).order_by("-created_at", "-id")


def _save_temp_attachment_upload(*, request, application_type, form_token, application_reference=""):
    form = ApplicationAttachmentUploadForm(request.POST, request.FILES)
    if not form.is_valid():
        messages.error(
            request,
            "; ".join(form.errors.get("file", []) + form.errors.get("file_name", []))
            or "Choose a valid file before uploading.",
        )
        return
    existing_count = _temp_attachment_queryset(
        application_type=application_type,
        form_token=form_token,
        user=request.user,
    ).count()
    if existing_count >= ApplicationAttachmentUploadForm.MAX_FILES_PER_APPLICATION:
        messages.error(
            request,
            f"Maximum {ApplicationAttachmentUploadForm.MAX_FILES_PER_APPLICATION} files are allowed for one application.",
        )
        return
    uploaded = form.cleaned_data["file"]
    raw_name = (form.cleaned_data.get("file_name") or "").strip() or uploaded.name
    display_name = (
        _prefixed_attachment_name(application_reference, uploaded.name, form.cleaned_data.get("file_name") or "")
        if application_reference
        else raw_name
    )
    try:
        attachment = _save_application_attachment(
            uploaded=uploaded,
            display_name=display_name,
            application_type=application_type,
            uploaded_by=request.user,
        )
        attachment.status = models.ApplicationAttachmentStatusChoices.TEMP
        attachment.form_token = form_token
        attachment.temp_expires_at = _attachment_temp_expiry()
        attachment.save(update_fields=["status", "form_token", "temp_expires_at"])
    except Exception:
        logger.exception("Temporary attachment upload failed for %s", application_type)
        if not google_drive.is_configured():
            messages.error(
                request,
                "Google Drive is not configured for uploads in this environment. "
                "Set GOOGLE_DRIVE_APPLICATIONS_FOLDER_ID, GOOGLE_DRIVE_CLIENT_ID, "
                "GOOGLE_DRIVE_CLIENT_SECRET, and GOOGLE_DRIVE_REFRESH_TOKEN.",
            )
        else:
            messages.error(request, "Attachment upload failed. Please check Google Drive configuration and try again.")
        return
    messages.success(request, "Attachment uploaded.")


def _link_temp_attachments_to_application(
    *,
    request,
    application_type,
    form_token,
    application_reference,
    district=None,
    public_entry=None,
    institution_application_number=None,
):
    temp_items = list(
        _temp_attachment_queryset(
            application_type=application_type,
            form_token=form_token,
            user=request.user,
        )
    )
    for attachment in temp_items:
        attachment.status = models.ApplicationAttachmentStatusChoices.LINKED
        attachment.form_token = None
        attachment.temp_expires_at = None
        attachment.file_name = _prefixed_attachment_name(
            application_reference,
            attachment.file_name or "attachment",
            attachment.file_name or "",
        )
        if district is not None:
            attachment.district = district
        if public_entry is not None:
            attachment.public_entry = public_entry
        if institution_application_number is not None:
            attachment.institution_application_number = institution_application_number
        attachment.save()


def _sync_drive_attachments_for_application(
    *,
    application_type,
    application_reference,
    district=None,
    public_entry=None,
    institution_application_number=None,
):
    if not google_drive.is_configured():
        return []
    reference = (application_reference or "").strip()
    if not reference:
        return []
    filters = {
        "application_type": application_type,
        "status": models.ApplicationAttachmentStatusChoices.LINKED,
    }
    if district is not None:
        filters["district"] = district
    if public_entry is not None:
        filters["public_entry"] = public_entry
    if institution_application_number is not None:
        filters["institution_application_number"] = institution_application_number
    attachments = list(
        models.ApplicationAttachment.objects.filter(**filters).select_related("uploaded_by").order_by("-created_at", "-id")
    )
    try:
        drive_files = google_drive.list_application_attachments(
            application_type=application_type,
            application_reference=reference,
        )
    except Exception:
        # Google Drive sync should never break data entry pages.
        # Return current DB attachments without syncing.
        logger.exception("Failed to sync Drive attachments for %s:%s", application_type, reference)
        return attachments
    if not drive_files:
        stale_drive_only_ids = [
            attachment.id
            for attachment in attachments
            if attachment.drive_file_id and not attachment.file
        ]
        if stale_drive_only_ids:
            for stale_attachment in models.ApplicationAttachment.objects.filter(id__in=stale_drive_only_ids):
                _mark_attachment_unavailable(stale_attachment)
        return list(
            models.ApplicationAttachment.objects.filter(**filters)
            .filter(_available_attachment_q())
            .select_related("uploaded_by")
            .order_by("-created_at", "-id")
        )

    def _normalized_name(value):
        return str(value or "").strip().casefold()

    existing_by_id = {
        str(attachment.drive_file_id or "").strip(): attachment
        for attachment in attachments
        if str(attachment.drive_file_id or "").strip()
    }
    available_by_name = {}
    for drive_file in drive_files:
        normalized_name = _normalized_name(drive_file.get("file_name"))
        if normalized_name and normalized_name not in available_by_name:
            available_by_name[normalized_name] = drive_file

    touched_ids = set()
    seen_drive_ids = {
        str(item.get("file_id") or "").strip()
        for item in drive_files
        if str(item.get("file_id") or "").strip()
    }
    for attachment in attachments:
        matched_drive_file = None
        drive_id = str(attachment.drive_file_id or "").strip()
        if drive_id and drive_id in existing_by_id and any(str(item.get("file_id") or "").strip() == drive_id for item in drive_files):
            matched_drive_file = next(
                (item for item in drive_files if str(item.get("file_id") or "").strip() == drive_id),
                None,
            )
        elif not attachment.file:
            matched_drive_file = available_by_name.get(_normalized_name(attachment.file_name))
        if not matched_drive_file:
            continue
        update_fields = []
        matched_id = str(matched_drive_file.get("file_id") or "").strip()
        if attachment.drive_file_id != matched_id:
            attachment.drive_file_id = matched_id
            update_fields.append("drive_file_id")
        matched_mime = str(matched_drive_file.get("mime_type") or "").strip()
        if attachment.drive_mime_type != matched_mime:
            attachment.drive_mime_type = matched_mime
            update_fields.append("drive_mime_type")
        matched_view = str(matched_drive_file.get("view_url") or "").strip()
        if attachment.drive_view_url != matched_view:
            attachment.drive_view_url = matched_view
            update_fields.append("drive_view_url")
        matched_name = str(matched_drive_file.get("file_name") or "").strip()
        if matched_name and attachment.file_name != matched_name:
            attachment.file_name = matched_name
            update_fields.append("file_name")
        if update_fields:
            attachment.save(update_fields=update_fields)
        touched_ids.add(matched_id)

    stale_attachment_ids = []
    for attachment in attachments:
        drive_id = str(attachment.drive_file_id or "").strip()
        if not drive_id:
            continue
        if attachment.file:
            continue
        if drive_id in seen_drive_ids:
            continue
        stale_attachment_ids.append(attachment.id)

    for drive_file in drive_files:
        matched_id = str(drive_file.get("file_id") or "").strip()
        if not matched_id or matched_id in touched_ids:
            continue
        existing_attachment = existing_by_id.get(matched_id)
        if existing_attachment:
            continue
        attachments.append(
            models.ApplicationAttachment.objects.create(
                application_type=application_type,
                district=district,
                public_entry=public_entry,
                institution_application_number=institution_application_number,
                file_name=str(drive_file.get("file_name") or "").strip(),
                drive_file_id=matched_id,
                drive_mime_type=str(drive_file.get("mime_type") or "").strip(),
                drive_view_url=str(drive_file.get("view_url") or "").strip(),
            )
        )

    if stale_attachment_ids:
        for stale_attachment in models.ApplicationAttachment.objects.filter(id__in=stale_attachment_ids):
            _mark_attachment_unavailable(stale_attachment)

    return list(
        models.ApplicationAttachment.objects.filter(**filters)
        .filter(_available_attachment_q())
        .select_related("uploaded_by")
        .order_by("-created_at", "-id")
    )


def _district_attachment_context(district):
    has_saved_application = bool(district and models.DistrictBeneficiaryEntry.objects.filter(district=district).exists())
    attachments = []
    upload_url = ""
    if has_saved_application:
        attachments = _sync_drive_attachments_for_application(
            application_type=models.ApplicationAttachmentTypeChoices.DISTRICT,
            application_reference=district.application_number,
            district=district,
        )
        upload_url = reverse("ui:district-attachment-upload", kwargs={"district_id": district.id})
    return _attachment_upload_context(
        attachments=attachments,
        enabled=has_saved_application,
        upload_url=upload_url,
        helper_text="Upload files related to this district application. You can rename the file before upload.",
    )


def _public_attachment_context(entry):
    has_saved_application = bool(entry and entry.pk)
    attachments = []
    upload_url = ""
    if has_saved_application:
        attachments = _sync_drive_attachments_for_application(
            application_type=models.ApplicationAttachmentTypeChoices.PUBLIC,
            application_reference=entry.application_number or f"PUBLIC-{entry.pk}",
            public_entry=entry,
        )
        upload_url = reverse("ui:public-attachment-upload", kwargs={"pk": entry.pk})
    context = _attachment_upload_context(
        attachments=attachments,
        enabled=has_saved_application,
        upload_url=upload_url,
        helper_text="Upload files related to this public application. You can rename the file before upload.",
    )
    context["entry_id"] = entry.pk if has_saved_application else None
    return context


def _institution_attachment_context(application_number):
    has_saved_application = bool(application_number)
    attachments = []
    upload_url = ""
    if has_saved_application:
        attachments = _sync_drive_attachments_for_application(
            application_type=models.ApplicationAttachmentTypeChoices.INSTITUTION,
            application_reference=application_number,
            institution_application_number=application_number,
        )
        upload_url = reverse("ui:institution-attachment-upload", kwargs={"application_number": application_number})
    return _attachment_upload_context(
        attachments=attachments,
        enabled=has_saved_application,
        upload_url=upload_url,
        helper_text="Upload files related to this institution application. You can rename the file before upload.",
    )


def _district_attachment_preview_data(district_ids):
    if not district_ids:
        return {}, {}
    attachments = (
        models.ApplicationAttachment.objects.filter(
            application_type=models.ApplicationAttachmentTypeChoices.DISTRICT,
            district_id__in=district_ids,
        )
        .filter(_available_attachment_q())
        .order_by("district_id", "-created_at", "-id")
    )
    preview_map = {}
    preview_lists = {}
    for attachment in attachments:
        if attachment.district_id not in preview_map:
            preview_map[attachment.district_id] = attachment
        preview_lists.setdefault(attachment.district_id, []).append(attachment)
    return preview_map, preview_lists


def _district_attachment_preview_map(district_ids):
    preview_map, _preview_lists = _district_attachment_preview_data(district_ids)
    return preview_map


def _district_attachment_preview_lists(district_ids):
    _preview_map, preview_lists = _district_attachment_preview_data(district_ids)
    return preview_lists


def _public_attachment_preview_data(entry_ids):
    if not entry_ids:
        return {}, {}
    attachments = (
        models.ApplicationAttachment.objects.filter(
            application_type=models.ApplicationAttachmentTypeChoices.PUBLIC,
            public_entry_id__in=entry_ids,
        )
        .filter(_available_attachment_q())
        .order_by("public_entry_id", "-created_at", "-id")
    )
    preview_map = {}
    preview_lists = {}
    for attachment in attachments:
        if attachment.public_entry_id not in preview_map:
            preview_map[attachment.public_entry_id] = attachment
        preview_lists.setdefault(attachment.public_entry_id, []).append(attachment)
    return preview_map, preview_lists


def _public_attachment_preview_map(entry_ids):
    preview_map, _preview_lists = _public_attachment_preview_data(entry_ids)
    return preview_map


def _public_attachment_preview_lists(entry_ids):
    _preview_map, preview_lists = _public_attachment_preview_data(entry_ids)
    return preview_lists


def _institution_attachment_preview_data(application_numbers):
    if not application_numbers:
        return {}, {}
    attachments = (
        models.ApplicationAttachment.objects.filter(
            application_type=models.ApplicationAttachmentTypeChoices.INSTITUTION,
            institution_application_number__in=application_numbers,
        )
        .filter(_available_attachment_q())
        .order_by("institution_application_number", "-created_at", "-id")
    )
    preview_map = {}
    preview_lists = {}
    for attachment in attachments:
        key = attachment.institution_application_number
        if key and key not in preview_map:
            preview_map[key] = attachment
        if key:
            preview_lists.setdefault(key, []).append(attachment)
    return preview_map, preview_lists


def _institution_attachment_preview_map(application_numbers):
    preview_map, _preview_lists = _institution_attachment_preview_data(application_numbers)
    return preview_map


def _institution_attachment_preview_lists(application_numbers):
    _preview_map, preview_lists = _institution_attachment_preview_data(application_numbers)
    return preview_lists


def _attachment_preview_title(attachment):
    if not attachment:
        return ""
    if attachment.file_name:
        return attachment.file_name
    if attachment.drive_view_url:
        return "Attachment"
    if attachment.file:
        return os.path.basename(attachment.file.name)
    return ""


def _attachment_preview_payload(attachment):
    if not attachment:
        return None
    preview_url = reverse("ui:application-attachment-download", kwargs={"attachment_id": attachment.id})
    source_name = _attachment_preview_source(attachment)
    return {
        "id": attachment.id,
        "title": _attachment_preview_title(attachment),
        "preview_url": preview_url,
        "download_url": f"{preview_url}?download=1",
        "source": source_name,
    }


def _attachment_preview_source(attachment):
    if not attachment:
        return ""
    if attachment.file and attachment.file.name:
        return (attachment.file.name or "").lower()
    source_name = (attachment.file_name or "").lower()
    mime_type = (attachment.drive_mime_type or "").lower()
    if source_name and "." not in os.path.basename(source_name):
        if mime_type == "application/pdf":
            source_name = f"{source_name}.pdf"
        elif mime_type.startswith("image/"):
            ext = mime_type.split("/", 1)[1].strip()
            if ext == "jpeg":
                ext = "jpg"
            if ext:
                source_name = f"{source_name}.{ext}"
    return source_name


def _attachment_items_b64(items):
    payload = json.dumps(items, ensure_ascii=False)
    return base64.b64encode(payload.encode("utf-8")).decode("ascii")


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
        "internal_notes": (entries[0].internal_notes or "") if entries else "",
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
                "name_of_beneficiary": entry.name_of_beneficiary or "",
                "name_of_institution": entry.name_of_institution or "",
                "aadhar_number": entry.aadhar_number or "",
                "cheque_rtgs_in_favour": entry.cheque_rtgs_in_favour or "",
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
        "is_handicapped": entry.get_is_handicapped_display() if entry.is_handicapped else models.HandicappedStatusChoices.NO,
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
        "name_of_institution": entry.name_of_institution or "",
        "cheque_rtgs_in_favour": entry.cheque_rtgs_in_favour or "",
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
        "internal_notes": first.internal_notes or "",
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
                "name_of_beneficiary": entry.name_of_beneficiary or "",
                "name_of_institution": entry.name_of_institution or "",
                "aadhar_number": entry.aadhar_number or "",
                "cheque_rtgs_in_favour": entry.cheque_rtgs_in_favour or "",
                "notes": entry.notes or "",
            }
            for entry in entries
        ],
    }


def _reconciliation_parse_decimal(value):
    raw = str(value or "").replace(",", "").strip()
    try:
        return Decimal(raw or "0")
    except (InvalidOperation, ValueError):
        return Decimal("0")


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
    "Name of Beneficiary",
    "Name of Institution",
    "Cheque / RTGS in Favour",
    "Handicapped Status",
    "Gender",
    "Gender Category",
    "Beneficiary Type",
    "Item Type",
    "Article Category",
    "Super Category Article",
    "Token Name",
    "Internal Notes",
    "Comments",
]

TOKEN_GENERATION_NUMERIC_HEADERS = {
    "Quantity",
    "Cost Per Unit",
    "Total Value",
    "Mobile",
    "Aadhar Number",
    "Waiting Hall Quantity",
    "Token Quantity",
    "Sequence No",
}

TOKEN_GENERATION_BENEFICIARY_ORDER = {
    "Institutions": 0,
    "Public": 1,
    "District": 2,
}

TOKEN_GENERATION_RENAME_MAP = {
    "I001 - Government Leprosy Centre,Chengalpattu.": "I001-Govt Leprosy Centre,CGL",
    "I002 - Athivakkam,Panchayat Union Primary School.": "I002-Athivakkam,Panchayat School",
    "I003 - Thirukazhukundram,Govt Girls Higher Secondary School.": "I003-Thirukazhukundram,Govt Girls School",
    "I004 - Acharapakkam,Govt Girls Higher Secondary School.": "I004-Acharapakkam,Govt Girls School",
    "I005 - Maduranthagam,District Educational Office.": "I005-Maduranthagam,District Edu Off",
    "I006 - Thozhupedu,Govt Higher Secondary School.": "I006-Thozhupedu,Govt School",
    "I007 - Kayappakkam,Government Higher Secondary School.": "I007-Kayappakkam,Government School",
    "I008 - Nolambur Government Higher SecondarySchool": "I008-Nolambur Government School",
    "I009 - Acharapakkam, Govt Boys Higher Secondary School.": "I009-Acharapakkam,Govt Boys School",
    "I010 - Cheyyur Govt Girls Higher Secondary School.": "I010-Cheyyur Govt Girls School",
    "I011 - Chunambedu Govt Higher Secondary School.": "I011-Chunambedu Govt School",
    "I012 - Avanippur Government Higher Secondary School": "I012-Avanippur Government School",
    "I013 - Polambakkam Govt Higher Secondary School.": "I013-Polambakkam Govt School",
}

TOKEN_GENERATION_ARTICLE_PRINT_EXCLUDES = {
    "Plant Sapling",
    "Provision items",
    "Aluminium holed rice strainer with Handle",
    "Goat(1 Pair)",
    "Ortho Caliper",
    "Fishing Net",
    "Grocery Items",
    "Artificial leg",
    "Cow & Calf",
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


def _attachment_name_exists(queryset, final_name):
    normalized = (final_name or "").strip().lower()
    if not normalized:
        return False
    for existing_name in queryset.values_list("file_name", flat=True):
        if (existing_name or "").strip().lower() == normalized:
            return True
    return False


def _attachment_application_reference(attachment):
    if not attachment:
        return ""
    if attachment.application_type == models.ApplicationAttachmentTypeChoices.DISTRICT and attachment.district_id:
        return attachment.district.application_number or ""
    if attachment.application_type == models.ApplicationAttachmentTypeChoices.PUBLIC and attachment.public_entry_id:
        return attachment.public_entry.application_number or f"PUBLIC-{attachment.public_entry_id}"
    if attachment.application_type == models.ApplicationAttachmentTypeChoices.INSTITUTION:
        return attachment.institution_application_number or ""
    return ""


def _save_application_attachment(*, uploaded, display_name, application_type, uploaded_by, district=None, public_entry=None, institution_application_number=None):
    from django.conf import settings

    attachment_kwargs = {
        "application_type": application_type,
        "district": district,
        "public_entry": public_entry,
        "institution_application_number": institution_application_number,
        "file_name": display_name,
        "uploaded_by": uploaded_by,
    }
    application_reference = (
        (district.application_number if district else "")
        or (public_entry.application_number if public_entry else "")
        or institution_application_number
        or ""
    )
    if google_drive.is_configured():
        drive_file = google_drive.upload_application_attachment(
            content=uploaded.read(),
            display_name=display_name,
            content_type=str(getattr(uploaded, "content_type", "") or mimetypes.guess_type(display_name)[0] or "application/octet-stream"),
            application_type=application_type,
            application_reference=application_reference,
        )
        attachment_kwargs.update(
            {
                "drive_file_id": str(drive_file.get("file_id") or "").strip(),
                "drive_mime_type": str(drive_file.get("mime_type") or "").strip(),
                "drive_view_url": str(drive_file.get("view_url") or "").strip(),
            }
        )
    else:
        # In production (Cloud Run), local filesystem uploads are ephemeral and will be lost.
        # Require Google Drive configuration in non-debug environments to avoid false success.
        if settings.DEBUG:
            attachment_kwargs["file"] = uploaded
        else:
            raise RuntimeError("Google Drive is not configured for attachments in this environment.")
    return models.ApplicationAttachment.objects.create(**attachment_kwargs)


def _delete_application_attachment_file(attachment):
    try:
        if attachment.drive_file_id:
            google_drive.delete_file(attachment.drive_file_id)
        elif attachment.file:
            attachment.file.delete(save=False)
    except Exception:
        logger.exception("Failed to delete attachment file (id=%s). Continuing.", getattr(attachment, "id", None))


def _sync_drive_attachments_for_application(
    *,
    application_type,
    application_reference,
    district=None,
    public_entry=None,
    institution_application_number=None,
):
    if not google_drive.is_configured():
        return []
    reference = (application_reference or "").strip()
    if not reference:
        return []
    filters = {
        "application_type": application_type,
        "status": models.ApplicationAttachmentStatusChoices.LINKED,
    }
    if district is not None:
        filters["district"] = district
    if public_entry is not None:
        filters["public_entry"] = public_entry
    if institution_application_number is not None:
        filters["institution_application_number"] = institution_application_number
    attachments = list(
        models.ApplicationAttachment.objects.filter(**filters).select_related("uploaded_by").order_by("-created_at", "-id")
    )
    try:
        drive_files = google_drive.list_application_attachments(
            application_type=application_type,
            application_reference=reference,
        )
    except Exception:
        # Google Drive sync should never break data entry pages.
        # Return current DB attachments without syncing.
        logger.exception("Failed to sync Drive attachments for %s:%s", application_type, reference)
        return attachments
    if not drive_files:
        stale_drive_only_ids = [
            attachment.id
            for attachment in attachments
            if attachment.drive_file_id and not attachment.file
        ]
        if stale_drive_only_ids:
            models.ApplicationAttachment.objects.filter(id__in=stale_drive_only_ids).delete()
        return list(
            models.ApplicationAttachment.objects.filter(**filters).select_related("uploaded_by").order_by("-created_at", "-id")
        )

    def _normalized_name(value):
        return str(value or "").strip().casefold()

    existing_by_id = {
        str(attachment.drive_file_id or "").strip(): attachment
        for attachment in attachments
        if str(attachment.drive_file_id or "").strip()
    }
    available_by_name = {}
    for drive_file in drive_files:
        normalized_name = _normalized_name(drive_file.get("file_name"))
        if normalized_name and normalized_name not in available_by_name:
            available_by_name[normalized_name] = drive_file

    touched_ids = set()
    seen_drive_ids = {
        str(item.get("file_id") or "").strip()
        for item in drive_files
        if str(item.get("file_id") or "").strip()
    }
    for attachment in attachments:
        matched_drive_file = None
        drive_id = str(attachment.drive_file_id or "").strip()
        if drive_id and drive_id in existing_by_id and any(str(item.get("file_id") or "").strip() == drive_id for item in drive_files):
            matched_drive_file = next(
                (item for item in drive_files if str(item.get("file_id") or "").strip() == drive_id),
                None,
            )
        elif not attachment.file:
            matched_drive_file = available_by_name.get(_normalized_name(attachment.file_name))
        if not matched_drive_file:
            continue
        update_fields = []
        matched_id = str(matched_drive_file.get("file_id") or "").strip()
        if attachment.drive_file_id != matched_id:
            attachment.drive_file_id = matched_id
            update_fields.append("drive_file_id")
        matched_mime = str(matched_drive_file.get("mime_type") or "").strip()
        if attachment.drive_mime_type != matched_mime:
            attachment.drive_mime_type = matched_mime
            update_fields.append("drive_mime_type")
        matched_view = str(matched_drive_file.get("view_url") or "").strip()
        if attachment.drive_view_url != matched_view:
            attachment.drive_view_url = matched_view
            update_fields.append("drive_view_url")
        matched_name = str(matched_drive_file.get("file_name") or "").strip()
        if matched_name and attachment.file_name != matched_name:
            attachment.file_name = matched_name
            update_fields.append("file_name")
        if update_fields:
            attachment.save(update_fields=update_fields)
        touched_ids.add(matched_id)

    stale_attachment_ids = []
    for attachment in attachments:
        drive_id = str(attachment.drive_file_id or "").strip()
        if not drive_id:
            continue
        if attachment.file:
            continue
        if drive_id in seen_drive_ids:
            continue
        stale_attachment_ids.append(attachment.id)

    for drive_file in drive_files:
        matched_id = str(drive_file.get("file_id") or "").strip()
        if not matched_id or matched_id in touched_ids:
            continue
        existing_attachment = existing_by_id.get(matched_id)
        if existing_attachment:
            continue
        attachments.append(
            models.ApplicationAttachment.objects.create(
                application_type=application_type,
                district=district,
                public_entry=public_entry,
                institution_application_number=institution_application_number,
                file_name=str(drive_file.get("file_name") or "").strip(),
                drive_file_id=matched_id,
                drive_mime_type=str(drive_file.get("mime_type") or "").strip(),
                drive_view_url=str(drive_file.get("view_url") or "").strip(),
            )
        )

    if stale_attachment_ids:
        models.ApplicationAttachment.objects.filter(id__in=stale_attachment_ids).delete()

    return list(
        models.ApplicationAttachment.objects.filter(**filters).select_related("uploaded_by").order_by("-created_at", "-id")
    )


def _district_attachment_context(district):
    has_district = bool(district)
    attachments = []
    upload_url = reverse("ui:district-attachment-temp-upload")
    if has_district:
        attachments = _sync_drive_attachments_for_application(
            application_type=models.ApplicationAttachmentTypeChoices.DISTRICT,
            application_reference=district.application_number,
            district=district,
        )
    context = _attachment_upload_context(
        attachments=attachments,
        enabled=has_district,
        upload_url=upload_url,
        helper_text="Upload sends file to Google Drive immediately. Save Draft / Submit saves application data and links uploaded files.",
    )
    context["attachment_district_id"] = district.id if district else ""
    context["attachment_has_temp_uploads"] = False
    return context


def _public_attachment_context(entry):
    has_saved_application = bool(entry and entry.pk)
    attachments = []
    upload_url = ""
    if has_saved_application:
        attachments = _sync_drive_attachments_for_application(
            application_type=models.ApplicationAttachmentTypeChoices.PUBLIC,
            application_reference=entry.application_number or f"PUBLIC-{entry.pk}",
            public_entry=entry,
        )
        upload_url = reverse("ui:public-attachment-upload", kwargs={"pk": entry.pk})
    context = _attachment_upload_context(
        attachments=attachments,
        enabled=True,
        upload_url=upload_url,
        helper_text="Upload sends file to Google Drive immediately. Save Draft / Submit saves application data and links uploaded files.",
    )
    context["attachment_form_token"] = ""
    context["attachment_temp_delete_url"] = reverse("ui:public-attachment-temp-clear")
    context["attachment_upload_url"] = upload_url
    context["entry_id"] = entry.pk if has_saved_application else None
    context["attachment_has_temp_uploads"] = False
    return context


def _public_attachment_context_with_request(request, entry):
    _cleanup_stale_temp_attachments()
    has_saved_application = bool(entry and entry.pk)
    if has_saved_application:
        context = _public_attachment_context(entry)
        return context
    form_token = _ensure_attachment_form_token(request, models.ApplicationAttachmentTypeChoices.PUBLIC)
    temp_items = list(
        _temp_attachment_queryset(
            application_type=models.ApplicationAttachmentTypeChoices.PUBLIC,
            form_token=form_token,
            user=request.user,
        )
    )
    context = _attachment_upload_context(
        attachments=temp_items,
        enabled=True,
        upload_url=reverse("ui:public-attachment-temp-upload"),
        helper_text="Upload sends file to Google Drive immediately. Save Draft / Submit saves application data and links uploaded files.",
    )
    context["attachment_form_token"] = form_token
    context["attachment_temp_delete_url"] = reverse("ui:public-attachment-temp-clear")
    context["attachment_has_temp_uploads"] = bool(temp_items)
    context["entry_id"] = None
    return context


def _institution_attachment_context(application_number):
    _cleanup_stale_temp_attachments()
    has_saved_application = bool(application_number)
    attachments = []
    upload_url = ""
    if has_saved_application:
        attachments = _sync_drive_attachments_for_application(
            application_type=models.ApplicationAttachmentTypeChoices.INSTITUTION,
            application_reference=application_number,
            institution_application_number=application_number,
        )
        upload_url = reverse("ui:institution-attachment-upload", kwargs={"application_number": application_number})
    context = _attachment_upload_context(
        attachments=attachments,
        enabled=True,
        upload_url=upload_url,
        helper_text="Upload sends file to Google Drive immediately. Save Draft / Submit saves application data and links uploaded files.",
    )
    context["attachment_form_token"] = ""
    context["attachment_temp_delete_url"] = reverse("ui:institution-attachment-temp-clear")
    context["attachment_upload_url"] = upload_url
    context["attachment_has_temp_uploads"] = False
    return context


def _institution_attachment_context_with_request(request, application_number):
    _cleanup_stale_temp_attachments()
    has_saved_application = bool(application_number)
    if has_saved_application:
        return _institution_attachment_context(application_number)
    form_token = _ensure_attachment_form_token(request, models.ApplicationAttachmentTypeChoices.INSTITUTION)
    temp_items = list(
        _temp_attachment_queryset(
            application_type=models.ApplicationAttachmentTypeChoices.INSTITUTION,
            form_token=form_token,
            user=request.user,
        )
    )
    context = _attachment_upload_context(
        attachments=temp_items,
        enabled=True,
        upload_url=reverse("ui:institution-attachment-temp-upload"),
        helper_text="Upload sends file to Google Drive immediately. Save Draft / Submit saves application data and links uploaded files.",
    )
    context["attachment_form_token"] = form_token
    context["attachment_temp_delete_url"] = reverse("ui:institution-attachment-temp-clear")
    context["attachment_upload_url"] = reverse("ui:institution-attachment-temp-upload")
    context["attachment_has_temp_uploads"] = bool(temp_items)
    return context


def _district_attachment_preview_data(district_ids):
    if not district_ids:
        return {}, {}
    attachments = (
        models.ApplicationAttachment.objects.filter(
            application_type=models.ApplicationAttachmentTypeChoices.DISTRICT,
            district_id__in=district_ids,
        )
        .order_by("district_id", "-created_at", "-id")
    )
    preview_map = {}
    preview_lists = {}
    for attachment in attachments:
        if attachment.district_id not in preview_map:
            preview_map[attachment.district_id] = attachment
        preview_lists.setdefault(attachment.district_id, []).append(attachment)
    return preview_map, preview_lists


def _district_attachment_preview_map(district_ids):
    preview_map, _preview_lists = _district_attachment_preview_data(district_ids)
    return preview_map


def _district_attachment_preview_lists(district_ids):
    _preview_map, preview_lists = _district_attachment_preview_data(district_ids)
    return preview_lists


def _public_attachment_preview_data(entry_ids):
    if not entry_ids:
        return {}, {}
    attachments = (
        models.ApplicationAttachment.objects.filter(
            application_type=models.ApplicationAttachmentTypeChoices.PUBLIC,
            public_entry_id__in=entry_ids,
        )
        .order_by("public_entry_id", "-created_at", "-id")
    )
    preview_map = {}
    preview_lists = {}
    for attachment in attachments:
        if attachment.public_entry_id not in preview_map:
            preview_map[attachment.public_entry_id] = attachment
        preview_lists.setdefault(attachment.public_entry_id, []).append(attachment)
    return preview_map, preview_lists


def _public_attachment_preview_map(entry_ids):
    preview_map, _preview_lists = _public_attachment_preview_data(entry_ids)
    return preview_map


def _public_attachment_preview_lists(entry_ids):
    _preview_map, preview_lists = _public_attachment_preview_data(entry_ids)
    return preview_lists


def _institution_attachment_preview_data(application_numbers):
    if not application_numbers:
        return {}, {}
    attachments = (
        models.ApplicationAttachment.objects.filter(
            application_type=models.ApplicationAttachmentTypeChoices.INSTITUTION,
            institution_application_number__in=application_numbers,
        )
        .order_by("institution_application_number", "-created_at", "-id")
    )
    preview_map = {}
    preview_lists = {}
    for attachment in attachments:
        key = attachment.institution_application_number
        if key and key not in preview_map:
            preview_map[key] = attachment
        if key:
            preview_lists.setdefault(key, []).append(attachment)
    return preview_map, preview_lists


def _institution_attachment_preview_map(application_numbers):
    preview_map, _preview_lists = _institution_attachment_preview_data(application_numbers)
    return preview_map


def _institution_attachment_preview_lists(application_numbers):
    _preview_map, preview_lists = _institution_attachment_preview_data(application_numbers)
    return preview_lists


def _attachment_preview_title(attachment):
    if not attachment:
        return ""
    if attachment.file_name:
        return attachment.file_name
    if attachment.drive_view_url:
        return "Attachment"
    if attachment.file:
        return os.path.basename(attachment.file.name)
    return ""


def _attachment_preview_payload(attachment):
    if not attachment:
        return None
    preview_url = reverse("ui:application-attachment-download", kwargs={"attachment_id": attachment.id})
    source_name = _attachment_preview_source(attachment)
    return {
        "id": attachment.id,
        "title": _attachment_preview_title(attachment),
        "preview_url": preview_url,
        "download_url": f"{preview_url}?download=1",
        "source": source_name,
    }


def _attachment_preview_source(attachment):
    if not attachment:
        return ""
    if attachment.file and attachment.file.name:
        return (attachment.file.name or "").lower()
    source_name = (attachment.file_name or "").lower()
    mime_type = (attachment.drive_mime_type or "").lower()
    if source_name and "." not in os.path.basename(source_name):
        if mime_type == "application/pdf":
            source_name = f"{source_name}.pdf"
        elif mime_type.startswith("image/"):
            ext = mime_type.split("/", 1)[1].strip()
            if ext == "jpeg":
                ext = "jpg"
            if ext:
                source_name = f"{source_name}.{ext}"
    return source_name


def _attachment_items_b64(items):
    payload = json.dumps(items, ensure_ascii=False)
    return base64.b64encode(payload.encode("utf-8")).decode("ascii")


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
        "internal_notes": (entries[0].internal_notes or "") if entries else "",
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
                "name_of_beneficiary": entry.name_of_beneficiary or "",
                "name_of_institution": entry.name_of_institution or "",
                "aadhar_number": entry.aadhar_number or "",
                "cheque_rtgs_in_favour": entry.cheque_rtgs_in_favour or "",
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
        "is_handicapped": entry.get_is_handicapped_display() if entry.is_handicapped else models.HandicappedStatusChoices.NO,
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
        "name_of_institution": entry.name_of_institution or "",
        "cheque_rtgs_in_favour": entry.cheque_rtgs_in_favour or "",
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
        "internal_notes": first.internal_notes or "",
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
                "name_of_beneficiary": entry.name_of_beneficiary or "",
                "name_of_institution": entry.name_of_institution or "",
                "aadhar_number": entry.aadhar_number or "",
                "cheque_rtgs_in_favour": entry.cheque_rtgs_in_favour or "",
                "notes": entry.notes or "",
            }
            for entry in entries
        ],
    }


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
            "Aadhar Number": entry.aadhar_number or "",
            "Name of Beneficiary": entry.name_of_beneficiary or "",
            "Name of Institution": entry.name_of_institution or "",
            "Cheque / RTGS in Favour": entry.cheque_rtgs_in_favour or "",
            "Handicapped Status": "",
            "Gender": "",
            "Gender Category": "",
            "Beneficiary Type": "District",
            "Item Type": entry.article.item_type or "",
            "Article Category": entry.article.category or "",
            "Super Category Article": entry.article.master_category or "",
            "Token Name": entry.article.article_name_tk or "",
            "Internal Notes": "",
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
            "Name of Beneficiary": entry.name or "",
            "Name of Institution": entry.name_of_institution or "",
            "Cheque / RTGS in Favour": entry.cheque_rtgs_in_favour or "",
            "Handicapped Status": entry.get_is_handicapped_display() if entry.is_handicapped else models.HandicappedStatusChoices.NO,
            "Gender": entry.gender or "",
            "Gender Category": entry.female_status or entry.gender or "",
            "Beneficiary Type": "Public",
            "Item Type": entry.article.item_type or "",
            "Article Category": entry.article.category or "",
            "Super Category Article": entry.article.master_category or "",
            "Token Name": entry.article.article_name_tk or "",
            "Internal Notes": "",
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
            "Aadhar Number": entry.aadhar_number or "",
            "Name of Beneficiary": entry.name_of_beneficiary or "",
            "Name of Institution": entry.name_of_institution or "",
            "Cheque / RTGS in Favour": entry.cheque_rtgs_in_favour or "",
            "Handicapped Status": "",
            "Gender": "",
            "Gender Category": "",
            "Beneficiary Type": "Institutions",
            "Item Type": entry.article.item_type or "",
            "Article Category": entry.article.category or "",
            "Super Category Article": entry.article.master_category or "",
            "Token Name": entry.article.article_name_tk or "",
            "Internal Notes": entry.internal_notes or "",
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
        status_filter = filters.get("status_filter") or ""
        filtered_public_entries = _filter_sort_public_entries(
            _public_visible_queryset(status_filter=status_filter).select_related("article").all(),
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
    timestamp = timezone.localtime().strftime("%d_%b_%y_%H_%M")
    if export_scope == "all":
        has_non_submitted = (
            models.DistrictBeneficiaryEntry.objects.exclude(status=models.BeneficiaryStatusChoices.SUBMITTED).exists()
            or _public_active_queryset().exclude(status=models.BeneficiaryStatusChoices.SUBMITTED).exists()
            or models.InstitutionsBeneficiaryEntry.objects.exclude(status=models.BeneficiaryStatusChoices.SUBMITTED).exists()
        )
        status_label = "Draft" if has_non_submitted else "Submitted"
        filename = f"1_Master_Data_{status_label}_{timestamp}.csv"
    else:
        has_non_submitted = False
        scope_rows = []
        if export_scope == "district":
            scope_rows = models.DistrictBeneficiaryEntry.objects.all()
        elif export_scope == "public":
            scope_rows = _public_active_queryset()
        elif export_scope == "institutions":
            scope_rows = models.InstitutionsBeneficiaryEntry.objects.all()
        if scope_rows:
            has_non_submitted = scope_rows.exclude(status=models.BeneficiaryStatusChoices.SUBMITTED).exists()
        status_label = "Draft" if has_non_submitted else "Submitted"
        scope_label = export_scope.title()
        filename = f"1_Master_Data_{scope_label}_{status_label}_{timestamp}.csv"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    writer = csv.DictWriter(response, fieldnames=EXPORT_COLUMNS)
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return response


def _build_district_entry_summaries():
    """
    Return per-district summaries for the master-entry list view.

    The older implementation loaded every DistrictBeneficiaryEntry row into Python and grouped there.
    That becomes noticeably slow as data grows. This version lets Postgres do the grouping/aggregation,
    then we enrich with attachment metadata in one shot.
    """

    latest_entry_qs = (
        models.DistrictBeneficiaryEntry.objects.filter(district_id=OuterRef("district_id"))
        .order_by("-created_at", "-id")
    )

    rows = list(
        models.DistrictBeneficiaryEntry.objects.values(
            "district_id",
            "district__application_number",
            "district__district_name",
            "district__allotted_budget",
        )
        .annotate(
            total_accrued=Coalesce(Sum("total_amount"), Value(Decimal("0"))),
            total_quantity=Coalesce(Sum("quantity"), Value(0)),
            article_count=Count("article_id", distinct=True),
            article_names=Coalesce(
                StringAgg("article__article_name", delimiter=", ", distinct=True, ordering="article__article_name"),
                Value("", output_field=TextField()),
            ),
            created_at=Max("created_at"),
            status=Subquery(latest_entry_qs.values("status")[:1]),
            internal_notes=Coalesce(
                Subquery(latest_entry_qs.values("internal_notes")[:1]),
                Value("", output_field=TextField()),
            ),
        )
        .order_by("district__application_number")
    )

    district_ids = [row["district_id"] for row in rows if row.get("district_id")]
    detail_entries = (
        models.DistrictBeneficiaryEntry.objects.select_related("article")
        .filter(district_id__in=district_ids)
        .order_by("district_id", "created_at", "id")
    )
    detail_items_by_district = {}
    for entry in detail_entries:
        items = detail_items_by_district.setdefault(entry.district_id, [])
        items.append(
            {
                "id": entry.id,
                "article_name": entry.article.article_name if entry.article_id else "",
                "item_type": entry.article.item_type if entry.article_id else "",
                "quantity": entry.quantity or 0,
                "unit_price": entry.article_cost_per_unit or Decimal("0"),
                "total_amount": entry.total_amount or Decimal("0"),
                "name_of_beneficiary": entry.name_of_beneficiary or "",
                "name_of_institution": entry.name_of_institution or "",
                "aadhar_number": entry.aadhar_number or "",
                "notes": entry.notes or "",
                "cheque_rtgs_in_favour": entry.cheque_rtgs_in_favour or "",
                "changed_at": entry.updated_at or entry.created_at,
            }
        )

    attachment_latest, attachment_counts = _district_attachment_latest_and_counts(district_ids)

    summaries = []
    for row in rows:
        district_id = row.get("district_id")
        allotted_budget = row.get("district__allotted_budget") or 0
        total_accrued = row.get("total_accrued") or 0
        attachment = attachment_latest.get(district_id)
        summaries.append(
            {
                "district_id": district_id,
                "application_number": row.get("district__application_number") or "-",
                "district_name": row.get("district__district_name") or "-",
                "article_names": row.get("article_names") or "",
                "article_count": int(row.get("article_count") or 0),
                "total_quantity": int(row.get("total_quantity") or 0),
                "allotted_budget": allotted_budget,
                "total_accrued": total_accrued,
                "remaining_fund": allotted_budget - total_accrued,
                "status": row.get("status") or "",
                "internal_notes": row.get("internal_notes") or "",
                "created_at": row.get("created_at") or timezone.now(),
                "attachment_id": attachment.id if attachment else None,
                "attachment_preview_url": (
                    reverse("ui:application-attachment-download", kwargs={"attachment_id": attachment.id})
                    if attachment
                    else ""
                ),
                "attachment_source": _attachment_preview_source(attachment),
                "attachment_title": _attachment_preview_title(attachment),
                "attachment_count": attachment_counts.get(district_id, 0),
                "detail_items": detail_items_by_district.get(district_id, []),
            }
        )

    return summaries


def _filter_sort_district_summaries(summaries, *, search_query="", date_from="", date_to="", status_filter="", sort_by="", sort_dir="desc"):
    if search_query:
        query = search_query.lower()
        summaries = [
            row for row in summaries
            if query in (row["application_number"] or "").lower()
            or query in (row["district_name"] or "").lower()
            or query in (row.get("article_names") or "").lower()
            or query in (row.get("internal_notes") or "").lower()
            or query in (row.get("status") or "").lower()
            or any(
                query in str(item.get("article_name") or "").lower()
                or query in str(item.get("name_of_beneficiary") or "").lower()
                or query in str(item.get("name_of_institution") or "").lower()
                or query in str(item.get("aadhar_number") or "").lower()
                or query in str(item.get("notes") or "").lower()
                or query in str(item.get("cheque_rtgs_in_favour") or "").lower()
                for item in row.get("detail_items", [])
            )
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
        "article_category_suggestions": get_article_text_suggestions("category"),
        "article_master_category_suggestions": get_article_text_suggestions("master_category"),
        "selected_district": district,
        "entry_rows": entries or [],
        "form_errors": errors or [],
        "form_successes": [],
        "application_status": (entries[0]["status"] if entries and isinstance(entries[0], dict) and entries[0].get("status") else ""),
        "internal_notes": (entries[0].get("internal_notes", "") if entries and isinstance(entries[0], dict) else ""),
    }


def _parse_district_rows(post_data):
    entry_ids = post_data.getlist("entry_id")
    article_ids = post_data.getlist("article_id")
    quantities = post_data.getlist("quantity")
    unit_costs = post_data.getlist("unit_cost")
    notes_list = post_data.getlist("notes")
    name_of_beneficiary_list = post_data.getlist("name_of_beneficiary")
    name_of_institution_list = post_data.getlist("name_of_institution")
    aadhar_number_list = post_data.getlist("aadhar_number")
    cheque_rtgs_list = post_data.getlist("cheque_rtgs_in_favour")
    rows = []
    max_len = max(
        len(article_ids),
        len(quantities),
        len(unit_costs),
        len(notes_list),
        len(name_of_beneficiary_list),
        len(name_of_institution_list),
        len(aadhar_number_list),
        len(cheque_rtgs_list),
        0,
    )
    for idx in range(max_len):
        rows.append(
            {
                "entry_id": (entry_ids[idx] if idx < len(entry_ids) else "").strip(),
                "article_id": (article_ids[idx] if idx < len(article_ids) else "").strip(),
                "quantity": (quantities[idx] if idx < len(quantities) else "").strip(),
                "unit_cost": (unit_costs[idx] if idx < len(unit_costs) else "").strip(),
                "notes": (notes_list[idx] if idx < len(notes_list) else "").strip(),
                "name_of_beneficiary": (name_of_beneficiary_list[idx] if idx < len(name_of_beneficiary_list) else "").strip(),
                "name_of_institution": (name_of_institution_list[idx] if idx < len(name_of_institution_list) else "").strip(),
                "aadhar_number": (aadhar_number_list[idx] if idx < len(aadhar_number_list) else "").strip(),
                "cheque_rtgs_in_favour": (cheque_rtgs_list[idx] if idx < len(cheque_rtgs_list) else "").strip(),
            }
        )
    return [row for row in rows if any(row.values())]


def _validate_and_build_district_entries(district, raw_rows, *, internal_notes=""):
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

        raw_unit_cost = str(row.get("unit_cost") or "").strip()
        if raw_unit_cost:
            try:
                unit_cost = Decimal(raw_unit_cost)
                if unit_cost < 0:
                    raise ValueError
            except (InvalidOperation, TypeError, ValueError):
                errors.append(f"Row {index}: enter a valid price for {article.article_name}.")
                continue
        elif article.cost_per_unit and article.cost_per_unit > 0:
            unit_cost = article.cost_per_unit
        else:
            errors.append(f"Row {index}: enter a valid price for {article.article_name}.")
            continue

        total_amount = unit_cost * quantity
        built_rows.append(
            {
                "entry_id": int(row["entry_id"]) if str(row.get("entry_id") or "").strip().isdigit() else None,
                "district": district,
                "application_number": district.application_number,
                "article": article,
                "article_cost_per_unit": unit_cost,
                "quantity": quantity,
                "total_amount": total_amount,
                "name_of_beneficiary": row.get("name_of_beneficiary") or None,
                "name_of_institution": row["name_of_institution"] or None,
                "aadhar_number": row["aadhar_number"] or None,
                "cheque_rtgs_in_favour": row["cheque_rtgs_in_favour"] or None,
                "notes": row["notes"] or None,
                "internal_notes": internal_notes or None,
                "status": models.BeneficiaryStatusChoices.PENDING,
            }
        )
        if article.item_type != models.ItemTypeChoices.AID:
            seen_articles.add(article.id)

    return built_rows, errors


def _timestamp_conflict_token(value):
    if not value:
        return ""
    return timezone.localtime(value).isoformat()


def _district_conflict_token(district):
    if not district:
        return ""
    latest = (
        models.DistrictBeneficiaryEntry.objects.filter(district=district)
        .order_by("-updated_at")
        .values_list("updated_at", flat=True)
        .first()
    )
    return _timestamp_conflict_token(latest)


def _public_conflict_token(entry):
    if not entry:
        return ""
    return _timestamp_conflict_token(entry.updated_at)


def _institution_conflict_token(application_number):
    if not application_number:
        return ""
    latest = (
        models.InstitutionsBeneficiaryEntry.objects.filter(application_number=application_number)
        .order_by("-updated_at")
        .values_list("updated_at", flat=True)
        .first()
    )
    return _timestamp_conflict_token(latest)


def _conflict_message(label):
    return (
        f"This {label} was updated after you opened this page. "
        f"We stopped the save so newer changes are not overwritten. "
        f"Please review the latest version and then try again."
    )


class DistrictMasterEntryBaseView(LoginRequiredMixin, WriteRoleMixin, TemplateView):
    module_key = models.ModuleKeyChoices.APPLICATION_ENTRY
    permission_action = "create_edit"
    template_name = "application_entry/master_entry_district_form.html"

    def get_district(self):
        district_id = self.kwargs.get("district_id")
        if district_id:
            return models.DistrictMaster.objects.get(pk=district_id, is_active=True)
        return None

    def _render_form(self, district=None, entries=None, errors=None):
        context = self.get_context_data(**_district_form_context(district=district, entries=entries, errors=errors))
        context.update(_district_attachment_context(district))
        context["conflict_token"] = _district_conflict_token(district)
        return self.render_to_response(context)

    def _save_entries(self, district, rows, *, replace=False):
        action = (self.request.POST.get("action") or "draft").strip().lower()
        internal_notes = (self.request.POST.get("internal_notes") or "").strip()
        target_status = models.BeneficiaryStatusChoices.SUBMITTED if action == "submit" else models.BeneficiaryStatusChoices.DRAFT
        built_rows, errors = _validate_and_build_district_entries(district, rows, internal_notes=internal_notes)
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
                        "entry_id": row.get("entry_id", ""),
                        "quantity": row["quantity"],
                        "unit_cost": row["unit_cost"],
                        "notes": row["notes"],
                        "name_of_beneficiary": row.get("name_of_beneficiary", ""),
                        "name_of_institution": row.get("name_of_institution", ""),
                        "aadhar_number": row.get("aadhar_number", ""),
                        "cheque_rtgs_in_favour": row.get("cheque_rtgs_in_favour", ""),
                        "article_name": article.article_name if article else "",
                        "item_type": article.item_type if article else "",
                        "internal_notes": internal_notes,
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
                log_audit(
                    user=self.request.user,
                    action_type=models.ActionTypeChoices.UPDATE,
                    entity_type="district_application",
                    entity_id=str(district.id),
                    details={"before": before_snapshot, "after": after_snapshot},
                    **get_request_audit_meta(self.request),
                )
                if previous_status != target_status:
                    log_audit(
                        user=self.request.user,
                        action_type=models.ActionTypeChoices.STATUS_CHANGE,
                        entity_type="district_application",
                        entity_id=str(district.id),
                        details={"from": previous_status, "to": target_status},
                        **get_request_audit_meta(self.request),
                    )
            else:
                for built in built_rows:
                    create_kwargs = {key: value for key, value in built.items() if key != "entry_id"}
                    models.DistrictBeneficiaryEntry.objects.create(created_by=self.request.user, **create_kwargs)
                log_audit(
                    user=self.request.user,
                    action_type=models.ActionTypeChoices.CREATE,
                    entity_type="district_application",
                    entity_id=str(district.id),
                    details={"after": _district_audit_snapshot(district)},
                    **get_request_audit_meta(self.request),
                )
                log_audit(
                    user=self.request.user,
                    action_type=models.ActionTypeChoices.STATUS_CHANGE,
                    entity_type="district_application",
                    entity_id=str(district.id),
                    details={"from": None, "to": target_status},
                        **get_request_audit_meta(self.request),
                    )
        return None


class DistrictMasterEntryCreateView(DistrictMasterEntryBaseView):
    def get(self, request, *args, **kwargs):
        district_id = (request.GET.get("district_id") or "").strip()
        if district_id:
            district = models.DistrictMaster.objects.filter(pk=district_id, is_active=True).first()
            if district:
                if models.DistrictBeneficiaryEntry.objects.filter(district=district).exists():
                    return HttpResponseRedirect(reverse("ui:master-entry-district-edit", kwargs={"district_id": district.id}))
                return self._render_form(district=district)
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
                "entry_id": str(entry.id),
                "quantity": entry.quantity,
                "unit_cost": entry.article_cost_per_unit,
                "notes": entry.notes or "",
                "name_of_beneficiary": entry.name_of_beneficiary or "",
                "name_of_institution": entry.name_of_institution or "",
                "aadhar_number": entry.aadhar_number or "",
                "cheque_rtgs_in_favour": entry.cheque_rtgs_in_favour or "",
                "article_name": entry.article.article_name,
                "item_type": entry.article.item_type,
                "status": entry.status,
                "internal_notes": entry.internal_notes or "",
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
        submitted_conflict_token = request.POST.get("_conflict_token", "")
        current_conflict_token = _district_conflict_token(district)
        if submitted_conflict_token and current_conflict_token and submitted_conflict_token != current_conflict_token:
            messages.error(request, _conflict_message("district application"), extra_tags="persistent")
            return HttpResponseRedirect(reverse("ui:master-entry-district-edit", kwargs={"district_id": district.id}))
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


class DistrictMasterEntryDeleteView(LoginRequiredMixin, AdminRequiredMixin, View):
    module_key = models.ModuleKeyChoices.APPLICATION_ENTRY
    permission_action = "delete"
    def post(self, request, *args, **kwargs):
        district = models.DistrictMaster.objects.get(pk=kwargs["district_id"], is_active=True)
        snapshot = _district_audit_snapshot(district)
        models.DistrictBeneficiaryEntry.objects.filter(district=district).delete()
        log_audit(
            user=request.user,
            action_type=models.ActionTypeChoices.DELETE,
            entity_type="district_application",
            entity_id=str(district.id),
            details={"before": snapshot},
            **get_request_audit_meta(request),
        )
        messages.warning(request, "District entry deleted.")
        return HttpResponseRedirect(reverse("ui:master-entry"))


class DistrictMasterEntryReopenView(LoginRequiredMixin, AdminRequiredMixin, View):
    module_key = models.ModuleKeyChoices.APPLICATION_ENTRY
    permission_action = "reopen"
    def post(self, request, *args, **kwargs):
        district = models.DistrictMaster.objects.get(pk=kwargs["district_id"], is_active=True)
        models.DistrictBeneficiaryEntry.objects.filter(district=district).update(status=models.BeneficiaryStatusChoices.DRAFT)
        log_audit(
            user=request.user,
            action_type=models.ActionTypeChoices.STATUS_CHANGE,
            entity_type="district_application",
            entity_id=str(district.id),
            details={"from": models.BeneficiaryStatusChoices.SUBMITTED, "to": models.BeneficiaryStatusChoices.DRAFT},
            **get_request_audit_meta(request),
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


def _public_history_summary(history_matches):
    items = []
    for row in history_matches or []:
        year = getattr(row, "year", "") or "-"
        article = getattr(row, "article_name", "") or "-"
        items.append(f"{year}: {article}")
    return "; ".join(items)


def _public_current_match(aadhar_number, *, exclude_pk=None):
    if not aadhar_number:
        return None
    queryset = _public_active_queryset().select_related("article").filter(aadhar_number=aadhar_number)
    if exclude_pk:
        queryset = queryset.exclude(pk=exclude_pk)
    return queryset.order_by("-created_at").first()


def _public_form_context(entry=None, form_data=None, history_matches=None, current_match=None, warnings=None, errors=None, successes=None, allow_duplicate_save=False):
    entry = entry or {}
    return {
        "public_entry": entry,
        "public_form_data": form_data or {},
        "history_matches": history_matches or [],
        "history_summary": _public_history_summary(history_matches or []),
        "current_match": current_match,
        "form_warnings": warnings or [],
        "form_errors": errors or [],
        "form_successes": successes or [],
        "allow_duplicate_save": allow_duplicate_save,
        "articles_master_list": list(models.Article.objects.filter(is_active=True).order_by("article_name")),
        "article_category_suggestions": get_article_text_suggestions("category"),
        "article_master_category_suggestions": get_article_text_suggestions("master_category"),
        "gender_choices": models.GenderChoices.choices,
        "female_status_choices": models.FemaleStatusChoices.choices,
        "disability_category_choices": models.DisabilityCategoryChoices.choices,
        "aadhaar_status_choices": models.AadhaarVerificationStatusChoices.choices,
        "female_status_descriptions": FEMALE_STATUS_DESCRIPTIONS,
        "application_status": getattr(entry, "status", ""),
    }


def _build_public_form_data(post_data):
    disability_category = (post_data.get("disability_category") or "").strip()
    is_handicapped = post_data.get("is_handicapped", "")
    if disability_category:
        is_handicapped = "true"
    return {
        "aadhar_number": (post_data.get("aadhar_number") or "").strip(),
        "aadhaar_not_available": (post_data.get("aadhaar_not_available") or "").strip().lower() in {"1", "true", "on", "yes"},
        "name": (post_data.get("name") or "").strip(),
        "is_handicapped": is_handicapped,
        "disability_category": disability_category,
        "gender": (post_data.get("gender") or "").strip(),
        "female_status": (post_data.get("female_status") or "").strip(),
        "address": (post_data.get("address") or "").strip(),
        "mobile": (post_data.get("mobile") or "").strip(),
        "article_id": (post_data.get("article_id") or "").strip(),
        "article_cost_per_unit": (post_data.get("article_cost_per_unit") or "").strip(),
        "quantity": (post_data.get("quantity") or "").strip(),
        "name_of_institution": (post_data.get("name_of_institution") or "").strip(),
        "cheque_rtgs_in_favour": (post_data.get("cheque_rtgs_in_favour") or "").strip(),
        "notes": (post_data.get("notes") or "").strip(),
    }


def _validate_public_form(form_data, *, require_complete=True):
    errors = []
    article = None

    aadhar_number = (form_data["aadhar_number"] or "").strip()
    aadhaar_not_available = bool(form_data.get("aadhaar_not_available"))
    if aadhaar_not_available:
        form_data["aadhar_number"] = ""
        if require_complete and not (form_data.get("notes") or "").strip():
            errors.append("Comments are required when Aadhaar is marked as not available.")
    else:
        if require_complete:
            if not (aadhar_number.isdigit() and len(aadhar_number) == 12):
                errors.append("Aadhaar number must be a valid 12-digit number.")
        elif aadhar_number and not (aadhar_number.isdigit() and len(aadhar_number) == 12):
            errors.append("Aadhaar number must be a valid 12-digit number.")

    if require_complete and not form_data["name"]:
        errors.append("Name is required.")

    if require_complete and form_data["is_handicapped"] not in {"true", "false"}:
        errors.append("Handicapped status is required.")

    if form_data["is_handicapped"] == "true":
        valid_disability_values = {value for value, _label in models.DisabilityCategoryChoices.choices}
        if require_complete and not form_data["disability_category"]:
            errors.append("Disability category is required when handicapped is Yes.")
        elif form_data["disability_category"] and form_data["disability_category"] not in valid_disability_values:
            errors.append("Select a valid disability category.")

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
        raw_unit_cost = str(form_data.get("article_cost_per_unit") or "").strip()
        if raw_unit_cost:
            try:
                unit_cost = Decimal(raw_unit_cost)
                if unit_cost < 0:
                    raise ValueError
            except (InvalidOperation, TypeError, ValueError):
                errors.append("Enter a valid cost per unit.")
        elif article.cost_per_unit and article.cost_per_unit > 0:
            unit_cost = article.cost_per_unit
        else:
            errors.append("Enter a valid cost per unit.")

    return article, quantity, unit_cost, errors


def _resolve_public_aadhaar_status(form_data):
    if form_data.get("aadhaar_not_available"):
        return models.AadhaarVerificationStatusChoices.NOT_AVAILABLE
    aadhar_number = (form_data.get("aadhar_number") or "").strip()
    if aadhar_number.isdigit() and len(aadhar_number) == 12:
        return models.AadhaarVerificationStatusChoices.VERIFIED
    return models.AadhaarVerificationStatusChoices.PENDING_VERIFICATION


def _build_institution_entry_summaries():
    """
    Return per-application summaries for Institutions/Others in master-entry list view.

    Uses Postgres aggregation instead of grouping every row in Python.
    """

    latest_entry_qs = (
        models.InstitutionsBeneficiaryEntry.objects.filter(application_number=OuterRef("application_number"))
        .order_by("-created_at", "-id")
    )

    rows = list(
        models.InstitutionsBeneficiaryEntry.objects.exclude(application_number__isnull=True)
        .exclude(application_number__exact="")
        .values("application_number")
        .annotate(
            institution_name=Coalesce(
                Subquery(latest_entry_qs.values("institution_name")[:1]),
                Value("", output_field=TextField()),
                output_field=TextField(),
            ),
            institution_type=Coalesce(
                Subquery(latest_entry_qs.values("institution_type")[:1]),
                Value("", output_field=TextField()),
                output_field=TextField(),
            ),
            address=Coalesce(
                Subquery(latest_entry_qs.values("address")[:1]),
                Value("", output_field=TextField()),
                output_field=TextField(),
            ),
            mobile=Coalesce(
                Subquery(latest_entry_qs.values("mobile")[:1]),
                Value("", output_field=TextField()),
                output_field=TextField(),
            ),
            status=Subquery(latest_entry_qs.values("status")[:1]),
            internal_notes=Coalesce(
                Subquery(latest_entry_qs.values("internal_notes")[:1]),
                Value("", output_field=TextField()),
            ),
            created_at=Max("created_at"),
            article_count=Count("article_id", distinct=True),
            article_names=Coalesce(
                StringAgg("article__article_name", delimiter=", ", distinct=True, ordering="article__article_name"),
                Value("", output_field=TextField()),
            ),
            total_quantity=Coalesce(Sum("quantity"), Value(0)),
            total_value=Coalesce(Sum("total_amount"), Value(Decimal("0"))),
        )
        .order_by("application_number")
    )

    application_numbers = [row["application_number"] for row in rows if row.get("application_number")]
    detail_entries = (
        models.InstitutionsBeneficiaryEntry.objects.select_related("article")
        .filter(application_number__in=application_numbers)
        .order_by("application_number", "created_at", "id")
    )
    detail_items_by_application = {}
    for entry in detail_entries:
        items = detail_items_by_application.setdefault(entry.application_number, [])
        items.append(
            {
                "id": entry.id,
                "article_name": entry.article.article_name if entry.article_id else "",
                "item_type": entry.article.item_type if entry.article_id else "",
                "quantity": entry.quantity or 0,
                "unit_price": entry.article_cost_per_unit or Decimal("0"),
                "total_amount": entry.total_amount or Decimal("0"),
                "name_of_beneficiary": entry.name_of_beneficiary or "",
                "name_of_institution": entry.name_of_institution or "",
                "aadhar_number": entry.aadhar_number or "",
                "notes": entry.notes or "",
                "cheque_rtgs_in_favour": entry.cheque_rtgs_in_favour or "",
                "changed_at": entry.updated_at or entry.created_at,
            }
        )

    attachment_latest, attachment_counts = _institution_attachment_latest_and_counts(application_numbers)

    summaries = []
    for row in rows:
        application_number = row.get("application_number") or "-"
        attachment = attachment_latest.get(application_number)
        institution_type_value = row.get("institution_type") or ""
        institution_type_label = institution_type_value
        if institution_type_value:
            try:
                institution_type_label = models.InstitutionTypeChoices(institution_type_value).label
            except ValueError:
                institution_type_label = institution_type_value
        summaries.append(
            {
                "application_number": application_number,
                "institution_name": row.get("institution_name") or "",
                "institution_type": institution_type_label,
                "article_names": row.get("article_names") or "",
                "article_count": int(row.get("article_count") or 0),
                "total_quantity": int(row.get("total_quantity") or 0),
                "total_value": row.get("total_value") or 0,
                "status": row.get("status") or "",
                "internal_notes": row.get("internal_notes") or "",
                "created_at": row.get("created_at") or timezone.now(),
                "address": row.get("address") or "",
                "mobile": row.get("mobile") or "",
                "attachment_id": attachment.id if attachment else None,
                "attachment_preview_url": (
                    reverse("ui:application-attachment-download", kwargs={"attachment_id": attachment.id})
                    if attachment
                    else ""
                ),
                "attachment_source": _attachment_preview_source(attachment),
                "attachment_title": _attachment_preview_title(attachment),
                "attachment_count": attachment_counts.get(application_number, 0),
                "detail_items": detail_items_by_application.get(application_number, []),
            }
        )

    return summaries


def _filter_sort_public_entries(queryset, *, search_query="", date_from="", date_to="", status_filter="", sort_by="", sort_dir="desc"):
    if search_query:
        query_filter = (
            Q(application_number__icontains=search_query)
            | Q(name__icontains=search_query)
            | Q(aadhar_number__icontains=search_query)
            | Q(address__icontains=search_query)
            | Q(mobile__icontains=search_query)
            | Q(article__article_name__icontains=search_query)
            | Q(name_of_institution__icontains=search_query)
            | Q(notes__icontains=search_query)
            | Q(cheque_rtgs_in_favour__icontains=search_query)
        )
        queryset = queryset.filter(query_filter)
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
            or query in (row.get("institution_type") or "").lower()
            or query in (row.get("article_names") or "").lower()
            or query in (row.get("internal_notes") or "").lower()
            or query in (row.get("address") or "").lower()
            or query in (row.get("mobile") or "").lower()
            or query in (row.get("status") or "").lower()
            or any(
                query in str(item.get("article_name") or "").lower()
                or query in str(item.get("name_of_beneficiary") or "").lower()
                or query in str(item.get("name_of_institution") or "").lower()
                or query in str(item.get("aadhar_number") or "").lower()
                or query in str(item.get("notes") or "").lower()
                or query in str(item.get("cheque_rtgs_in_favour") or "").lower()
                for item in row.get("detail_items", [])
            )
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
        "article_category_suggestions": get_article_text_suggestions("category"),
        "article_master_category_suggestions": get_article_text_suggestions("master_category"),
        "institution_type_choices": models.InstitutionTypeChoices.choices,
        "institution_application_number": application_number,
        "application_status": (rows[0]["status"] if rows and isinstance(rows[0], dict) and rows[0].get("status") else ""),
        "internal_notes": (form_data or {}).get("internal_notes", ""),
    }


def _build_institution_form_data(post_data):
    return {
        "institution_name": (post_data.get("institution_name") or "").strip(),
        "institution_type": (post_data.get("institution_type") or "").strip(),
        "address": (post_data.get("address") or "").strip(),
        "mobile": (post_data.get("mobile") or "").strip(),
        "internal_notes": (post_data.get("internal_notes") or "").strip(),
    }


def _validate_institution_rows(raw_rows, *, require_complete=True, internal_notes=""):
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

        raw_unit_cost = str(row.get("unit_cost") or "").strip()
        if raw_unit_cost:
            try:
                unit_cost = Decimal(raw_unit_cost)
                if unit_cost < 0:
                    raise ValueError
            except (InvalidOperation, TypeError, ValueError):
                errors.append(f"Row {index}: enter a valid price for {article.article_name}.")
                continue
        elif article.cost_per_unit and article.cost_per_unit > 0:
            unit_cost = article.cost_per_unit
        else:
            errors.append(f"Row {index}: enter a valid price for {article.article_name}.")
            continue

        built_rows.append(
            {
                "entry_id": int(row["entry_id"]) if str(row.get("entry_id") or "").strip().isdigit() else None,
                "article": article,
                "article_cost_per_unit": unit_cost,
                "quantity": quantity,
                "total_amount": unit_cost * quantity,
                "name_of_beneficiary": row.get("name_of_beneficiary") or None,
                "name_of_institution": row.get("name_of_institution") or None,
                "aadhar_number": row.get("aadhar_number") or None,
                "cheque_rtgs_in_favour": row.get("cheque_rtgs_in_favour") or None,
                "notes": row["notes"] or None,
                "internal_notes": internal_notes or None,
            }
        )
        if article.item_type != models.ItemTypeChoices.AID:
            seen_articles.add(article.id)
    return built_rows, errors


def _sync_district_entries(existing_entries, built_rows, user):
    by_id = {entry.id: entry for entry in existing_entries}
    by_article = {}
    for entry in existing_entries:
        by_article.setdefault(entry.article_id, []).append(entry)

    used_ids = set()
    for built in built_rows:
        match = None
        entry_id = built.get("entry_id")
        if entry_id:
            candidate = by_id.get(entry_id)
            if candidate and candidate.id not in used_ids:
                match = candidate
        if match is None:
            candidates = by_article.get(built["article"].id, [])
            match = next((entry for entry in candidates if entry.id not in used_ids), None)
        if match is None:
            create_kwargs = {key: value for key, value in built.items() if key != "entry_id"}
            models.DistrictBeneficiaryEntry.objects.create(created_by=user, **create_kwargs)
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
        if match.name_of_beneficiary != built.get("name_of_beneficiary"):
            match.name_of_beneficiary = built.get("name_of_beneficiary")
            changed = True
        if match.name_of_institution != built.get("name_of_institution"):
            match.name_of_institution = built.get("name_of_institution")
            changed = True
        if match.aadhar_number != built.get("aadhar_number"):
            match.aadhar_number = built.get("aadhar_number")
            changed = True
        if match.cheque_rtgs_in_favour != built.get("cheque_rtgs_in_favour"):
            match.cheque_rtgs_in_favour = built.get("cheque_rtgs_in_favour")
            changed = True
        if match.notes != built["notes"]:
            match.notes = built["notes"]
            changed = True
        if match.internal_notes != built.get("internal_notes"):
            match.internal_notes = built.get("internal_notes")
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
    by_id = {entry.id: entry for entry in existing_entries}
    by_article = {}
    for entry in existing_entries:
        by_article.setdefault(entry.article_id, []).append(entry)

    used_ids = set()
    for built in built_rows:
        match = None
        entry_id = built.get("entry_id")
        if entry_id:
            candidate = by_id.get(entry_id)
            if candidate and candidate.id not in used_ids:
                match = candidate
        if match is None:
            candidates = by_article.get(built["article"].id, [])
            match = next((entry for entry in candidates if entry.id not in used_ids), None)
        if match is None:
            create_kwargs = {key: value for key, value in built.items() if key != "entry_id"}
            models.InstitutionsBeneficiaryEntry.objects.create(
                created_by=user,
                application_number=application_number,
                institution_name=form_data["institution_name"],
                institution_type=form_data["institution_type"],
                address=form_data["address"] or None,
                mobile=form_data["mobile"] or None,
                **create_kwargs,
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
        if match.name_of_beneficiary != built.get("name_of_beneficiary"):
            match.name_of_beneficiary = built.get("name_of_beneficiary")
            changed = True
        if match.name_of_institution != built.get("name_of_institution"):
            match.name_of_institution = built.get("name_of_institution")
            changed = True
        if match.aadhar_number != built.get("aadhar_number"):
            match.aadhar_number = built.get("aadhar_number")
            changed = True
        if match.cheque_rtgs_in_favour != built.get("cheque_rtgs_in_favour"):
            match.cheque_rtgs_in_favour = built.get("cheque_rtgs_in_favour")
            changed = True
        if match.notes != built["notes"]:
            match.notes = built["notes"]
            changed = True
        if match.internal_notes != built.get("internal_notes"):
            match.internal_notes = built.get("internal_notes")
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
    module_key = models.ModuleKeyChoices.APPLICATION_ENTRY
    permission_action = "create_edit"
    template_name = "application_entry/master_entry_public_form.html"

    def get_entry(self):
        pk = self.kwargs.get("pk")
        if pk:
            return _public_any_queryset().select_related("article").get(pk=pk)
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
        context.update(_public_attachment_context_with_request(self.request, entry))
        context["conflict_token"] = _public_conflict_token(entry)
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
        previous_application_number = entry.application_number

        entry.name = form_data["name"]
        entry.aadhar_number = form_data["aadhar_number"] or None
        entry.aadhaar_status = _resolve_public_aadhaar_status(form_data)
        entry.is_handicapped = form_data["disability_category"] or models.HandicappedStatusChoices.NO
        entry.gender = form_data["gender"]
        entry.female_status = form_data["female_status"] or None
        entry.address = form_data["address"] or None
        entry.mobile = form_data["mobile"]
        entry.article = article
        entry.article_cost_per_unit = unit_cost
        entry.quantity = quantity
        entry.total_amount = unit_cost * quantity
        entry.name_of_institution = form_data["name_of_institution"] or None
        entry.cheque_rtgs_in_favour = form_data["cheque_rtgs_in_favour"] or None
        entry.notes = form_data["notes"] or None
        if target_status == models.BeneficiaryStatusChoices.SUBMITTED and (not entry.application_number or str(entry.application_number).startswith("DRAFT-PUB-")):
            entry.application_number = base_file_services.next_public_application_number()
        entry.status = target_status
        if not entry.created_by_id:
            entry.created_by = self.request.user
        entry.save()
        if previous_application_number and previous_application_number != entry.application_number:
            _rename_attachment_display_names_for_reference(
                attachments_qs=models.ApplicationAttachment.objects.filter(
                    application_type=models.ApplicationAttachmentTypeChoices.PUBLIC,
                    public_entry=entry,
                ),
                new_reference=entry.application_number or f"PUBLIC-{entry.pk}",
            )
        form_token = (self.request.POST.get("attachment_form_token") or "").strip()
        if form_token:
            _link_temp_attachments_to_application(
                request=self.request,
                application_type=models.ApplicationAttachmentTypeChoices.PUBLIC,
                form_token=form_token,
                application_reference=entry.application_number or f"PUBLIC-{entry.pk}",
                public_entry=entry,
            )
            _clear_attachment_form_token(self.request, models.ApplicationAttachmentTypeChoices.PUBLIC)
        log_audit(
            user=self.request.user,
            action_type=action_type,
            entity_type="public_application",
            entity_id=str(entry.id),
            details={"before": before_snapshot, "after": _public_audit_snapshot(entry)},
            **get_request_audit_meta(self.request),
        )
        if previous_status != target_status:
            log_audit(
                user=self.request.user,
                action_type=models.ActionTypeChoices.STATUS_CHANGE,
                entity_type="public_application",
                entity_id=str(entry.id),
                details={"from": previous_status, "to": target_status},
                **get_request_audit_meta(self.request),
            )
        return None, entry


class PublicMasterEntryCreateView(PublicMasterEntryBaseView):
    def get(self, request, *args, **kwargs):
        return self._render_form(form_data={"quantity": "1", "aadhaar_not_available": False})

    def post(self, request, *args, **kwargs):
        form_data = _build_public_form_data(request.POST)
        if request.POST.get("action") == "verify":
            if form_data.get("aadhaar_not_available"):
                return self._render_form(
                    form_data=form_data,
                    warnings=["Aadhaar is marked as not available. Verification will remain pending until Aadhaar is entered."],
                )
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
        if entry.status == models.BeneficiaryStatusChoices.ARCHIVED:
            messages.error(request, "This public application is archived. Unarchive it before editing.")
            return HttpResponseRedirect(reverse("ui:master-entry") + "?type=public&status=archived")
        if entry.status == models.BeneficiaryStatusChoices.SUBMITTED:
            messages.error(request, "This public application is submitted and locked. Reopen it first.")
            return HttpResponseRedirect(reverse("ui:master-entry") + "?type=public")
        return self._render_form(
            entry=entry,
            form_data={
                "aadhar_number": entry.aadhar_number or "",
                "aadhaar_not_available": entry.aadhaar_status == models.AadhaarVerificationStatusChoices.NOT_AVAILABLE,
                "name": entry.name,
                "is_handicapped": "true" if entry.is_handicapped and entry.is_handicapped != models.HandicappedStatusChoices.NO else "false",
                "disability_category": entry.is_handicapped if entry.is_handicapped and entry.is_handicapped != models.HandicappedStatusChoices.NO else "",
                "gender": entry.gender or "",
                "female_status": entry.female_status or "",
                "address": entry.address or "",
                "mobile": entry.mobile or "",
                "article_id": str(entry.article_id),
                "article_cost_per_unit": str(entry.article_cost_per_unit),
                "quantity": str(entry.quantity),
                "name_of_institution": entry.name_of_institution or "",
                "cheque_rtgs_in_favour": entry.cheque_rtgs_in_favour or "",
                "notes": entry.notes or "",
            },
            history_matches=_public_history_matches(entry.aadhar_number),
        )

    def post(self, request, *args, **kwargs):
        entry = self.get_entry()
        if entry.status == models.BeneficiaryStatusChoices.ARCHIVED:
            messages.error(request, "This public application is archived. Unarchive it before editing.")
            return HttpResponseRedirect(reverse("ui:master-entry") + "?type=public&status=archived")
        if entry.status == models.BeneficiaryStatusChoices.SUBMITTED:
            messages.error(request, "This public application is submitted and locked. Reopen it first.")
            return HttpResponseRedirect(reverse("ui:master-entry") + "?type=public")
        submitted_conflict_token = request.POST.get("_conflict_token", "")
        current_conflict_token = _public_conflict_token(entry)
        if submitted_conflict_token and current_conflict_token and submitted_conflict_token != current_conflict_token:
            messages.error(request, _conflict_message("public application"), extra_tags="persistent")
            return HttpResponseRedirect(reverse("ui:master-entry-public-edit", kwargs={"pk": entry.pk}))
        form_data = _build_public_form_data(request.POST)
        if request.POST.get("action") == "verify":
            if form_data.get("aadhaar_not_available"):
                return self._render_form(
                    entry=entry,
                    form_data=form_data,
                    warnings=["Aadhaar is marked as not available. Verification will remain pending until Aadhaar is entered."],
                )
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


class PublicMasterEntryDeleteView(LoginRequiredMixin, AdminRequiredMixin, View):
    module_key = models.ModuleKeyChoices.APPLICATION_ENTRY
    permission_action = "delete"
    def post(self, request, *args, **kwargs):
        entry = _public_any_queryset().get(pk=kwargs["pk"])
        snapshot = _public_audit_snapshot(entry)
        entry.delete()
        log_audit(
            user=request.user,
            action_type=models.ActionTypeChoices.DELETE,
            entity_type="public_application",
            entity_id=str(kwargs["pk"]),
            details={"before": snapshot},
            **get_request_audit_meta(request),
        )
        messages.warning(request, "Public entry deleted.")
        return HttpResponseRedirect(reverse("ui:master-entry") + "?type=public")


class PublicMasterEntryArchiveView(LoginRequiredMixin, AdminRequiredMixin, View):
    module_key = models.ModuleKeyChoices.APPLICATION_ENTRY
    permission_action = "delete"

    def post(self, request, *args, **kwargs):
        entry = get_object_or_404(_public_active_queryset(), pk=kwargs["pk"])
        snapshot_before = _public_audit_snapshot(entry)
        now = timezone.now()
        entry.archived_previous_status = entry.status or models.BeneficiaryStatusChoices.DRAFT
        entry.status = models.BeneficiaryStatusChoices.ARCHIVED
        entry.archived_at = now
        entry.archived_by = request.user
        entry.save(update_fields=["status", "archived_previous_status", "archived_at", "archived_by", "updated_at"])
        log_audit(
            user=request.user,
            action_type=models.ActionTypeChoices.UPDATE,
            entity_type="public_application",
            entity_id=str(entry.id),
            details={"before": snapshot_before, "after": _public_audit_snapshot(entry), "archive_action": "archived"},
            **get_request_audit_meta(request),
        )
        messages.success(request, "Public application archived.")
        return HttpResponseRedirect(reverse("ui:master-entry") + "?type=public")


class PublicMasterEntryUnarchiveView(LoginRequiredMixin, AdminRequiredMixin, View):
    module_key = models.ModuleKeyChoices.APPLICATION_ENTRY
    permission_action = "reopen"

    def post(self, request, *args, **kwargs):
        entry = get_object_or_404(models.PublicBeneficiaryEntry.objects.archived(), pk=kwargs["pk"])
        snapshot_before = _public_audit_snapshot(entry)
        restored_status = entry.archived_previous_status or models.BeneficiaryStatusChoices.DRAFT
        entry.status = restored_status
        entry.archived_previous_status = None
        entry.archived_at = None
        entry.archived_by = None
        entry.save(update_fields=["status", "archived_previous_status", "archived_at", "archived_by", "updated_at"])
        log_audit(
            user=request.user,
            action_type=models.ActionTypeChoices.UPDATE,
            entity_type="public_application",
            entity_id=str(entry.id),
            details={"before": snapshot_before, "after": _public_audit_snapshot(entry), "archive_action": "unarchived"},
            **get_request_audit_meta(request),
        )
        messages.success(request, "Public application unarchived.")
        return HttpResponseRedirect(reverse("ui:master-entry") + "?type=public")


class PublicMasterEntryReopenView(LoginRequiredMixin, AdminRequiredMixin, View):
    module_key = models.ModuleKeyChoices.APPLICATION_ENTRY
    permission_action = "reopen"
    def post(self, request, *args, **kwargs):
        entry = _public_any_queryset().get(pk=kwargs["pk"])
        if entry.status == models.BeneficiaryStatusChoices.ARCHIVED:
            messages.error(request, "Archived public applications must be unarchived first.")
            return HttpResponseRedirect(reverse("ui:master-entry") + "?type=public&status=archived")
        previous_status = entry.status
        entry.status = models.BeneficiaryStatusChoices.DRAFT
        entry.save(update_fields=["status"])
        log_audit(
            user=request.user,
            action_type=models.ActionTypeChoices.STATUS_CHANGE,
            entity_type="public_application",
            entity_id=str(entry.id),
            details={"from": previous_status, "to": models.BeneficiaryStatusChoices.DRAFT},
            **get_request_audit_meta(request),
        )
        messages.success(request, "Public application reopened as draft.")
        return HttpResponseRedirect(reverse("ui:master-entry") + "?type=public")


class InstitutionsMasterEntryBaseView(LoginRequiredMixin, WriteRoleMixin, TemplateView):
    module_key = models.ModuleKeyChoices.APPLICATION_ENTRY
    permission_action = "create_edit"
    template_name = "application_entry/master_entry_institution_form.html"

    def _render_form(self, *, form_data=None, rows=None, errors=None, application_number=None):
        context = self.get_context_data(
            **_institution_form_context(
                form_data=form_data,
                rows=rows,
                errors=errors,
                application_number=application_number,
            )
        )
        context.update(_institution_attachment_context_with_request(self.request, application_number))
        context["conflict_token"] = _institution_conflict_token(application_number)
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

        built_rows, row_errors = _validate_institution_rows(
            raw_rows,
            require_complete=require_complete,
            internal_notes=form_data["internal_notes"],
        )
        errors.extend(row_errors)

        if errors:
            article_lookup = {str(article.id): article for article in models.Article.objects.filter(is_active=True)}
            hydrated_rows = []
            for row in raw_rows:
                article = article_lookup.get(row["article_id"])
                hydrated_rows.append(
                    {
                        "article_id": row["article_id"],
                        "entry_id": row.get("entry_id", ""),
                        "quantity": row["quantity"],
                        "unit_cost": row["unit_cost"],
                        "notes": row["notes"],
                        "name_of_beneficiary": row.get("name_of_beneficiary", ""),
                        "name_of_institution": row.get("name_of_institution", ""),
                        "aadhar_number": row.get("aadhar_number", ""),
                        "cheque_rtgs_in_favour": row.get("cheque_rtgs_in_favour", ""),
                        "article_name": article.article_name if article else "",
                        "item_type": article.item_type if article else "",
                        "internal_notes": form_data["internal_notes"],
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
                application_number = base_file_services.next_institution_application_number()
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
                    _rename_attachment_display_names_for_reference(
                        attachments_qs=models.ApplicationAttachment.objects.filter(
                            application_type=models.ApplicationAttachmentTypeChoices.INSTITUTION,
                            institution_application_number=application_number,
                        ),
                        new_reference=application_number,
                    )
                log_audit(
                    user=self.request.user,
                    action_type=models.ActionTypeChoices.UPDATE,
                    entity_type="institution_application",
                    entity_id=application_number,
                    details={"before": before_snapshot, "after": _institution_audit_snapshot(application_number)},
                    **get_request_audit_meta(self.request),
                )
                if previous_status != target_status:
                    log_audit(
                        user=self.request.user,
                        action_type=models.ActionTypeChoices.STATUS_CHANGE,
                        entity_type="institution_application",
                        entity_id=application_number,
                        details={"from": previous_status, "to": target_status},
                        **get_request_audit_meta(self.request),
                    )
            else:
                for built in built_rows:
                    create_kwargs = {key: value for key, value in built.items() if key != "entry_id"}
                    models.InstitutionsBeneficiaryEntry.objects.create(
                        created_by=self.request.user,
                        application_number=application_number,
                        institution_name=form_data["institution_name"],
                        institution_type=form_data["institution_type"],
                        address=form_data["address"] or None,
                        mobile=form_data["mobile"] or None,
                        **create_kwargs,
                    )
                log_audit(
                    user=self.request.user,
                    action_type=models.ActionTypeChoices.CREATE,
                    entity_type="institution_application",
                    entity_id=application_number,
                    details={"after": _institution_audit_snapshot(application_number)},
                    **get_request_audit_meta(self.request),
                )
                log_audit(
                    user=self.request.user,
                    action_type=models.ActionTypeChoices.STATUS_CHANGE,
                    entity_type="institution_application",
                    entity_id=application_number,
                    details={"from": None, "to": target_status},
                    **get_request_audit_meta(self.request),
                )
        form_token = (self.request.POST.get("attachment_form_token") or "").strip()
        if form_token:
            _link_temp_attachments_to_application(
                request=self.request,
                application_type=models.ApplicationAttachmentTypeChoices.INSTITUTION,
                form_token=form_token,
                application_reference=application_number,
                institution_application_number=application_number,
            )
            _clear_attachment_form_token(self.request, models.ApplicationAttachmentTypeChoices.INSTITUTION)
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
                "entry_id": str(entry.id),
                "quantity": entry.quantity,
                "unit_cost": entry.article_cost_per_unit,
                "notes": entry.notes or "",
                "name_of_beneficiary": entry.name_of_beneficiary or "",
                "name_of_institution": entry.name_of_institution or "",
                "aadhar_number": entry.aadhar_number or "",
                "cheque_rtgs_in_favour": entry.cheque_rtgs_in_favour or "",
                "article_name": entry.article.article_name,
                "item_type": entry.article.item_type,
                "status": entry.status,
                "internal_notes": entry.internal_notes or "",
            }
            for entry in entries
        ]
        form_data = {
            "institution_name": first.institution_name,
            "institution_type": first.institution_type,
            "address": first.address or "",
            "mobile": first.mobile or "",
            "internal_notes": first.internal_notes or "",
        }
        return self._render_form(form_data=form_data, rows=rows, application_number=application_number)

    def post(self, request, *args, **kwargs):
        application_number = kwargs["application_number"]
        existing_entries = list(models.InstitutionsBeneficiaryEntry.objects.filter(application_number=application_number).order_by("id"))
        if existing_entries and existing_entries[0].status == models.BeneficiaryStatusChoices.SUBMITTED:
            messages.error(request, "This institution application is submitted and locked. Reopen it first.")
            return HttpResponseRedirect(reverse("ui:master-entry") + "?type=institutions")
        submitted_conflict_token = request.POST.get("_conflict_token", "")
        current_conflict_token = _institution_conflict_token(application_number)
        if submitted_conflict_token and current_conflict_token and submitted_conflict_token != current_conflict_token:
            messages.error(request, _conflict_message("institution application"), extra_tags="persistent")
            return HttpResponseRedirect(reverse("ui:master-entry-institution-edit", kwargs={"application_number": application_number}))
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


class InstitutionsMasterEntryDeleteView(LoginRequiredMixin, AdminRequiredMixin, View):
    module_key = models.ModuleKeyChoices.APPLICATION_ENTRY
    permission_action = "delete"
    def post(self, request, *args, **kwargs):
        application_number = kwargs["application_number"]
        snapshot = _institution_audit_snapshot(application_number)
        models.InstitutionsBeneficiaryEntry.objects.filter(application_number=application_number).delete()
        log_audit(
            user=request.user,
            action_type=models.ActionTypeChoices.DELETE,
            entity_type="institution_application",
            entity_id=application_number,
            details={"before": snapshot},
            **get_request_audit_meta(request),
        )
        messages.warning(request, "Institution entry deleted.")
        return HttpResponseRedirect(reverse("ui:master-entry") + "?type=institutions")


class InstitutionsMasterEntryReopenView(LoginRequiredMixin, AdminRequiredMixin, View):
    module_key = models.ModuleKeyChoices.APPLICATION_ENTRY
    permission_action = "reopen"
    def post(self, request, *args, **kwargs):
        application_number = kwargs["application_number"]
        models.InstitutionsBeneficiaryEntry.objects.filter(application_number=application_number).update(
            status=models.BeneficiaryStatusChoices.DRAFT
        )
        log_audit(
            user=request.user,
            action_type=models.ActionTypeChoices.STATUS_CHANGE,
            entity_type="institution_application",
            entity_id=application_number,
            details={"from": models.BeneficiaryStatusChoices.SUBMITTED, "to": models.BeneficiaryStatusChoices.DRAFT},
            **get_request_audit_meta(request),
        )
        messages.success(request, "Institution application reopened as draft.")
        return HttpResponseRedirect(reverse("ui:master-entry") + "?type=institutions")


class ApplicationAttachmentDownloadView(LoginRequiredMixin, RoleRequiredMixin, View):
    module_key = models.ModuleKeyChoices.APPLICATION_ENTRY
    permission_action = "view"
    def get(self, request, *args, **kwargs):
        attachment = get_object_or_404(models.ApplicationAttachment.objects.select_related("uploaded_by"), pk=kwargs["attachment_id"])
        if not attachment.file and not attachment.drive_file_id:
            messages.error(request, "This attachment is no longer available in Google Drive.")
            return HttpResponseRedirect(request.META.get("HTTP_REFERER") or reverse("ui:master-entry"))
        stored_name = attachment.file_name or (os.path.basename(attachment.file.name) if attachment.file else "attachment")
        application_reference = _attachment_application_reference(attachment)
        display_name = _prefixed_attachment_name(application_reference, stored_name, attachment.file_name or stored_name)
        as_attachment = (request.GET.get("download") or "").strip() == "1"
        content_type, _ = mimetypes.guess_type(stored_name)
        content_type = attachment.drive_mime_type or content_type or "application/octet-stream"
        if attachment.drive_file_id:
            try:
                file_bytes = google_drive.download_file(attachment.drive_file_id)
            except Exception as exc:
                logger.warning(
                    "Attachment download failed for attachment_id=%s drive_file_id=%s",
                    attachment.id,
                    attachment.drive_file_id,
                    exc_info=True,
                )
                if _is_probably_missing_drive_file_error(exc):
                    _mark_attachment_unavailable(attachment)
                    messages.error(request, "This attachment is no longer available in Google Drive.")
                else:
                    messages.error(request, "Attachment is temporarily unavailable. Please try again.")
                return HttpResponseRedirect(request.META.get("HTTP_REFERER") or reverse("ui:master-entry"))
            if as_attachment:
                display_root, display_ext = os.path.splitext(display_name)
                _, stored_ext = os.path.splitext(stored_name)
                download_name = display_name if display_ext else f"{display_name}{stored_ext}"
                response = HttpResponse(file_bytes, content_type=content_type)
                response["Content-Disposition"] = f'attachment; filename="{download_name}"'
                return response
            response = HttpResponse(file_bytes, content_type=content_type)
            response["Content-Disposition"] = "inline"
            return response
        if as_attachment:
            display_root, display_ext = os.path.splitext(display_name)
            _, stored_ext = os.path.splitext(stored_name)
            download_name = display_name if display_ext else f"{display_name}{stored_ext}"
            try:
                return FileResponse(
                    attachment.file.open("rb"),
                    as_attachment=True,
                    filename=download_name,
                    content_type=content_type,
                )
            except Exception:
                messages.error(request, "This attachment file is no longer available.")
                return HttpResponseRedirect(request.META.get("HTTP_REFERER") or reverse("ui:master-entry"))
        try:
            response = FileResponse(
                attachment.file.open("rb"),
                as_attachment=False,
                content_type=content_type,
            )
        except Exception:
            messages.error(request, "This attachment file is no longer available.")
            return HttpResponseRedirect(request.META.get("HTTP_REFERER") or reverse("ui:master-entry"))
        response["Content-Disposition"] = "inline"
        return response


class DistrictApplicationAttachmentTempUploadView(LoginRequiredMixin, WriteRoleMixin, View):
    module_key = models.ModuleKeyChoices.APPLICATION_ENTRY
    permission_action = "create_edit"

    @staticmethod
    def _target_url_for_district(district):
        if models.DistrictBeneficiaryEntry.objects.filter(district=district).exists():
            return reverse("ui:master-entry-district-edit", kwargs={"district_id": district.id})
        return f"{reverse('ui:master-entry-district-create')}?district_id={district.id}"

    def post(self, request, *args, **kwargs):
        district_id = (request.POST.get("district_id") or "").strip()
        if not district_id:
            messages.error(request, "Select a district before uploading attachments.")
            return HttpResponseRedirect(reverse("ui:master-entry-district-create"))
        district = get_object_or_404(models.DistrictMaster, pk=district_id, is_active=True)
        target_url = self._target_url_for_district(district)
        form = ApplicationAttachmentUploadForm(request.POST, request.FILES)
        if not form.is_valid():
            messages.error(request, "; ".join(form.errors.get("file", []) + form.errors.get("file_name", [])) or "Choose a valid file before uploading.")
            return HttpResponseRedirect(target_url)

        attachments_qs = models.ApplicationAttachment.objects.filter(
            application_type=models.ApplicationAttachmentTypeChoices.DISTRICT,
            district=district,
            status=models.ApplicationAttachmentStatusChoices.LINKED,
        )
        existing_count = attachments_qs.count()
        if existing_count >= ApplicationAttachmentUploadForm.MAX_FILES_PER_APPLICATION:
            messages.error(request, f"Maximum {ApplicationAttachmentUploadForm.MAX_FILES_PER_APPLICATION} files are allowed for one application.")
            return HttpResponseRedirect(target_url)

        uploaded = form.cleaned_data["file"]
        display_name = _prefixed_attachment_name(district.application_number, uploaded.name, form.cleaned_data.get("file_name") or "")
        if _attachment_name_exists(attachments_qs, display_name):
            messages.error(request, "A file with this name already exists for this application. Please rename it before uploading.")
            return HttpResponseRedirect(target_url)
        try:
            _save_application_attachment(
                uploaded=uploaded,
                display_name=display_name,
                application_type=models.ApplicationAttachmentTypeChoices.DISTRICT,
                district=district,
                uploaded_by=request.user,
            )
        except Exception:
            logger.exception("Attachment upload failed for district=%s", district.id)
            if not google_drive.is_configured():
                messages.error(
                    request,
                    "Google Drive is not configured for uploads in this environment. "
                    "Set GOOGLE_DRIVE_APPLICATIONS_FOLDER_ID, GOOGLE_DRIVE_CLIENT_ID, "
                    "GOOGLE_DRIVE_CLIENT_SECRET, and GOOGLE_DRIVE_REFRESH_TOKEN."
                )
            else:
                messages.error(request, "Attachment upload failed. Please check Google Drive configuration and try again.")
            return HttpResponseRedirect(target_url)
        messages.success(request, "Attachment uploaded.")
        return HttpResponseRedirect(target_url)


class DistrictApplicationAttachmentUploadView(LoginRequiredMixin, WriteRoleMixin, View):
    module_key = models.ModuleKeyChoices.APPLICATION_ENTRY
    permission_action = "create_edit"
    def post(self, request, *args, **kwargs):
        district = get_object_or_404(models.DistrictMaster, pk=kwargs["district_id"], is_active=True)
        form = ApplicationAttachmentUploadForm(request.POST, request.FILES)
        if not form.is_valid():
            messages.error(request, "; ".join(form.errors.get("file", []) + form.errors.get("file_name", [])) or "Choose a valid file before uploading.")
            return HttpResponseRedirect(reverse("ui:master-entry-district-edit", kwargs={"district_id": district.id}))

        attachments_qs = models.ApplicationAttachment.objects.filter(
            application_type=models.ApplicationAttachmentTypeChoices.DISTRICT,
            district=district,
        )
        existing_count = attachments_qs.count()
        if existing_count >= ApplicationAttachmentUploadForm.MAX_FILES_PER_APPLICATION:
            messages.error(request, f"Maximum {ApplicationAttachmentUploadForm.MAX_FILES_PER_APPLICATION} files are allowed for one application.")
            return HttpResponseRedirect(reverse("ui:master-entry-district-edit", kwargs={"district_id": district.id}))

        uploaded = form.cleaned_data["file"]
        display_name = _prefixed_attachment_name(district.application_number, uploaded.name, form.cleaned_data.get("file_name") or "")
        if _attachment_name_exists(attachments_qs, display_name):
            messages.error(request, "A file with this name already exists for this application. Please rename it before uploading.")
            return HttpResponseRedirect(reverse("ui:master-entry-district-edit", kwargs={"district_id": district.id}))
        try:
            _save_application_attachment(
                uploaded=uploaded,
                display_name=display_name,
                application_type=models.ApplicationAttachmentTypeChoices.DISTRICT,
                district=district,
                uploaded_by=request.user,
            )
        except Exception:
            logger.exception("Attachment upload failed for district=%s", district.id)
            if not google_drive.is_configured():
                messages.error(
                    request,
                    "Google Drive is not configured for uploads in this environment. "
                    "Set GOOGLE_DRIVE_APPLICATIONS_FOLDER_ID, GOOGLE_DRIVE_CLIENT_ID, "
                    "GOOGLE_DRIVE_CLIENT_SECRET, and GOOGLE_DRIVE_REFRESH_TOKEN."
                )
            else:
                messages.error(request, "Attachment upload failed. Please check Google Drive configuration and try again.")
            return HttpResponseRedirect(reverse("ui:master-entry-district-edit", kwargs={"district_id": district.id}))
        messages.success(request, "Attachment uploaded.")
        return HttpResponseRedirect(reverse("ui:master-entry-district-edit", kwargs={"district_id": district.id}))


class DistrictApplicationAttachmentDeleteView(LoginRequiredMixin, WriteRoleMixin, View):
    module_key = models.ModuleKeyChoices.APPLICATION_ENTRY
    permission_action = "create_edit"
    def post(self, request, *args, **kwargs):
        district = get_object_or_404(models.DistrictMaster, pk=kwargs["district_id"], is_active=True)
        attachment = get_object_or_404(
            models.ApplicationAttachment,
            pk=kwargs["attachment_id"],
            application_type=models.ApplicationAttachmentTypeChoices.DISTRICT,
            district=district,
        )
        _delete_application_attachment_file(attachment)
        attachment.delete()
        messages.success(request, "Attachment removed.")
        return HttpResponseRedirect(reverse("ui:master-entry-district-edit", kwargs={"district_id": district.id}))


class PublicApplicationAttachmentUploadView(LoginRequiredMixin, WriteRoleMixin, View):
    module_key = models.ModuleKeyChoices.APPLICATION_ENTRY
    permission_action = "create_edit"
    def post(self, request, *args, **kwargs):
        entry = get_object_or_404(_public_any_queryset(), pk=kwargs["pk"])
        if entry.status == models.BeneficiaryStatusChoices.ARCHIVED:
            messages.error(request, "This public application is archived. Unarchive it before uploading attachments.")
            return HttpResponseRedirect(reverse("ui:master-entry") + "?type=public&status=archived")
        form = ApplicationAttachmentUploadForm(request.POST, request.FILES)
        if not form.is_valid():
            messages.error(request, "; ".join(form.errors.get("file", []) + form.errors.get("file_name", [])) or "Choose a valid file before uploading.")
            return HttpResponseRedirect(reverse("ui:master-entry-public-edit", kwargs={"pk": entry.pk}))

        attachments_qs = models.ApplicationAttachment.objects.filter(
            application_type=models.ApplicationAttachmentTypeChoices.PUBLIC,
            public_entry=entry,
        )
        existing_count = attachments_qs.count()
        if existing_count >= ApplicationAttachmentUploadForm.MAX_FILES_PER_APPLICATION:
            messages.error(request, f"Maximum {ApplicationAttachmentUploadForm.MAX_FILES_PER_APPLICATION} files are allowed for one application.")
            return HttpResponseRedirect(reverse("ui:master-entry-public-edit", kwargs={"pk": entry.pk}))

        uploaded = form.cleaned_data["file"]
        application_reference = entry.application_number or f"PUBLIC-{entry.pk}"
        display_name = _prefixed_attachment_name(application_reference, uploaded.name, form.cleaned_data.get("file_name") or "")
        if _attachment_name_exists(attachments_qs, display_name):
            messages.error(request, "A file with this name already exists for this application. Please rename it before uploading.")
            return HttpResponseRedirect(reverse("ui:master-entry-public-edit", kwargs={"pk": entry.pk}))
        try:
            _save_application_attachment(
                uploaded=uploaded,
                display_name=display_name,
                application_type=models.ApplicationAttachmentTypeChoices.PUBLIC,
                public_entry=entry,
                uploaded_by=request.user,
            )
        except Exception:
            logger.exception("Attachment upload failed for public_entry=%s", entry.pk)
            if not google_drive.is_configured():
                messages.error(
                    request,
                    "Google Drive is not configured for uploads in this environment. "
                    "Set GOOGLE_DRIVE_APPLICATIONS_FOLDER_ID, GOOGLE_DRIVE_CLIENT_ID, "
                    "GOOGLE_DRIVE_CLIENT_SECRET, and GOOGLE_DRIVE_REFRESH_TOKEN."
                )
            else:
                messages.error(request, "Attachment upload failed. Please check Google Drive configuration and try again.")
            return HttpResponseRedirect(reverse("ui:master-entry-public-edit", kwargs={"pk": entry.pk}))
        messages.success(request, "Attachment uploaded.")
        return HttpResponseRedirect(reverse("ui:master-entry-public-edit", kwargs={"pk": entry.pk}))


class PublicApplicationAttachmentTempUploadView(LoginRequiredMixin, WriteRoleMixin, View):
    module_key = models.ModuleKeyChoices.APPLICATION_ENTRY
    permission_action = "create_edit"

    def post(self, request, *args, **kwargs):
        form_token = (request.POST.get("attachment_form_token") or "").strip() or _ensure_attachment_form_token(
            request, models.ApplicationAttachmentTypeChoices.PUBLIC
        )
        _save_temp_attachment_upload(
            request=request,
            application_type=models.ApplicationAttachmentTypeChoices.PUBLIC,
            form_token=form_token,
        )
        return HttpResponseRedirect(reverse("ui:master-entry-public-create"))


class PublicApplicationAttachmentDeleteView(LoginRequiredMixin, WriteRoleMixin, View):
    module_key = models.ModuleKeyChoices.APPLICATION_ENTRY
    permission_action = "create_edit"
    def post(self, request, *args, **kwargs):
        entry = get_object_or_404(_public_any_queryset(), pk=kwargs["pk"])
        if entry.status == models.BeneficiaryStatusChoices.ARCHIVED:
            messages.error(request, "This public application is archived. Unarchive it before editing attachments.")
            return HttpResponseRedirect(reverse("ui:master-entry") + "?type=public&status=archived")
        attachment = get_object_or_404(
            models.ApplicationAttachment,
            pk=kwargs["attachment_id"],
            application_type=models.ApplicationAttachmentTypeChoices.PUBLIC,
            public_entry=entry,
        )
        _delete_application_attachment_file(attachment)
        attachment.delete()
        messages.success(request, "Attachment removed.")
        return HttpResponseRedirect(reverse("ui:master-entry-public-edit", kwargs={"pk": entry.pk}))


class PublicApplicationAttachmentTempDeleteView(LoginRequiredMixin, WriteRoleMixin, View):
    module_key = models.ModuleKeyChoices.APPLICATION_ENTRY
    permission_action = "create_edit"

    def post(self, request, *args, **kwargs):
        form_token = (request.POST.get("attachment_form_token") or "").strip()
        attachment = get_object_or_404(
            models.ApplicationAttachment,
            pk=kwargs["attachment_id"],
            application_type=models.ApplicationAttachmentTypeChoices.PUBLIC,
            status=models.ApplicationAttachmentStatusChoices.TEMP,
            uploaded_by=request.user,
        )
        if form_token and attachment.form_token and attachment.form_token != form_token:
            messages.error(request, "Attachment token mismatch. Refresh and try again.")
            return HttpResponseRedirect(reverse("ui:master-entry-public-create"))
        _delete_application_attachment_file(attachment)
        attachment.delete()
        messages.success(request, "Attachment removed.")
        return HttpResponseRedirect(reverse("ui:master-entry-public-create"))


class PublicApplicationAttachmentTempClearView(LoginRequiredMixin, WriteRoleMixin, View):
    module_key = models.ModuleKeyChoices.APPLICATION_ENTRY
    permission_action = "create_edit"

    def post(self, request, *args, **kwargs):
        form_token = (request.POST.get("attachment_form_token") or "").strip()
        if not form_token:
            return HttpResponseRedirect(reverse("ui:master-entry-public-create"))
        temp_items = list(
            _temp_attachment_queryset(
                application_type=models.ApplicationAttachmentTypeChoices.PUBLIC,
                form_token=form_token,
                user=request.user,
            )
        )
        for attachment in temp_items:
            _delete_application_attachment_file(attachment)
            attachment.delete()
        _clear_attachment_form_token(request, models.ApplicationAttachmentTypeChoices.PUBLIC)
        messages.success(request, "Uploaded temporary files were removed.")
        return HttpResponseRedirect(reverse("ui:master-entry-public-create"))


class InstitutionApplicationAttachmentUploadView(LoginRequiredMixin, WriteRoleMixin, View):
    module_key = models.ModuleKeyChoices.APPLICATION_ENTRY
    permission_action = "create_edit"
    def post(self, request, *args, **kwargs):
        application_number = kwargs["application_number"]
        if not models.InstitutionsBeneficiaryEntry.objects.filter(application_number=application_number).exists():
            raise Http404("Institution application not found.")
        form = ApplicationAttachmentUploadForm(request.POST, request.FILES)
        if not form.is_valid():
            messages.error(request, "; ".join(form.errors.get("file", []) + form.errors.get("file_name", [])) or "Choose a valid file before uploading.")
            return HttpResponseRedirect(reverse("ui:master-entry-institution-edit", kwargs={"application_number": application_number}))

        attachments_qs = models.ApplicationAttachment.objects.filter(
            application_type=models.ApplicationAttachmentTypeChoices.INSTITUTION,
            institution_application_number=application_number,
        )
        existing_count = attachments_qs.count()
        if existing_count >= ApplicationAttachmentUploadForm.MAX_FILES_PER_APPLICATION:
            messages.error(request, f"Maximum {ApplicationAttachmentUploadForm.MAX_FILES_PER_APPLICATION} files are allowed for one application.")
            return HttpResponseRedirect(reverse("ui:master-entry-institution-edit", kwargs={"application_number": application_number}))

        uploaded = form.cleaned_data["file"]
        display_name = _prefixed_attachment_name(application_number, uploaded.name, form.cleaned_data.get("file_name") or "")
        if _attachment_name_exists(attachments_qs, display_name):
            messages.error(request, "A file with this name already exists for this application. Please rename it before uploading.")
            return HttpResponseRedirect(reverse("ui:master-entry-institution-edit", kwargs={"application_number": application_number}))
        try:
            _save_application_attachment(
                uploaded=uploaded,
                display_name=display_name,
                application_type=models.ApplicationAttachmentTypeChoices.INSTITUTION,
                institution_application_number=application_number,
                uploaded_by=request.user,
            )
        except Exception:
            logger.exception("Attachment upload failed for institution=%s", application_number)
            if not google_drive.is_configured():
                messages.error(
                    request,
                    "Google Drive is not configured for uploads in this environment. "
                    "Set GOOGLE_DRIVE_APPLICATIONS_FOLDER_ID, GOOGLE_DRIVE_CLIENT_ID, "
                    "GOOGLE_DRIVE_CLIENT_SECRET, and GOOGLE_DRIVE_REFRESH_TOKEN."
                )
            else:
                messages.error(request, "Attachment upload failed. Please check Google Drive configuration and try again.")
            return HttpResponseRedirect(reverse("ui:master-entry-institution-edit", kwargs={"application_number": application_number}))
        messages.success(request, "Attachment uploaded.")
        return HttpResponseRedirect(reverse("ui:master-entry-institution-edit", kwargs={"application_number": application_number}))


class InstitutionApplicationAttachmentTempUploadView(LoginRequiredMixin, WriteRoleMixin, View):
    module_key = models.ModuleKeyChoices.APPLICATION_ENTRY
    permission_action = "create_edit"

    def post(self, request, *args, **kwargs):
        form_token = (request.POST.get("attachment_form_token") or "").strip() or _ensure_attachment_form_token(
            request, models.ApplicationAttachmentTypeChoices.INSTITUTION
        )
        _save_temp_attachment_upload(
            request=request,
            application_type=models.ApplicationAttachmentTypeChoices.INSTITUTION,
            form_token=form_token,
        )
        return HttpResponseRedirect(reverse("ui:master-entry-institution-create"))


class InstitutionApplicationAttachmentDeleteView(LoginRequiredMixin, WriteRoleMixin, View):
    module_key = models.ModuleKeyChoices.APPLICATION_ENTRY
    permission_action = "create_edit"
    def post(self, request, *args, **kwargs):
        application_number = kwargs["application_number"]
        attachment = get_object_or_404(
            models.ApplicationAttachment,
            pk=kwargs["attachment_id"],
            application_type=models.ApplicationAttachmentTypeChoices.INSTITUTION,
            institution_application_number=application_number,
        )
        _delete_application_attachment_file(attachment)
        attachment.delete()
        messages.success(request, "Attachment removed.")
        return HttpResponseRedirect(reverse("ui:master-entry-institution-edit", kwargs={"application_number": application_number}))


class InstitutionApplicationAttachmentTempDeleteView(LoginRequiredMixin, WriteRoleMixin, View):
    module_key = models.ModuleKeyChoices.APPLICATION_ENTRY
    permission_action = "create_edit"

    def post(self, request, *args, **kwargs):
        form_token = (request.POST.get("attachment_form_token") or "").strip()
        attachment = get_object_or_404(
            models.ApplicationAttachment,
            pk=kwargs["attachment_id"],
            application_type=models.ApplicationAttachmentTypeChoices.INSTITUTION,
            status=models.ApplicationAttachmentStatusChoices.TEMP,
            uploaded_by=request.user,
        )
        if form_token and attachment.form_token and attachment.form_token != form_token:
            messages.error(request, "Attachment token mismatch. Refresh and try again.")
            return HttpResponseRedirect(reverse("ui:master-entry-institution-create"))
        _delete_application_attachment_file(attachment)
        attachment.delete()
        messages.success(request, "Attachment removed.")
        return HttpResponseRedirect(reverse("ui:master-entry-institution-create"))


class InstitutionApplicationAttachmentTempClearView(LoginRequiredMixin, WriteRoleMixin, View):
    module_key = models.ModuleKeyChoices.APPLICATION_ENTRY
    permission_action = "create_edit"

    def post(self, request, *args, **kwargs):
        form_token = (request.POST.get("attachment_form_token") or "").strip()
        if not form_token:
            return HttpResponseRedirect(reverse("ui:master-entry-institution-create"))
        temp_items = list(
            _temp_attachment_queryset(
                application_type=models.ApplicationAttachmentTypeChoices.INSTITUTION,
                form_token=form_token,
                user=request.user,
            )
        )
        for attachment in temp_items:
            _delete_application_attachment_file(attachment)
            attachment.delete()
        _clear_attachment_form_token(request, models.ApplicationAttachmentTypeChoices.INSTITUTION)
        messages.success(request, "Uploaded temporary files were removed.")
        return HttpResponseRedirect(reverse("ui:master-entry-institution-create"))
