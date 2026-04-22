from __future__ import annotations

import base64
import json
import logging
import mimetypes
import os
import uuid
from dataclasses import dataclass
from datetime import timedelta

from django.urls import reverse
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from core import models
from core.application_entry import drive_service
from core.application_entry.forms import ApplicationAttachmentUploadForm

logger = logging.getLogger(__name__)


def available_attachment_q():
    return Q(drive_file_id__gt="")


def is_configured() -> bool:
    return drive_service.is_configured()


def is_probably_missing_drive_file_error(exc: Exception) -> bool:
    message = str(exc or "").lower()
    return any(marker in message for marker in ("404", "not found", "filenotfound", "file not found", "requested entity was not found"))


def mark_attachment_unavailable(attachment):
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
    if getattr(attachment, "status", "") != models.ApplicationAttachmentStatusChoices.MISSING:
        attachment.status = models.ApplicationAttachmentStatusChoices.MISSING
        update_fields.append("status")
    if update_fields:
        attachment.save(update_fields=update_fields)


def attachment_form_token_session_key(application_type):
    return f"application_attachment_draft_uid:{str(application_type or '').strip().lower()}"


def ensure_attachment_form_token(request, application_type):
    key = attachment_form_token_session_key(application_type)
    token = (request.session.get(key) or "").strip()
    if token:
        return token
    token = str(uuid.uuid4())
    request.session[key] = token
    request.session.modified = True
    return token


def clear_attachment_form_token(request, application_type):
    key = attachment_form_token_session_key(application_type)
    if key in request.session:
        request.session.pop(key, None)
        request.session.modified = True


def prefixed_attachment_name(application_reference, uploaded_name, custom_name=""):
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


def attachment_name_exists(queryset, final_name):
    normalized = (final_name or "").strip().lower()
    if not normalized:
        return False
    for existing_name in queryset.values_list("file_name", flat=True):
        if (existing_name or "").strip().lower() == normalized:
            return True
    return False


def attachment_application_reference(attachment):
    if not attachment:
        return ""
    if attachment.prefix:
        return str(attachment.prefix).strip()
    if attachment.application_type == models.ApplicationAttachmentTypeChoices.DISTRICT and attachment.district_id:
        return attachment.district.application_number or ""
    if attachment.application_type == models.ApplicationAttachmentTypeChoices.PUBLIC and attachment.public_entry_id:
        return attachment.public_entry.application_number or f"PUBLIC-{attachment.public_entry_id}"
    if attachment.application_type == models.ApplicationAttachmentTypeChoices.INSTITUTION:
        return attachment.institution_application_number or ""
    return ""


def save_application_attachment(*, uploaded, display_name, application_type, uploaded_by, district=None, public_entry=None, institution_application_number=None):
    original_filename = str(getattr(uploaded, "name", "") or "").strip() or "attachment"
    display_filename = (display_name or "").strip() or original_filename
    prefix = ""
    if district is not None:
        prefix = district.application_number or ""
    elif public_entry is not None:
        prefix = public_entry.application_number or ""
    elif institution_application_number is not None:
        prefix = institution_application_number
    attachment_kwargs = {
        "application_type": application_type,
        "district": district,
        "public_entry": public_entry,
        "institution_application_number": institution_application_number,
        "prefix": prefix,
        "original_filename": original_filename,
        "display_filename": display_filename,
        "file_name": display_filename,
        "uploaded_by": uploaded_by,
        "status": models.ApplicationAttachmentStatusChoices.LINKED,
    }
    if not drive_service.is_configured():
        raise RuntimeError("Google Drive is not configured for attachments in this environment.")
    uploaded.seek(0)
    result = drive_service.upload_attachment(
        application_type=application_type,
        reference=prefix,
        filename=display_name,
        content=uploaded.read(),
        content_type=str(getattr(uploaded, "content_type", "") or mimetypes.guess_type(display_name)[0] or "application/octet-stream"),
    )
    attachment_kwargs.update(
        {
            "drive_file_id": result.file_id,
            "drive_mime_type": result.mime_type,
            "drive_view_url": result.view_url,
        }
    )
    return models.ApplicationAttachment.objects.create(**attachment_kwargs)


def delete_application_attachment_file(attachment):
    try:
        if attachment.drive_file_id:
            drive_service.delete_attachment(attachment.drive_file_id)
        elif attachment.file:
            attachment.file.delete(save=False)
    except Exception:
        logger.exception("Failed to delete attachment file (id=%s). Continuing.", getattr(attachment, "id", None))


def attachment_exists(file_id: str) -> bool:
    if not file_id:
        return False
    drive_service.attachment_exists(file_id)
    return True


def download_attachment(file_id: str) -> bytes:
    return drive_service.download_attachment(file_id)


def cleanup_application_attachments(*, application_type, district=None, public_entry=None, institution_application_number=None):
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
    attachments = list(models.ApplicationAttachment.objects.filter(**filters))
    failures = []
    for attachment in attachments:
        try:
            delete_application_attachment_file(attachment)
        except Exception as exc:
            if is_probably_missing_drive_file_error(exc):
                continue
            failures.append(attachment.id)
            logger.warning("Attachment cleanup failed for attachment_id=%s while deleting application", attachment.id, exc_info=True)
    if failures:
        return False, len(attachments), len(failures)
    if attachments:
        models.ApplicationAttachment.objects.filter(id__in=[item.id for item in attachments]).delete()
    return True, len(attachments), 0


def temp_attachment_queryset(*, application_type, form_token, user):
    queryset = models.ApplicationAttachment.objects.filter(
        application_type=application_type,
        status=models.ApplicationAttachmentStatusChoices.TEMP,
        draft_uid=form_token,
        uploaded_by=user,
    )
    return queryset.filter(available_attachment_q()).order_by("-created_at", "-id")


def linked_attachment_queryset(*, application_type, district=None, public_entry=None, institution_application_number=None):
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
    return models.ApplicationAttachment.objects.filter(**filters).filter(available_attachment_q()).order_by("-created_at", "-id")


def rename_attachment_display_names_for_reference(*, attachments_qs, new_reference):
    reference = (new_reference or "").strip()
    if not reference:
        return
    for attachment in attachments_qs.order_by("id"):
        current_name = (attachment.display_filename or attachment.file_name or attachment.original_filename or "").strip() or "attachment"
        bare_name = current_name
        current_prefix = (attachment.prefix or "").strip()
        if current_prefix and bare_name.startswith(f"{current_prefix}_"):
            bare_name = bare_name[len(f"{current_prefix}_") :]
        renamed = prefixed_attachment_name(reference, bare_name, bare_name)
        if renamed == current_name:
            continue
        attachment.prefix = reference
        attachment.display_filename = renamed
        attachment.file_name = renamed
        update_fields = ["prefix", "display_filename", "file_name"]
        if attachment.drive_file_id:
            try:
                drive_data = drive_service.rename_attachment(attachment.drive_file_id, renamed)
                attachment.drive_mime_type = str(drive_data.mime_type or attachment.drive_mime_type or "").strip()
                attachment.drive_view_url = str(drive_data.view_url or attachment.drive_view_url or "").strip()
                update_fields.extend(["drive_mime_type", "drive_view_url"])
            except Exception as exc:
                logger.warning("Attachment rename failed for attachment_id=%s", attachment.id, exc_info=True)
                raise RuntimeError(f"Failed to rename Drive attachment {attachment.id}") from exc
        attachment.save(update_fields=sorted(set(update_fields)))


def link_temp_attachments_to_application(
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
        temp_attachment_queryset(
            application_type=application_type,
            form_token=form_token,
            user=request.user,
        )
    )
    for attachment in temp_items:
        bare_name = (attachment.original_filename or attachment.display_filename or attachment.file_name or "").strip() or "attachment"
        normalized_reference = (application_reference or "").strip()
        is_draft_reference = normalized_reference.startswith("DRAFT-") or normalized_reference.startswith("DRAFT_")
        target_prefix = f"DRAFT_{form_token}" if is_draft_reference else normalized_reference
        renamed = prefixed_attachment_name(target_prefix, bare_name, bare_name)
        attachment.prefix = target_prefix
        attachment.file_name = renamed
        attachment.display_filename = renamed
        attachment.status = models.ApplicationAttachmentStatusChoices.LINKED
        attachment.draft_uid = form_token if is_draft_reference else None
        attachment.temp_expires_at = None
        if district is not None:
            attachment.application_id = district.id
            attachment.district = district
        if public_entry is not None:
            attachment.application_id = public_entry.id
            attachment.public_entry = public_entry
        if institution_application_number is not None:
            attachment.institution_application_number = institution_application_number
        update_fields = [
            "application_id",
            "prefix",
            "file_name",
            "display_filename",
            "status",
            "draft_uid",
            "temp_expires_at",
            "district",
            "public_entry",
            "institution_application_number",
        ]
        if attachment.drive_file_id:
            try:
                drive_data = drive_service.rename_attachment(attachment.drive_file_id, renamed)
                attachment.drive_mime_type = str(drive_data.mime_type or attachment.drive_mime_type or "").strip()
                attachment.drive_view_url = str(drive_data.view_url or attachment.drive_view_url or "").strip()
                update_fields.extend(["drive_mime_type", "drive_view_url"])
            except Exception as exc:
                logger.warning("Attachment relink rename failed for attachment_id=%s", attachment.id, exc_info=True)
                raise RuntimeError(f"Failed to relink Drive attachment {attachment.id}") from exc
        attachment.save(update_fields=sorted(set(update_fields)))


def save_temp_attachment_upload(
    *,
    request,
    application_type,
    form_token,
    initial_prefix="",
    save_kwargs=None,
    temp_scope_filters=None,
):
    form = ApplicationAttachmentUploadForm(request.POST, request.FILES)
    if not form.is_valid():
        return False, "; ".join(form.errors.get("file", []) + form.errors.get("file_name", [])) or "Choose a valid file before uploading."

    uploaded = form.cleaned_data["file"]
    raw_name = form.cleaned_data.get("file_name") or uploaded.name
    draft_prefix = (initial_prefix or "").strip() or f"DRAFT_{form_token}"
    base_name = (raw_name or "").strip() or (uploaded.name or "attachment")
    display_name = prefixed_attachment_name(draft_prefix, uploaded.name, base_name)
    existing_names_qs = models.ApplicationAttachment.objects.filter(
        application_type=application_type,
        status=models.ApplicationAttachmentStatusChoices.TEMP,
        draft_uid=form_token,
        uploaded_by=request.user,
        **(temp_scope_filters or {}),
    )
    if attachment_name_exists(existing_names_qs, display_name):
        return False, "A file with this name already exists. Please rename it before uploading."

    try:
        with transaction.atomic():
            locked_qs = (
                models.ApplicationAttachment.objects.select_for_update()
                .filter(
                    application_type=application_type,
                    status=models.ApplicationAttachmentStatusChoices.TEMP,
                    draft_uid=form_token,
                    uploaded_by=request.user,
                    **(temp_scope_filters or {}),
                )
            )
            existing_count = locked_qs.filter(available_attachment_q()).count()
            if existing_count >= ApplicationAttachmentUploadForm.MAX_FILES_PER_APPLICATION:
                return False, f"Maximum {ApplicationAttachmentUploadForm.MAX_FILES_PER_APPLICATION} files are allowed for one application."
            if attachment_name_exists(locked_qs, display_name):
                return False, "A file with this name already exists. Please rename it before uploading."
            attachment = save_application_attachment(
                uploaded=uploaded,
                display_name=display_name,
                application_type=application_type,
                uploaded_by=request.user,
                **(save_kwargs or {}),
            )
    except Exception as exc:
        logger.exception("Temporary attachment upload failed for %s", application_type)
        message = f"{exc.__class__.__name__}: {exc}".strip()
        if message.endswith(":"):
            message = "Attachment upload failed. Please check Google Drive configuration and try again."
        return False, message

    attachment.status = models.ApplicationAttachmentStatusChoices.TEMP
    attachment.draft_uid = form_token
    attachment.prefix = draft_prefix
    attachment.display_filename = display_name
    attachment.original_filename = uploaded.name or attachment.original_filename
    attachment.file_name = display_name
    attachment.temp_expires_at = timezone.now() + timedelta(hours=24)
    attachment.save(
        update_fields=[
            "status",
            "draft_uid",
            "prefix",
            "display_filename",
            "original_filename",
            "file_name",
            "temp_expires_at",
        ]
    )
    return True, "Attachment uploaded."


def save_linked_attachment_upload(*, request, uploaded, application_type, display_name, queryset_filters, save_kwargs):
    with transaction.atomic():
        attachments_qs = (
            models.ApplicationAttachment.objects.select_for_update()
            .filter(**queryset_filters)
            .filter(available_attachment_q())
        )
        existing_count = attachments_qs.count()
        if existing_count >= ApplicationAttachmentUploadForm.MAX_FILES_PER_APPLICATION:
            return False, f"Maximum {ApplicationAttachmentUploadForm.MAX_FILES_PER_APPLICATION} files are allowed for one application."
        if attachment_name_exists(attachments_qs, display_name):
            return False, "A file with this name already exists for this application. Please rename it before uploading."
        save_application_attachment(
            uploaded=uploaded,
            display_name=display_name,
            application_type=application_type,
            uploaded_by=request.user,
            **save_kwargs,
        )
    return True, ""


def cleanup_stale_temp_attachments():
    expiry_cutoff = timezone.now()
    stale_qs = models.ApplicationAttachment.objects.filter(
        status=models.ApplicationAttachmentStatusChoices.TEMP,
        temp_expires_at__lt=expiry_cutoff,
    )
    for attachment in stale_qs.iterator():
        delete_application_attachment_file(attachment)
        attachment.delete()


def sync_drive_attachments_for_application(*, application_type, application_reference, district=None, public_entry=None, institution_application_number=None):
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

    existing_qs = models.ApplicationAttachment.objects.filter(**filters).filter(available_attachment_q())
    existing_file_ids = set(existing_qs.values_list("drive_file_id", flat=True))
    existing_names = {str(name or "").strip().casefold() for name in existing_qs.values_list("file_name", flat=True)}

    try:
        drive_files = drive_service.google_drive.list_application_attachments(
            application_type=application_type,
            application_reference=application_reference,
        )
    except Exception:
        logger.warning("Drive attachment scan failed for application_reference=%s", application_reference, exc_info=True)
        return list(existing_qs.select_related("uploaded_by").order_by("-created_at", "-id"))

    for drive_file in drive_files:
        file_id = str(drive_file.get("file_id") or "").strip()
        file_name = str(drive_file.get("file_name") or "").strip()
        if not file_id or file_id in existing_file_ids:
            continue
        if file_name and file_name.casefold() in existing_names:
            continue
        try:
            models.ApplicationAttachment.objects.create(
                application_type=application_type,
                district=district,
                public_entry=public_entry,
                institution_application_number=institution_application_number,
                original_filename=file_name,
                display_filename=file_name,
                prefix=(application_reference or "").strip(),
                file_name=file_name,
                drive_file_id=file_id,
                drive_mime_type=str(drive_file.get("mime_type") or "").strip(),
                drive_view_url=str(drive_file.get("view_url") or "").strip(),
                status=models.ApplicationAttachmentStatusChoices.LINKED,
            )
        except Exception:
            logger.warning("Failed to register manually uploaded attachment file_id=%s", file_id, exc_info=True)

    return list(
        models.ApplicationAttachment.objects.filter(**filters)
        .filter(available_attachment_q())
        .select_related("uploaded_by")
        .order_by("-created_at", "-id")
    )


def attachment_preview_title(attachment):
    if not attachment:
        return ""
    if attachment.display_filename:
        return attachment.display_filename
    if attachment.file_name:
        return attachment.file_name
    if attachment.original_filename:
        return attachment.original_filename
    if attachment.drive_view_url:
        return "Attachment"
    return ""


def attachment_preview_source(attachment):
    if not attachment:
        return ""
    source_name = (
        str(attachment.display_filename or "").lower()
        or str(attachment.file_name or "").lower()
        or str(attachment.original_filename or "").lower()
    )
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


def attachment_preview_kind(attachment):
    if not attachment:
        return "unsupported"
    mime_type = str(getattr(attachment, "drive_mime_type", "") or "").lower().strip()
    if mime_type == "application/pdf":
        return "pdf"
    if mime_type.startswith("image/"):
        return "image"
    source_name = attachment_preview_source(attachment)
    if source_name.endswith(".pdf"):
        return "pdf"
    if source_name.endswith((".png", ".jpg", ".jpeg", ".webp", ".gif")):
        return "image"
    return "unsupported"


def attachment_preview_payload(attachment):
    if not attachment:
        return None
    preview_url = reverse("ui:application-attachment-download", kwargs={"attachment_id": attachment.id})
    source_name = attachment_preview_source(attachment)
    return {
        "id": attachment.id,
        "title": attachment_preview_title(attachment),
        "preview_url": preview_url,
        "download_url": f"{preview_url}?download=1",
        "source": source_name,
        "preview_kind": attachment_preview_kind(attachment),
    }


def attachment_items_b64(items):
    payload = json.dumps(items, ensure_ascii=False)
    return base64.b64encode(payload.encode("utf-8")).decode("ascii")
