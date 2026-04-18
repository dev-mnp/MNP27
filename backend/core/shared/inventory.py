from __future__ import annotations

"""Shared inventory aggregation helpers reused by multiple modules."""

from decimal import Decimal

from django.utils import timezone

from core import models


def _split_order_article_names(article: models.Article | None) -> tuple[list[str], bool]:
    if not article or not article.article_name:
        return [], False
    raw_name = article.article_name.strip()
    if not raw_name:
        return [], False
    has_plus = "+" in raw_name
    if has_plus:
        parts = [part.strip() for part in raw_name.split("+") if part.strip()]
    else:
        parts = [raw_name]
    return parts, bool(article.combo or has_plus)


def _ensure_order_summary_row(rows_map, order_name: str, article: models.Article | None, combo_related: bool):
    key = order_name.casefold()
    if key not in rows_map:
        rows_map[key] = {
            "row_key": key,
            "article_name": order_name,
            "item_type": article.item_type if article else "",
            "category": article.category if article else "",
            "master_category": article.master_category if article else "",
            "combo_related": combo_related,
            "total_quantity": 0,
            "quantity_ordered": 0,
            "quantity_received": 0,
            "quantity_pending": 0,
            "total_value": Decimal("0"),
            "breakdown": {"district": 0, "public": 0, "institutions": 0},
            "source_items": set(),
            "beneficiaries": [],
            "statuses": set(),
        }
    row = rows_map[key]
    if article:
        row["item_type"] = row["item_type"] or article.item_type
        row["category"] = row["category"] or (article.category or "")
        row["master_category"] = row["master_category"] or (article.master_category or "")
    row["combo_related"] = row["combo_related"] or combo_related
    return row


def build_order_management_rows():
    rows_map = {}

    district_entries = (
        models.DistrictBeneficiaryEntry.objects.select_related("district", "article")
        .order_by("application_number", "district__district_name", "created_at")
    )
    for entry in district_entries:
        parts, combo_related = _split_order_article_names(entry.article)
        if not parts:
            continue
        split_count = Decimal(len(parts))
        value_share = (entry.total_amount or Decimal("0")) / split_count if split_count else Decimal("0")
        for part in parts:
            row = _ensure_order_summary_row(rows_map, part, entry.article, combo_related)
            row["total_quantity"] += entry.quantity
            row["total_value"] += value_share
            row["breakdown"]["district"] += entry.quantity
            row["source_items"].add(entry.article.article_name)
            row["statuses"].add(entry.status)
            row["beneficiaries"].append(
                {
                    "beneficiary_type": "District",
                    "application_number": entry.application_number or "",
                    "beneficiary_name": entry.district.district_name,
                    "quantity": entry.quantity,
                    "source_item": entry.article.article_name,
                    "notes": entry.notes or "",
                    "status": entry.status,
                    "item_type": entry.article.item_type,
                    "linked_fund_request_status": getattr(entry.fund_request, "status", "") if entry.fund_request_id else "",
                    "created_at": entry.created_at,
                }
            )

    public_entries = (
        models.PublicBeneficiaryEntry.objects.active().select_related("article")
        .order_by("application_number", "name", "created_at")
    )
    for entry in public_entries:
        parts, combo_related = _split_order_article_names(entry.article)
        if not parts:
            continue
        split_count = Decimal(len(parts))
        value_share = (entry.total_amount or Decimal("0")) / split_count if split_count else Decimal("0")
        for part in parts:
            row = _ensure_order_summary_row(rows_map, part, entry.article, combo_related)
            row["total_quantity"] += entry.quantity
            row["total_value"] += value_share
            row["breakdown"]["public"] += entry.quantity
            row["source_items"].add(entry.article.article_name)
            row["statuses"].add(entry.status)
            row["beneficiaries"].append(
                {
                    "beneficiary_type": "Public",
                    "application_number": entry.application_number or "",
                    "beneficiary_name": entry.name,
                    "quantity": entry.quantity,
                    "source_item": entry.article.article_name,
                    "notes": entry.notes or "",
                    "status": entry.status,
                    "item_type": entry.article.item_type,
                    "linked_fund_request_status": getattr(entry.fund_request, "status", "") if entry.fund_request_id else "",
                    "created_at": entry.created_at,
                }
            )

    institution_entries = (
        models.InstitutionsBeneficiaryEntry.objects.select_related("article")
        .order_by("application_number", "institution_name", "created_at")
    )
    for entry in institution_entries:
        parts, combo_related = _split_order_article_names(entry.article)
        if not parts:
            continue
        split_count = Decimal(len(parts))
        value_share = (entry.total_amount or Decimal("0")) / split_count if split_count else Decimal("0")
        for part in parts:
            row = _ensure_order_summary_row(rows_map, part, entry.article, combo_related)
            row["total_quantity"] += entry.quantity
            row["total_value"] += value_share
            row["breakdown"]["institutions"] += entry.quantity
            row["source_items"].add(entry.article.article_name)
            row["statuses"].add(entry.status)
            row["beneficiaries"].append(
                {
                    "beneficiary_type": "Institutions",
                    "application_number": entry.application_number or "",
                    "beneficiary_name": entry.institution_name,
                    "quantity": entry.quantity,
                    "source_item": entry.article.article_name,
                    "notes": entry.notes or "",
                    "status": entry.status,
                    "item_type": entry.article.item_type,
                    "linked_fund_request_status": getattr(entry.fund_request, "status", "") if entry.fund_request_id else "",
                    "created_at": entry.created_at,
                }
            )

    order_entries = (
        models.OrderEntry.objects.select_related("article")
        .exclude(status=models.OrderStatusChoices.CANCELLED)
        .order_by("article__article_name", "order_date", "created_at")
    )
    for entry in order_entries:
        parts, combo_related = _split_order_article_names(entry.article)
        if not parts:
            continue
        for part in parts:
            row = _ensure_order_summary_row(rows_map, part, entry.article, combo_related)
            if entry.status in {models.OrderStatusChoices.ORDERED, models.OrderStatusChoices.RECEIVED}:
                row["quantity_ordered"] += entry.quantity_ordered
            if entry.status == models.OrderStatusChoices.RECEIVED:
                row["quantity_received"] += entry.quantity_ordered

    rows = []
    for index, row in enumerate(sorted(rows_map.values(), key=lambda item: item["article_name"].casefold()), start=1):
        if models.BeneficiaryStatusChoices.SUBMITTED in row["statuses"]:
            row["source_status"] = models.BeneficiaryStatusChoices.SUBMITTED
        elif models.BeneficiaryStatusChoices.DRAFT in row["statuses"]:
            row["source_status"] = models.BeneficiaryStatusChoices.DRAFT
        else:
            row["source_status"] = ""
        quantity_gap = row["total_quantity"] - row["quantity_ordered"]
        row["quantity_pending"] = quantity_gap if quantity_gap > 0 else 0
        row["quantity_excess"] = abs(quantity_gap) if quantity_gap < 0 else 0
        row["source_items_display"] = ", ".join(sorted(row["source_items"]))
        row["beneficiaries"] = sorted(
            row["beneficiaries"],
            key=lambda item: (
                item["beneficiary_type"],
                item.get("created_at") or timezone.now(),
                item["application_number"],
                item["beneficiary_name"].casefold(),
                item["source_item"].casefold(),
            ),
        )
        allocation_status_priority = {
            models.BeneficiaryStatusChoices.SUBMITTED: 0,
            models.BeneficiaryStatusChoices.DRAFT: 1,
        }
        beneficiaries_for_allocation = sorted(
            row["beneficiaries"],
            key=lambda item: (
                allocation_status_priority.get(item.get("application_status") or item.get("status") or "", 99),
                item["beneficiary_type"],
                item.get("created_at") or timezone.now(),
                item["application_number"],
                item["beneficiary_name"].casefold(),
                item["source_item"].casefold(),
            ),
        )
        remaining_ordered = int(row["quantity_ordered"] or 0)
        for item in beneficiaries_for_allocation:
            quantity = int(item.get("quantity") or 0)
            source_status = item.get("status") or ""
            item["application_status"] = source_status or ""
            if item.get("item_type") == models.ItemTypeChoices.AID:
                linked_status = item.get("linked_fund_request_status") or ""
                item["ordered_quantity"] = quantity if linked_status == models.FundRequestStatusChoices.SUBMITTED else 0
                item["order_status"] = "Fund Raised" if item["ordered_quantity"] >= quantity and quantity > 0 else "No"
                continue
            if remaining_ordered <= 0:
                item["ordered_quantity"] = 0
                item["order_status"] = "No"
                continue
            if remaining_ordered >= quantity:
                item["ordered_quantity"] = quantity
                item["order_status"] = "Fund Raised"
                remaining_ordered -= quantity
            else:
                item["ordered_quantity"] = remaining_ordered
                item["order_status"] = "Partial"
                remaining_ordered = 0
        row["order_statuses"] = {item.get("order_status") or "" for item in row["beneficiaries"]}
        row["beneficiary_names_display"] = ", ".join(
            f'{item["beneficiary_type"]}: {item["beneficiary_name"]}' for item in row["beneficiaries"]
        )
        row["row_id"] = f"order-row-{index}"
        rows.append(row)
    return rows
