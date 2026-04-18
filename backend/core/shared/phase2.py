"""Shared phase-2 helper functions reused across seat, sequence, token, and reports."""

from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from core import models
from core.application_entry.views import (
    _build_district_entry_summaries,
    _build_institution_entry_summaries,
    _district_export_rows,
    _institution_export_rows,
    _public_export_rows,
)
from core.shared.csv_utils import _tabular_rows_from_upload

PHASE2_MASTER_REQUIRED_HEADERS = [
    "Application Number",
    "Beneficiary Name",
    "Requested Item",
    "Quantity",
    "Beneficiary Type",
    "Item Type",
]

def _phase2_parse_number(value):
    raw = str(value or "").replace(",", "").strip()
    try:
        number = int(Decimal(raw or "0"))
    except (InvalidOperation, ValueError):
        return 0
    return max(number, 0)

def _phase2_normalize_text(value):
    return " ".join(str(value or "").strip().lower().split())

def _phase2_active_or_latest_session():
    return (
        models.EventSession.objects.order_by("-is_active", "-event_year", "session_name", "-id").first()
    )

def _phase2_get_or_create_default_session():
    session = _phase2_active_or_latest_session()
    if session:
        return session
    year = timezone.localdate().year
    return models.EventSession.objects.create(
        session_name=f"{year} Event",
        event_year=year,
        is_active=True,
    )

def _phase2_selected_session(request):
    session_id = (request.GET.get("session") or request.POST.get("session") or "").strip()
    if session_id:
        try:
            return models.EventSession.objects.get(pk=session_id)
        except (ValueError, models.EventSession.DoesNotExist):
            return _phase2_active_or_latest_session()
    return _phase2_active_or_latest_session()

def _phase2_session_querystring(request, session):
    params = request.GET.copy()
    params["session"] = str(session.pk)
    return params.urlencode()

def _phase2_redirect_url(request, view_name, session=None, *, filter_keys=None):
    params = request.GET.copy()
    if filter_keys is not None:
        filtered = params.__class__(mutable=True)
        for key in filter_keys:
            if key in params:
                values = params.getlist(key)
                if values:
                    filtered.setlist(key, values)
        params = filtered
    if session:
        params["session"] = str(session.pk)
    elif "session" in params:
        del params["session"]
    query = params.urlencode()
    base_url = reverse(view_name)
    return f"{base_url}?{query}" if query else base_url

def _phase2_url_with_extra_params(request, view_name, session=None, *, filter_keys=None, extra_params=None):
    params = request.GET.copy()
    if filter_keys is not None:
        filtered = params.__class__(mutable=True)
        for key in filter_keys:
            if key in params:
                values = params.getlist(key)
                if values:
                    filtered.setlist(key, values)
        params = filtered
    if session:
        params["session"] = str(session.pk)
    if extra_params:
        for key, value in extra_params.items():
            if value in (None, ""):
                params.pop(key, None)
            else:
                params[key] = value
    query = params.urlencode()
    base_url = reverse(view_name)
    return f"{base_url}?{query}" if query else base_url

def _phase2_distinct_beneficiary_key(application_number, beneficiary_name, beneficiary_type):
    return (
        _phase2_normalize_text(beneficiary_type),
        str(application_number or "").strip(),
        str(beneficiary_name or "").strip(),
    )

def _phase2_reconciliation_snapshot(*, source_rows, grouped_rows, total_value_getter):
    source_unique_items = set()
    grouped_unique_items = set()
    source_beneficiaries = {}
    grouped_beneficiaries = {}
    source_quantity_total = 0
    grouped_quantity_total = 0
    source_value_total = 0
    grouped_value_total = 0

    for row in source_rows:
        beneficiary_type = str(row.get("Beneficiary Type") or "").strip()
        application_number = str(row.get("Application Number") or "").strip()
        beneficiary_name = str(row.get("Beneficiary Name") or "").strip()
        requested_item = str(row.get("Requested Item") or "").strip()
        quantity = _phase2_parse_number(row.get("Quantity"))
        source_quantity_total += quantity
        source_value_total += total_value_getter(row)
        if requested_item:
            source_unique_items.add(requested_item)
        if beneficiary_type or application_number or beneficiary_name:
            source_beneficiaries.setdefault(beneficiary_type or "Unknown", set()).add(
                _phase2_distinct_beneficiary_key(application_number, beneficiary_name, beneficiary_type)
            )

    for row in grouped_rows:
        beneficiary_type = str(row.get("beneficiary_type") or "").strip()
        application_number = str(row.get("application_number") or "").strip()
        beneficiary_name = str(row.get("beneficiary_name") or "").strip()
        requested_item = str(row.get("requested_item") or "").strip()
        quantity = int(row.get("quantity") or 0)
        grouped_quantity_total += quantity
        grouped_value_total += total_value_getter(row)
        if requested_item:
            grouped_unique_items.add(requested_item)
        if beneficiary_type or application_number or beneficiary_name:
            grouped_beneficiaries.setdefault(beneficiary_type or "Unknown", set()).add(
                _phase2_distinct_beneficiary_key(application_number, beneficiary_name, beneficiary_type)
            )

    beneficiary_labels = [
        models.RecipientTypeChoices.DISTRICT,
        models.RecipientTypeChoices.PUBLIC,
        models.RecipientTypeChoices.INSTITUTIONS,
        models.RecipientTypeChoices.OTHERS,
    ]
    beneficiary_metrics = []
    for label in beneficiary_labels:
        source_count = len(source_beneficiaries.get(label, set()))
        grouped_count = len(grouped_beneficiaries.get(label, set()))
        if source_count or grouped_count:
            beneficiary_metrics.append(
                {
                    "label": f"{label} Beneficiaries",
                    "source": source_count,
                    "grouped": grouped_count,
                }
            )

    return {
        "source_row_count": len(source_rows),
        "grouped_row_count": len(grouped_rows),
        "source_quantity_total": source_quantity_total,
        "grouped_quantity_total": grouped_quantity_total,
        "source_total_value": source_value_total,
        "grouped_total_value": grouped_value_total,
        "source_unique_items": len(source_unique_items),
        "grouped_unique_items": len(grouped_unique_items),
        "beneficiary_metrics": beneficiary_metrics,
    }

def _phase2_reconciliation_checks(reconciliation_snapshot):
    if not reconciliation_snapshot:
        return []
    checks = [
        {
            "label": "Quantity",
            "matched": reconciliation_snapshot.get("source_quantity_total", 0) == reconciliation_snapshot.get("grouped_quantity_total", 0),
            "source": reconciliation_snapshot.get("source_quantity_total", 0),
            "grouped": reconciliation_snapshot.get("grouped_quantity_total", 0),
        },
        {
            "label": "Total Value",
            "matched": reconciliation_snapshot.get("source_total_value", 0) == reconciliation_snapshot.get("grouped_total_value", 0),
            "source": reconciliation_snapshot.get("source_total_value", 0),
            "grouped": reconciliation_snapshot.get("grouped_total_value", 0),
        },
        {
            "label": "Unique Items",
            "matched": reconciliation_snapshot.get("source_unique_items", 0) == reconciliation_snapshot.get("grouped_unique_items", 0),
            "source": reconciliation_snapshot.get("source_unique_items", 0),
            "grouped": reconciliation_snapshot.get("grouped_unique_items", 0),
        },
    ]
    for metric in reconciliation_snapshot.get("beneficiary_metrics") or []:
        checks.append(
            {
                "label": metric.get("label") or "Beneficiaries",
                "matched": metric.get("source", 0) == metric.get("grouped", 0),
                "source": metric.get("source", 0),
                "grouped": metric.get("grouped", 0),
            }
        )
    return checks

def _phase2_split_reconciliation(rows, pending_waiting_by_id=None):
    pending_waiting_by_id = pending_waiting_by_id or {}
    total_quantity = 0
    total_waiting = 0
    total_token = 0
    row_mismatch_count = 0
    row_count = 0

    for row in rows:
        row_count += 1
        quantity = int(row.quantity or 0)
        total_quantity += quantity
        if str(row.id) in pending_waiting_by_id:
            waiting = pending_waiting_by_id[str(row.id)]
            waiting = max(min(int(waiting or 0), quantity), 0)
            token = max(quantity - waiting, 0)
        else:
            waiting = int(row.waiting_hall_quantity or 0)
            token = int(row.token_quantity or 0)
        total_waiting += waiting
        total_token += token
        if waiting + token != quantity:
            row_mismatch_count += 1

    return {
        "row_count": row_count,
        "row_mismatch_count": row_mismatch_count,
        "rowwise_matched": row_mismatch_count == 0,
        "total_quantity": total_quantity,
        "total_waiting": total_waiting,
        "total_token": total_token,
        "overall_matched": (total_waiting + total_token) == total_quantity,
    }

def _phase2_group_key(application_number, beneficiary_name, district, requested_item):
    return (
        str(application_number or "").strip(),
        str(beneficiary_name or "").strip(),
        str(district or "").strip(),
        str(requested_item or "").strip(),
    )

def _phase2_row_identity_key(data):
    if hasattr(data, "master_row"):
        master_row = getattr(data, "master_row", None) or {}
        master_headers = getattr(data, "master_headers", None) or []
    else:
        master_row = (data.get("master_row") or {}) if isinstance(data, dict) else {}
        master_headers = (data.get("master_headers") or []) if isinstance(data, dict) else []

    if master_row:
        headers = list(master_headers) if master_headers else list(master_row.keys())
        filtered_headers = [
            header
            for header in headers
            if _phase2_normalize_text(header) not in {"waiting hall quantity", "token quantity", "sequence no", "sequence list"}
        ]
        return (
            "master_row",
            tuple(
                (header, str(master_row.get(header, "") or "").strip())
                for header in filtered_headers
            ),
        )

    if hasattr(data, "application_number"):
        application_number = getattr(data, "application_number", "")
        beneficiary_name = getattr(data, "beneficiary_name", "")
        district = getattr(data, "district", "")
        requested_item = getattr(data, "requested_item", "")
        quantity = getattr(data, "quantity", 0)
        beneficiary_type = getattr(data, "beneficiary_type", "")
        item_type = getattr(data, "item_type", "")
        comments = getattr(data, "comments", "")
    else:
        application_number = data.get("application_number", "") if isinstance(data, dict) else ""
        beneficiary_name = data.get("beneficiary_name", "") if isinstance(data, dict) else ""
        district = data.get("district", "") if isinstance(data, dict) else ""
        requested_item = data.get("requested_item", "") if isinstance(data, dict) else ""
        quantity = data.get("quantity", 0) if isinstance(data, dict) else 0
        beneficiary_type = data.get("beneficiary_type", "") if isinstance(data, dict) else ""
        item_type = data.get("item_type", "") if isinstance(data, dict) else ""
        comments = data.get("comments", "") if isinstance(data, dict) else ""

    return (
        "fallback",
        str(application_number or "").strip(),
        str(beneficiary_name or "").strip(),
        str(district or "").strip(),
        str(requested_item or "").strip(),
        int(quantity or 0),
        str(beneficiary_type or "").strip(),
        str(item_type or "").strip(),
        str(comments or "").strip(),
    )

def _phase2_row_identity_candidates(data):
    primary = _phase2_row_identity_key(data)
    candidates = [primary]

    if hasattr(data, "application_number"):
        application_number = getattr(data, "application_number", "")
        beneficiary_name = getattr(data, "beneficiary_name", "")
        district = getattr(data, "district", "")
        requested_item = getattr(data, "requested_item", "")
        quantity = getattr(data, "quantity", 0)
        beneficiary_type = getattr(data, "beneficiary_type", "")
        item_type = getattr(data, "item_type", "")
        comments = getattr(data, "comments", "")
    else:
        application_number = data.get("application_number", "") if isinstance(data, dict) else ""
        beneficiary_name = data.get("beneficiary_name", "") if isinstance(data, dict) else ""
        district = data.get("district", "") if isinstance(data, dict) else ""
        requested_item = data.get("requested_item", "") if isinstance(data, dict) else ""
        quantity = data.get("quantity", 0) if isinstance(data, dict) else 0
        beneficiary_type = data.get("beneficiary_type", "") if isinstance(data, dict) else ""
        item_type = data.get("item_type", "") if isinstance(data, dict) else ""
        comments = data.get("comments", "") if isinstance(data, dict) else ""

    fallback = (
        "fallback",
        str(application_number or "").strip(),
        str(beneficiary_name or "").strip(),
        str(district or "").strip(),
        str(requested_item or "").strip(),
        int(quantity or 0),
        str(beneficiary_type or "").strip(),
        str(item_type or "").strip(),
        str(comments or "").strip(),
    )
    structural = (
        "structural",
        str(application_number or "").strip(),
        str(beneficiary_name or "").strip(),
        str(district or "").strip(),
        str(requested_item or "").strip(),
    )
    if structural not in candidates:
        candidates.append(structural)
    if fallback not in candidates:
        candidates.append(fallback)
    return candidates

def _phase2_preview_row_from_upload(row):
    return {
        "beneficiary_type": str(row.get("beneficiary_type") or "").strip(),
        "application_number": str(row.get("application_number") or "").strip(),
        "beneficiary_name": str(row.get("beneficiary_name") or "").strip(),
        "requested_item": str(row.get("requested_item") or "").strip(),
    }

def _phase2_preview_row_from_existing(row):
    return {
        "beneficiary_type": str(row.beneficiary_type or "").strip(),
        "application_number": str(row.application_number or "").strip(),
        "beneficiary_name": str(row.beneficiary_name or "").strip(),
        "requested_item": str(row.requested_item or "").strip(),
    }

def _phase2_preserve_existing_split_state(session, upload_rows):
    existing_rows = list(models.SeatAllocationRow.objects.filter(session=session))
    existing_map = {}
    for row in existing_rows:
        for key in _phase2_row_identity_candidates(row):
            existing_map.setdefault(key, []).append(row)
    preserved_count = 0
    matched_existing_ids = set()
    matched_count = 0

    for row in upload_rows:
        existing = None
        for key in _phase2_row_identity_candidates(row):
            existing_candidates = existing_map.get(key) or []
            while existing_candidates and str(existing_candidates[0].id) in matched_existing_ids:
                existing_candidates.pop(0)
            if existing_candidates:
                existing = existing_candidates.pop(0)
                break
        if not existing:
            continue
        matched_existing_ids.add(str(existing.id))
        quantity = int(row.get("quantity") or 0)
        preserved_waiting = min(int(existing.waiting_hall_quantity or 0), quantity)
        row["waiting_hall_quantity"] = preserved_waiting
        row["token_quantity"] = max(quantity - preserved_waiting, 0)
        row["sequence_no"] = existing.sequence_no
        preserved_count += 1
        matched_count += 1

    removed_count = max(len(existing_rows) - len(matched_existing_ids), 0)
    new_count = max(len(upload_rows) - matched_count, 0)
    return {
        "rows": upload_rows,
        "preserved_count": preserved_count,
        "new_count": new_count,
        "removed_count": removed_count,
    }

def _phase2_preview_sync_state(session, upload_rows):
    existing_rows = list(models.SeatAllocationRow.objects.filter(session=session))
    existing_map = {}
    for row in existing_rows:
        for key in _phase2_row_identity_candidates(row):
            existing_map.setdefault(key, []).append(row)

    preserved_count = 0
    added_rows = []
    matched_existing_ids = set()
    for row in upload_rows:
        matched = False
        for key in _phase2_row_identity_candidates(row):
            existing_candidates = existing_map.get(key) or []
            while existing_candidates and str(existing_candidates[0].id) in matched_existing_ids:
                existing_candidates.pop(0)
            if existing_candidates:
                matched_existing_ids.add(str(existing_candidates.pop(0).id))
                matched = True
                break
        if matched:
            preserved_count += 1
            continue
        if len(added_rows) < 8:
            added_rows.append(_phase2_preview_row_from_upload(row))

    removed_rows = []
    unmatched_existing = [row for row in existing_rows if str(row.id) not in matched_existing_ids]
    removed_count = len(unmatched_existing)
    for row in unmatched_existing[:8]:
        removed_rows.append(_phase2_preview_row_from_existing(row))

    new_count = max(len(upload_rows) - preserved_count, 0)
    return {
        "preserved_count": preserved_count,
        "new_count": new_count,
        "removed_count": removed_count,
        "added_rows": added_rows,
        "removed_rows": removed_rows,
    }

def _phase2_master_change_state(session, upload_rows):
    existing_rows = list(models.SeatAllocationRow.objects.filter(session=session))
    existing_map = {}
    for row in existing_rows:
        for key in _phase2_row_identity_candidates(row):
            existing_map.setdefault(key, []).append(row)

    new_count = 0
    removed_count = 0
    updated_count = 0
    updated_rows = []
    matched_existing_ids = set()

    field_labels = {
        "Application Number": "Application Number",
        "Beneficiary Name": "Beneficiary Name",
        "Requested Item": "Requested Item",
        "Quantity": "Quantity",
        "Cost Per Unit": "Cost Per Unit",
        "Total Value": "Total Value",
        "Beneficiary Type": "Beneficiary Type",
        "Item Type": "Item Type",
        "Comments": "Comments",
        "Aadhar Number": "Aadhaar Number",
        "Name of Beneficiary": "Name of Beneficiary",
        "Name of Institution": "Name of Institution",
        "Cheque / RTGS in Favour": "Cheque / RTGS in Favour",
    }

    for incoming in upload_rows:
        matched = False
        matched_row = None
        for key in _phase2_row_identity_candidates(incoming):
            existing_candidates = existing_map.get(key) or []
            while existing_candidates and str(existing_candidates[0].id) in matched_existing_ids:
                existing_candidates.pop(0)
            if existing_candidates:
                matched_row = existing_candidates.pop(0)
                matched_existing_ids.add(str(matched_row.id))
                matched = True
                break
        if matched:
            incoming_master = incoming.get("master_row") or {}
            existing_master = matched_row.master_row or {}
            changes = []
            for header, label in field_labels.items():
                incoming_value = str(incoming_master.get(header, "") or "").strip()
                existing_value = str(existing_master.get(header, "") or "").strip()
                if incoming_value != existing_value:
                    changes.append(
                        f"{label} {existing_value or '-'} -> {incoming_value or '-'}"
                    )
            if changes:
                updated_count += 1
                if len(updated_rows) < 8:
                    updated_rows.append(
                        {
                            "beneficiary_type": str(incoming.get("beneficiary_type") or "").strip(),
                            "application_number": str(incoming.get("application_number") or "").strip(),
                            "beneficiary_name": str(incoming.get("beneficiary_name") or "").strip(),
                            "requested_item": str(incoming.get("requested_item") or "").strip(),
                            "changes": changes[:3],
                        }
                    )
            continue
        new_count += 1
        if len(updated_rows) < 8:
            updated_rows.append(
                {
                    "beneficiary_type": str(incoming.get("beneficiary_type") or "").strip(),
                    "application_number": str(incoming.get("application_number") or "").strip(),
                    "beneficiary_name": str(incoming.get("beneficiary_name") or "").strip(),
                    "requested_item": str(incoming.get("requested_item") or "").strip(),
                    "changes": ["New or changed row"],
                }
            )

    removed_count = max(len(existing_rows) - len(matched_existing_ids), 0)

    return {
        "has_changes": bool(new_count or removed_count or updated_count),
        "new_count": new_count,
        "removed_count": removed_count,
        "updated_count": updated_count,
        "updated_rows": updated_rows,
    }

def _phase2_export_rows(rows, *, include_sequence=False):
    rows = list(rows)
    if not rows:
        return [], []

    base_headers = []
    for row in rows:
        if row.master_headers:
            base_headers = list(row.master_headers)
            break
    if not base_headers:
        base_headers = [
            "Application Number",
            "Beneficiary Name",
            "Requested Item",
            "Quantity",
            "Beneficiary Type",
            "Item Type",
            "Comments",
        ]

    filtered_headers = [
        header for header in base_headers
        if _phase2_normalize_text(header) not in {"waiting hall quantity", "token quantity", "sequence no"}
    ]
    export_headers = [*filtered_headers, "Waiting Hall Quantity", "Token Quantity"]
    if include_sequence:
        export_headers.append("Sequence No")
    export_rows = []
    for row in rows:
        export_row = {}
        for header in filtered_headers:
            export_row[header] = (row.master_row or {}).get(header, "")
        export_row["Waiting Hall Quantity"] = row.waiting_hall_quantity
        export_row["Token Quantity"] = row.token_quantity
        if include_sequence:
            export_row["Sequence No"] = row.sequence_no or ""
        export_rows.append(export_row)
    return export_rows, export_headers

def _phase2_unique_headers(headers):
    unique_headers = []
    seen = set()
    for header in list(headers or []):
        key = str(header or "")
        if key in seen:
            continue
        seen.add(key)
        unique_headers.append(key)
    return unique_headers

def _phase2_build_rows_from_master_export_rows(rows, *, source_file_name):
    headers = list(rows[0].keys()) if rows else []
    order = 0
    source_rows_for_reconciliation = []
    raw_rows = []
    for source_row in rows:
        application_number = str(source_row.get("Application Number") or "").strip()
        beneficiary_name = str(source_row.get("Beneficiary Name") or "").strip()
        requested_item = str(source_row.get("Requested Item") or "").strip()
        beneficiary_type = str(source_row.get("Beneficiary Type") or "").strip()
        item_type = str(source_row.get("Item Type") or "").strip()
        comments = str(source_row.get("Comments") or "").strip()
        quantity = _phase2_parse_number(source_row.get("Quantity"))
        if not (application_number or beneficiary_name or requested_item or quantity):
            continue
        source_rows_for_reconciliation.append(source_row)
        district = beneficiary_name if _phase2_normalize_text(beneficiary_type) == "district" else "Non-District"
        master_row = {header: source_row.get(header, "") for header in headers}
        order += 1
        raw_rows.append(
            {
                "source_file_name": source_file_name,
                "application_number": application_number,
                "beneficiary_name": beneficiary_name,
                "district": district,
                "requested_item": requested_item,
                "quantity": quantity,
                "waiting_hall_quantity": 0,
                "token_quantity": quantity,
                "beneficiary_type": beneficiary_type,
                "item_type": item_type,
                "comments": comments,
                "master_row": master_row,
                "master_headers": headers,
                "sort_order": order,
            }
        )
    reconciliation_snapshot = _phase2_reconciliation_snapshot(
        source_rows=source_rows_for_reconciliation,
        grouped_rows=raw_rows,
        total_value_getter=lambda row: _phase2_parse_number(
            row.get("Total Value")
            if isinstance(row, dict) and "Total Value" in row
            else (row.get("master_row") or {}).get("Total Value")
        ),
    )
    return {
        "rows": raw_rows,
        "headers": headers,
        **reconciliation_snapshot,
        "reconciliation_snapshot": reconciliation_snapshot,
    }

def _phase2_master_export_rows():
    district_rows = _district_export_rows(_build_district_entry_summaries())
    public_rows = _public_export_rows(models.PublicBeneficiaryEntry.objects.active().select_related("article").all())
    institution_rows = _institution_export_rows(_build_institution_entry_summaries())
    return district_rows + public_rows + institution_rows

def _phase2_replace_session_rows(session, upload_rows, *, source_file_name, user, reconciliation=None):
    with transaction.atomic():
        models.SeatAllocationRow.objects.filter(session=session).delete()
        for row in upload_rows:
            models.SeatAllocationRow.objects.create(
                session=session,
                source_file_name=source_file_name,
                application_number=row["application_number"],
                beneficiary_name=row["beneficiary_name"],
                district=row["district"],
                requested_item=row["requested_item"],
                quantity=row["quantity"],
                waiting_hall_quantity=row["waiting_hall_quantity"],
                token_quantity=row["token_quantity"],
                beneficiary_type=row["beneficiary_type"],
                item_type=row["item_type"],
                comments=row["comments"],
                master_row=row["master_row"],
                master_headers=row["master_headers"],
                sort_order=row["sort_order"],
                sequence_no=row.get("sequence_no"),
                created_by=user,
                updated_by=user,
            )
        if reconciliation is None:
            reconciliation = {}
        session.phase2_source_name = source_file_name
        session.phase2_source_row_count = int(reconciliation.get("source_row_count") or len(upload_rows))
        session.phase2_grouped_row_count = int(reconciliation.get("grouped_row_count") or len(upload_rows))
        session.phase2_source_quantity_total = int(
            reconciliation.get("source_quantity_total")
            if reconciliation.get("source_quantity_total") is not None
            else sum(int(row.get("quantity") or 0) for row in upload_rows)
        )
        session.phase2_grouped_quantity_total = int(
            reconciliation.get("grouped_quantity_total")
            if reconciliation.get("grouped_quantity_total") is not None
            else sum(int(row.get("quantity") or 0) for row in upload_rows)
        )
        session.phase2_reconciliation_snapshot = reconciliation.get("reconciliation_snapshot") or {}
        session.save(
            update_fields=[
                "phase2_source_name",
                "phase2_source_row_count",
                "phase2_grouped_row_count",
                "phase2_source_quantity_total",
                "phase2_grouped_quantity_total",
                "phase2_reconciliation_snapshot",
                "updated_at",
            ]
        )

def _phase2_build_upload_rows(uploaded_file):
    headers, uploaded_rows = _tabular_rows_from_upload(uploaded_file)
    if not headers:
        raise ValueError("Uploaded file is empty.")

    normalized_headers = {_phase2_normalize_text(header): header for header in headers}
    missing = [header for header in PHASE2_MASTER_REQUIRED_HEADERS if _phase2_normalize_text(header) not in normalized_headers]
    if missing:
        raise ValueError(f"Missing required column(s): {', '.join(missing)}")

    quantity_header = normalized_headers[_phase2_normalize_text("Quantity")]
    application_header = normalized_headers[_phase2_normalize_text("Application Number")]
    beneficiary_header = normalized_headers[_phase2_normalize_text("Beneficiary Name")]
    requested_item_header = normalized_headers[_phase2_normalize_text("Requested Item")]
    beneficiary_type_header = normalized_headers[_phase2_normalize_text("Beneficiary Type")]
    item_type_header = normalized_headers[_phase2_normalize_text("Item Type")]
    comments_header = normalized_headers.get(_phase2_normalize_text("Comments"))
    total_value_header = normalized_headers.get(_phase2_normalize_text("Total Value"))
    waiting_hall_header = normalized_headers.get(_phase2_normalize_text("Waiting Hall Quantity"))
    token_header = normalized_headers.get(_phase2_normalize_text("Token Quantity"))

    order = 0
    source_rows_for_reconciliation = []
    raw_rows = []
    for source_row in uploaded_rows:
        application_number = str(source_row.get(application_header) or "").strip()
        beneficiary_name = str(source_row.get(beneficiary_header) or "").strip()
        requested_item = str(source_row.get(requested_item_header) or "").strip()
        beneficiary_type = str(source_row.get(beneficiary_type_header) or "").strip()
        item_type = str(source_row.get(item_type_header) or "").strip()
        comments = str(source_row.get(comments_header) or "").strip() if comments_header else ""
        quantity = _phase2_parse_number(source_row.get(quantity_header))
        if not (application_number or beneficiary_name or requested_item or quantity):
            continue
        waiting_hall_quantity = _phase2_parse_number(source_row.get(waiting_hall_header)) if waiting_hall_header else None
        token_quantity = _phase2_parse_number(source_row.get(token_header)) if token_header else None
        if waiting_hall_quantity is None and token_quantity is None:
            waiting_hall_quantity = 0
            token_quantity = quantity
        elif waiting_hall_quantity is None:
            token_quantity = max(min(token_quantity, quantity), 0)
            waiting_hall_quantity = max(quantity - token_quantity, 0)
        else:
            waiting_hall_quantity = max(min(waiting_hall_quantity, quantity), 0)
            token_quantity = max(quantity - waiting_hall_quantity, 0)
        normalized_source_row = {header: source_row.get(header, "") for header in headers}
        source_rows_for_reconciliation.append(
            {
                "Application Number": normalized_source_row.get(application_header, ""),
                "Beneficiary Name": normalized_source_row.get(beneficiary_header, ""),
                "Requested Item": normalized_source_row.get(requested_item_header, ""),
                "Quantity": normalized_source_row.get(quantity_header, ""),
                "Beneficiary Type": normalized_source_row.get(beneficiary_type_header, ""),
                "Item Type": normalized_source_row.get(item_type_header, ""),
                "Total Value": normalized_source_row.get(total_value_header, "") if total_value_header else "",
            }
        )

        district = beneficiary_name if _phase2_normalize_text(beneficiary_type) == "district" else "Non-District"
        master_row = normalized_source_row
        order += 1
        raw_rows.append(
            {
                "application_number": application_number,
                "beneficiary_name": beneficiary_name,
                "district": district,
                "requested_item": requested_item,
                "quantity": quantity,
                "waiting_hall_quantity": waiting_hall_quantity,
                "token_quantity": token_quantity,
                "beneficiary_type": beneficiary_type,
                "item_type": item_type,
                "comments": comments,
                "master_row": master_row,
                "master_headers": headers,
                "sort_order": order,
            }
        )
    reconciliation_snapshot = _phase2_reconciliation_snapshot(
        source_rows=source_rows_for_reconciliation,
        grouped_rows=raw_rows,
        total_value_getter=lambda row: _phase2_parse_number(
            row.get("Total Value")
            if isinstance(row, dict) and "Total Value" in row
            else (row.get("master_row") or {}).get(total_value_header, "")
        ),
    )
    return {
        "rows": raw_rows,
        "headers": headers,
        **reconciliation_snapshot,
        "reconciliation_snapshot": reconciliation_snapshot,
    }
