from __future__ import annotations

from typing import Optional

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from . import models


def next_fund_request_number() -> str:
    prefix = "FR"
    today = timezone.now().strftime("%Y%m%d")
    prefix_like = f"{prefix}{today}-"
    latest = (
        models.FundRequest.objects.filter(fund_request_number__startswith=prefix_like)
        .order_by("-fund_request_number")
        .values_list("fund_request_number", flat=True)
        .first()
    )
    if not latest:
        return f"{prefix_like}0001"
    try:
        seq = int(str(latest).split("-")[-1]) + 1
    except (ValueError, TypeError):
        seq = 1
    return f"{prefix_like}{seq:04d}"


def next_purchase_order_number() -> str:
    """
    Serial PO number format: MASM/MNP0001
    """
    prefix = "MASM/MNP"
    latest = models.FundRequest.objects.exclude(purchase_order_number__isnull=True).exclude(
        purchase_order_number=""
    ).order_by("-created_at").first()
    if not latest or not latest.purchase_order_number:
        return f"{prefix}0001"
    try:
        numeric = int(str(latest.purchase_order_number).replace(prefix, "", 1))
        return f"{prefix}{numeric + 1:04d}"
    except (TypeError, ValueError):
        return f"{prefix}0001"


def next_public_application_number() -> str:
    prefix = "P"
    latest = (
        models.PublicBeneficiaryEntry.objects.filter(application_number__startswith=prefix)
        .order_by("-application_number")
        .values_list("application_number", flat=True)
        .first()
    )
    if not latest:
        return f"{prefix}001"
    try:
        seq = int(str(latest).replace(prefix, "", 1)) + 1
    except (TypeError, ValueError):
        seq = 1
    return f"{prefix}{seq:03d}"


def next_institution_application_number() -> str:
    prefix = "I"
    latest = (
        models.InstitutionsBeneficiaryEntry.objects.filter(application_number__startswith=prefix)
        .order_by("-application_number")
        .values_list("application_number", flat=True)
        .first()
    )
    if not latest:
        return f"{prefix}001"
    try:
        seq = int(str(latest).replace(prefix, "", 1)) + 1
    except (TypeError, ValueError):
        seq = 1
    return f"{prefix}{seq:03d}"


def sync_fund_request_totals(fund_request: models.FundRequest) -> None:
    with transaction.atomic():
        total_value = models.FundRequestArticle.objects.filter(fund_request=fund_request).aggregate(
            total=Sum("value")
        ).get("total") or 0
        fund_request.total_amount = total_value
        fund_request.save(update_fields=["total_amount"])


def log_audit(
    *,
    user: Optional[models.AppUser],
    action_type: str,
    entity_type: str,
    entity_id: str | None,
    details: dict,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> None:
    models.AuditLog.objects.create(
        user=user,
        action_type=action_type,
        entity_type=entity_type,
        entity_id=entity_id,
        details=details,
        ip_address=ip_address,
        user_agent=user_agent,
    )


def mark_fund_request_status(
    fund_request: models.FundRequest,
    status: models.FundRequestStatusChoices,
    actor: Optional[models.AppUser] = None,
) -> models.FundRequest:
    prev = fund_request.status
    fund_request.status = status
    if status in {models.FundRequestStatusChoices.SUBMITTED, models.FundRequestStatusChoices.APPROVED, models.FundRequestStatusChoices.REJECTED}:
        sync_fund_request_totals(fund_request)
    fund_request.save(update_fields=["status"])
    log_audit(
        user=actor,
        action_type=models.ActionTypeChoices.STATUS_CHANGE,
        entity_type="fund_request",
        entity_id=str(fund_request.id),
        details={"from": prev, "to": status},
    )
    return fund_request
