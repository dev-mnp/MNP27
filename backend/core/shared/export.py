"""Shared sequence/export helper functions reused across sequence and reports flows."""

from collections import Counter

from core import models
from core.shared.phase2 import (
    _phase2_export_rows,
    _phase2_master_export_rows,
    _phase2_parse_number,
    _phase2_reconciliation_checks,
    _phase2_reconciliation_snapshot,
    _phase2_split_reconciliation,
)

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

def _sequence_project_rows(rows, headers):
    projected_rows = []
    for row in rows:
        projected_rows.append({header: row.get(header, "") for header in headers})
    return projected_rows

def _sequence_row_key(row, headers):
    return tuple("" if row.get(header) is None else str(row.get(header)) for header in headers)

def _sequence_row_label(row):
    return " / ".join(
        [
            str(row.get("Application Number") or "-").strip() or "-",
            str(row.get("Beneficiary Name") or "-").strip() or "-",
            str(row.get("Requested Item") or "-").strip() or "-",
        ]
    )

def _sequence_prepare_export_row(row, *, sequence_no=None):
    prepared = dict(row or {})
    application_number = str(prepared.get("Application Number") or "").strip()
    beneficiary_name = str(prepared.get("Beneficiary Name") or "").strip()
    beneficiary_type = str(prepared.get("Beneficiary Type") or "").strip()

    if beneficiary_type == "District":
        prepared["Names"] = beneficiary_name
    elif application_number and beneficiary_name:
        prepared["Names"] = f"{application_number} - {beneficiary_name}"
    else:
        prepared["Names"] = application_number or beneficiary_name

    if beneficiary_type == "Public":
        prepared["R_Names"] = "AA_Public"
    elif beneficiary_type == "Institutions":
        prepared["R_Names"] = "A_Institutions"
    else:
        prepared["R_Names"] = beneficiary_name

    if sequence_no is not None:
        prepared["Sequence No"] = sequence_no
    elif "Sequence No" not in prepared:
        prepared["Sequence No"] = ""

    for header in list(prepared.keys()):
        value = prepared.get(header)
        if value is None or (isinstance(value, str) and not value.strip()):
            prepared[header] = "0" if header in TOKEN_GENERATION_NUMERIC_HEADERS else "N/A"
    return prepared

def _sequence_prepare_export_rows(rows):
    return [_sequence_prepare_export_row(row) for row in rows]

def _sequence_final_headers(seat_headers):
    headers = []
    inserted_names = False
    for header in seat_headers:
        headers.append(header)
        if header == "Application Number":
            headers.append("Names")
            inserted_names = True
    if not inserted_names:
        headers.append("Names")
    headers.extend(["Sequence No", "R_Names"])
    return headers

def _sequence_exact_compare(*, left_rows, left_headers, right_rows, right_headers, matched_label, mismatch_label):
    if list(left_headers) != list(right_headers):
        return {
            "matched": False,
            "details": (
                f"{mismatch_label}. Column mismatch: final has {len(left_headers)} column(s), "
                f"expected {len(right_headers)} column(s)."
            ),
        }

    left_counter = Counter(_sequence_row_key(row, left_headers) for row in left_rows)
    right_counter = Counter(_sequence_row_key(row, right_headers) for row in right_rows)
    if left_counter == right_counter:
        return {
            "matched": True,
            "details": matched_label,
        }

    missing_counter = right_counter - left_counter
    extra_counter = left_counter - right_counter
    parts = []
    if missing_counter:
        missing_key = next(iter(missing_counter))
        missing_row = {header: missing_key[idx] for idx, header in enumerate(right_headers)}
        parts.append(
            f"missing {sum(missing_counter.values())} row(s), e.g. {_sequence_row_label(missing_row)}"
        )
    if extra_counter:
        extra_key = next(iter(extra_counter))
        extra_row = {header: extra_key[idx] for idx, header in enumerate(left_headers)}
        parts.append(
            f"extra {sum(extra_counter.values())} row(s), e.g. {_sequence_row_label(extra_row)}"
        )

    return {
        "matched": False,
        "details": f"{mismatch_label}. " + " | ".join(parts),
    }

def _sequence_final_export_rows(session, sequence_map):
    seat_rows = list(
        models.SeatAllocationRow.objects.filter(session=session).order_by(
            "sort_order",
            "requested_item",
            "application_number",
            "id",
        )
    )
    seat_export_rows, seat_export_headers = _phase2_export_rows(seat_rows, include_sequence=False)
    final_export_rows = []
    for row in seat_export_rows:
        item_name = str(row.get("Requested Item") or "").strip()
        final_row = dict(row)
        final_row["Sequence No"] = sequence_map.get(item_name, "")
        final_export_rows.append(final_row)
    return {
        "seat_rows": seat_export_rows,
        "seat_headers": seat_export_headers,
        "final_rows": final_export_rows,
        "final_headers": [*seat_export_headers, "Sequence No"],
    }

def _sequence_map_from_seat_allocation(session):
    sequence_map = {}
    for item_name, sequence_no in (
        models.SeatAllocationRow.objects.filter(session=session)
        .exclude(sequence_no__isnull=True)
        .values_list("requested_item", "sequence_no")
    ):
        item_name = str(item_name or "").strip()
        if item_name and sequence_no and item_name not in sequence_map:
            sequence_map[item_name] = int(sequence_no)
    return sequence_map

def _sequence_seat_allocation_integrity(session):
    source_rows = _phase2_master_export_rows()
    seat_rows = list(models.SeatAllocationRow.objects.filter(session=session))
    grouped_rows = [
        {
            "application_number": row.application_number or "",
            "beneficiary_name": row.beneficiary_name or "",
            "district": row.district or "",
            "requested_item": row.requested_item or "",
            "quantity": int(row.quantity or 0),
            "waiting_hall_quantity": int(row.waiting_hall_quantity or 0),
            "token_quantity": int(row.token_quantity or 0),
            "beneficiary_type": row.beneficiary_type or "",
            "item_type": row.item_type or "",
            "comments": row.comments or "",
            "master_row": row.master_row or {},
            "master_headers": row.master_headers or [],
        }
        for row in seat_rows
    ]
    snapshot = _phase2_reconciliation_snapshot(
        source_rows=source_rows,
        grouped_rows=grouped_rows,
        total_value_getter=lambda row: _phase2_parse_number(
            row.get("Total Value")
            if isinstance(row, dict) and "Total Value" in row
            else (row.get("master_row") or {}).get("Total Value")
        ),
    )
    return {
        "snapshot": snapshot,
        "checks": _phase2_reconciliation_checks(snapshot),
        "split_check": _phase2_split_reconciliation(seat_rows),
    }
