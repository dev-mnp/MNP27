"""Shared token-generation helper functions reused across modules."""

from collections import Counter
from decimal import Decimal, InvalidOperation

from django.db.models import F
from django.utils import timezone

from core import models
from core.shared.export import _sequence_row_label
from core.shared.phase2 import _phase2_export_rows
from core.shared.phase2 import _phase2_parse_number
from core.shared.phase2 import _phase2_unique_headers

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


def _reconciliation_parse_decimal(value):
    raw = str(value or "").replace(",", "").strip()
    try:
        return Decimal(raw or "0")
    except (InvalidOperation, ValueError):
        return Decimal("0")

def _token_generation_empty_value_summary(rows, headers):
    entries = []
    for header in headers:
        empty_count = 0
        for row in rows:
            value = row.get(header, "")
            if value is None or (isinstance(value, str) and not value.strip()):
                empty_count += 1
        if empty_count:
            entries.append(
                {
                    "column": header,
                    "count": empty_count,
                    "fill_value": "0" if header in TOKEN_GENERATION_NUMERIC_HEADERS else "N/A",
                }
            )
    return entries

def _token_generation_invalid_value_summary(rows, headers=None):
    checks = [
        ("Quantity", "Quantity"),
        ("Cost Per Unit", "Cost Per Unit"),
        ("Total Value", "Total Value"),
    ]
    header_set = {str(header or "").strip() for header in (headers or []) if str(header or "").strip()}
    entries = []
    for header, label in checks:
        if header_set and header not in header_set:
            continue
        invalid_count = 0
        for row in rows:
            value = _reconciliation_parse_decimal(row.get(header))
            if value < Decimal("1"):
                invalid_count += 1
        if invalid_count:
            entries.append(
                {
                    "column": header,
                    "label": label,
                    "count": invalid_count,
                }
            )
    return entries

def _token_generation_sequence_no(value):
    parsed = _phase2_parse_number(value)
    if parsed is None:
        return 10**9
    try:
        return int(parsed)
    except (TypeError, ValueError):
        return 10**9

def _token_generation_sort_order(row):
    beneficiary_type = str(row.get("Beneficiary Type") or "").strip()
    requested_item = str(row.get("Requested Item") or "")
    application_number = str(row.get("Application Number") or "").strip()
    handicapped_status = str(row.get("Handicapped Status") or "").strip().lower()
    names_value = str(row.get("Names") or "").strip()
    is_public_laptop = beneficiary_type == "Public" and "laptop" in requested_item.lower()
    p116_top = 0 if is_public_laptop and application_number == "P116" else 1
    handicap_first = 0 if handicapped_status == "yes" else 1
    return (
        _token_generation_sequence_no(row.get("Sequence No")),
        TOKEN_GENERATION_BENEFICIARY_ORDER.get(beneficiary_type, 99),
        p116_top,
        handicap_first,
        names_value.lower(),
        str(row.get("Requested Item") or "").strip().lower(),
        application_number.lower(),
    )

def _token_generation_apply_names_cleanup(row):
    names_value = str(row.get("Names") or "").strip()
    if names_value in TOKEN_GENERATION_RENAME_MAP:
        row["Names"] = TOKEN_GENERATION_RENAME_MAP[names_value]
    token_name = str(row.get("Token Name") or "").strip()
    if token_name == "Wet Grinder Floor 2L":
        row["Token Name"] = "Wet Grinder FLR 2L"
    return row

def _token_generation_token_print_flag(row):
    token_quantity = max(_phase2_parse_number(row.get("Token Quantity")) or 0, 0)
    item_type = str(row.get("Item Type") or "").strip()
    requested_item = str(row.get("Requested Item") or "").strip()
    flag = 1 if item_type == models.ItemTypeChoices.ARTICLE and requested_item not in TOKEN_GENERATION_ARTICLE_PRINT_EXCLUDES else 0
    if token_quantity <= 0:
        flag = 0
    row["Token Print for ARTL"] = str(flag)
    return row

def _token_generation_apply_token_ranges(rows):
    running_end = 0
    for row in rows:
        token_quantity = max(_phase2_parse_number(row.get("Token Quantity")) or 0, 0)
        if token_quantity > 0:
            start_token = running_end + 1
            end_token = running_end + token_quantity
            running_end = end_token
        else:
            start_token = 0
            end_token = 0
        row["Start Token No"] = str(start_token)
        row["End Token No"] = str(end_token)
    return rows

def _token_generation_quality_checks(rows):
    sequence_to_items = {}
    item_to_sequences = {}
    token_quantity_total = 0
    printable_token_total = 0
    zero_token_rows = 0
    duplicate_rows = 0
    duplicate_example = None
    row_counter = Counter()

    for row in rows:
        row_key = tuple((key, "" if row.get(key) is None else str(row.get(key))) for key in sorted(row.keys()))
        row_counter[row_key] += 1
        sequence_no = _phase2_parse_number(row.get("Sequence No"))
        requested_item = str(row.get("Requested Item") or "").strip()
        if sequence_no:
            sequence_to_items.setdefault(int(sequence_no), set()).add(requested_item)
        if requested_item:
            item_to_sequences.setdefault(requested_item, set())
            if sequence_no:
                item_to_sequences[requested_item].add(int(sequence_no))

        token_quantity = max(_phase2_parse_number(row.get("Token Quantity")) or 0, 0)
        token_quantity_total += token_quantity
        if token_quantity == 0:
            zero_token_rows += 1
        if str(row.get("Token Print for ARTL") or "").strip() == "1":
            printable_token_total += token_quantity

    sequence_item_conflicts = [
        {
            "sequence_no": sequence_no,
            "items": sorted(item for item in items if item),
        }
        for sequence_no, items in sorted(sequence_to_items.items())
        if len({item for item in items if item}) > 1
    ]
    article_sequence_conflicts = [
        {
            "requested_item": requested_item,
            "sequence_numbers": sorted(sequence_numbers),
        }
        for requested_item, sequence_numbers in sorted(item_to_sequences.items())
        if len(sequence_numbers) > 1
    ]

    sequence_numbers = sorted(
        int(number)
        for number in {
            _phase2_parse_number(row.get("Sequence No"))
            for row in rows
        }
        if number
    )
    max_sequence = max(sequence_numbers) if sequence_numbers else 0
    missing_sequences = [number for number in range(1, max_sequence + 1) if number not in set(sequence_numbers)]

    for row_key, count in row_counter.items():
        if count > 1:
            duplicate_rows += count - 1
            if duplicate_example is None:
                row_map = dict(row_key)
                duplicate_example = _sequence_row_label(row_map)

    return {
        "sequence_item_conflicts": sequence_item_conflicts,
        "article_sequence_conflicts": article_sequence_conflicts,
        "missing_sequences": missing_sequences,
        "token_quantity_total": token_quantity_total,
        "printable_token_total": printable_token_total,
        "zero_token_rows": zero_token_rows,
        "duplicate_rows": duplicate_rows,
        "duplicate_example": duplicate_example or "",
    }

def _token_generation_headers(base_headers):
    headers = []
    inserted_names = False
    base_headers = _phase2_unique_headers(base_headers)
    for header in list(base_headers or []):
        headers.append(header)
        if header == "Application Number" and "Names" not in headers:
            headers.append("Names")
            inserted_names = True
    if not inserted_names and "Names" not in headers:
        headers.append("Names")
    if "Token Print for ARTL" not in headers:
        headers.append("Token Print for ARTL")
    return _phase2_unique_headers(headers)

def _token_generation_generated_headers(base_headers):
    headers = _phase2_unique_headers(base_headers)
    if "Start Token No" not in headers:
        headers.append("Start Token No")
    if "End Token No" not in headers:
        headers.append("End Token No")
    return _phase2_unique_headers(headers)

def _token_generation_prepare_row(row):
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
    for header in list(prepared.keys()):
        value = prepared.get(header)
        if value is None or (isinstance(value, str) and not value.strip()):
            prepared[header] = "0" if header in TOKEN_GENERATION_NUMERIC_HEADERS else "N/A"
    prepared = _token_generation_apply_names_cleanup(prepared)
    prepared = _token_generation_token_print_flag(prepared)
    return prepared

def _token_generation_prepare_dataset(rows, headers):
    prepared_headers = _token_generation_headers(headers)
    prepared_rows = [_token_generation_prepare_row(row) for row in rows]
    prepared_rows = _token_generation_sort_dataset(prepared_rows)
    blank_summary = _token_generation_empty_value_summary(rows, prepared_headers)
    quality_checks = _token_generation_quality_checks(prepared_rows)
    return {
        "headers": prepared_headers,
        "rows": prepared_rows,
        "blank_summary": blank_summary,
        "quality_checks": quality_checks,
    }

def _token_generation_sort_dataset(rows):
    sorted_rows = [dict(row) for row in rows]
    sorted_rows.sort(key=_token_generation_sort_order)
    return sorted_rows

def _token_generation_generate_dataset(rows, headers):
    generated_rows = _token_generation_sort_dataset(rows)
    generated_rows = _token_generation_apply_token_ranges(generated_rows)
    return {
        "headers": _token_generation_generated_headers(headers),
        "rows": generated_rows,
    }

def _token_generation_is_sorted(rows):
    if not rows:
        return False
    return [dict(row) for row in rows] == _token_generation_sort_dataset(rows)

def _token_generation_is_generated(rows):
    if not rows:
        return False
    has_any_token = False
    for row in rows:
        token_quantity = max(_phase2_parse_number(row.get("Token Quantity")) or 0, 0)
        start_token = _phase2_parse_number(row.get("Start Token No"))
        end_token = _phase2_parse_number(row.get("End Token No"))
        if token_quantity > 0:
            has_any_token = True
            if not start_token or not end_token:
                return False
        else:
            if (start_token or 0) != 0 or (end_token or 0) != 0:
                return False
    return has_any_token

def _token_generation_edit_candidates(rows, *, length_limit):
    unique_names = []
    unique_token_names = []
    seen_names = set()
    seen_token_names = set()
    for row in rows:
        names_value = str(row.get("Names") or "").strip()
        token_name_value = str(row.get("Token Name") or "").strip()
        if len(names_value) > length_limit and names_value not in seen_names:
            seen_names.add(names_value)
            unique_names.append({"value": names_value, "length": len(names_value)})
        if len(token_name_value) > length_limit and token_name_value not in seen_token_names:
            seen_token_names.add(token_name_value)
            unique_token_names.append({"value": token_name_value, "length": len(token_name_value)})
    return {
        "names": unique_names,
        "token_names": unique_token_names,
    }

def _token_generation_parse_rule_lines(raw_value):
    lines = []
    seen = set()
    for line in str(raw_value or "").splitlines():
        value = line.strip()
        normalized = value.lower()
        if value and normalized not in seen:
            seen.add(normalized)
            lines.append(value)
    return lines

def _token_generation_filter_state(request):
    return {
        "application_number": str(request.GET.get("filter_application_number") or "").strip(),
        "beneficiary_name": str(request.GET.get("filter_beneficiary_name") or "").strip(),
        "beneficiary_type": str(request.GET.get("filter_beneficiary_type") or "").strip(),
        "requested_item": str(request.GET.get("filter_requested_item") or "").strip(),
        "item_type": str(request.GET.get("filter_item_type") or "").strip(),
        "comments": str(request.GET.get("filter_comments") or "").strip(),
    }

def _token_generation_filter_rows(rows, filters):
    entries = []
    for index, row in enumerate(rows):
        application_number = str(row.get("Application Number") or "").strip()
        beneficiary_name = str(row.get("Beneficiary Name") or "").strip()
        beneficiary_type = str(row.get("Beneficiary Type") or "").strip()
        requested_item = str(row.get("Requested Item") or "").strip()
        item_type = str(row.get("Item Type") or "").strip()
        comments = str(row.get("Comments") or "").strip()

        if filters["application_number"] and filters["application_number"].lower() not in application_number.lower():
            continue
        if filters["beneficiary_name"] and filters["beneficiary_name"].lower() not in beneficiary_name.lower():
            continue
        if filters["beneficiary_type"] and filters["beneficiary_type"].lower() != beneficiary_type.lower():
            continue
        if filters["requested_item"] and filters["requested_item"].lower() not in requested_item.lower():
            continue
        if filters["item_type"] and filters["item_type"].lower() != item_type.lower():
            continue
        if filters["comments"] and filters["comments"].lower() not in comments.lower():
            continue

        entries.append(
            {
                "row_index": index,
                "application_number": application_number,
                "beneficiary_name": beneficiary_name,
                "beneficiary_type": beneficiary_type,
                "requested_item": requested_item,
                "item_type": item_type,
                "comments": comments,
            }
        )
    return entries

def _token_generation_has_active_filters(filters):
    return any(str(value or "").strip() for value in (filters or {}).values())

def _token_generation_article_toggle_rows(rows):
    article_rows = {}
    for row in rows:
        if str(row.get("Item Type") or "").strip() != models.ItemTypeChoices.ARTICLE:
            continue
        requested_item = str(row.get("Requested Item") or "").strip()
        if not requested_item:
            continue
        article_rows.setdefault(requested_item, []).append(row)

    entries = []
    for requested_item in sorted(article_rows.keys(), key=str.lower):
        item_rows = article_rows[requested_item]
        skip_label = all(str(row.get("Token Print for ARTL") or "").strip() == "0" for row in item_rows)
        token_total = sum(max(_phase2_parse_number(row.get("Token Quantity")) or 0, 0) for row in item_rows)
        entries.append(
            {
                "requested_item": requested_item,
                "token_total": token_total,
                "skip_label": skip_label,
            }
        )
    return entries

def _token_generation_source_dataset(session):
    seat_rows = models.SeatAllocationRow.objects.filter(session=session).order_by(
        F("sequence_no").asc(nulls_last=True),
        "sort_order",
        "requested_item",
        "application_number",
        "id",
    )
    source_rows, source_headers = _phase2_export_rows(seat_rows, include_sequence=True)
    return {
        "headers": source_headers,
        "rows": source_rows,
        "blank_summary": _token_generation_empty_value_summary(source_rows, source_headers),
        "quality_checks": _token_generation_quality_checks(source_rows),
    }

def _token_generation_store_dataset(*, session, dataset, source_name, user):
    models.TokenGenerationRow.objects.filter(session=session).delete()
    rows = dataset["rows"]
    headers = _phase2_unique_headers(dataset["headers"])
    models.TokenGenerationRow.objects.bulk_create(
        [
            models.TokenGenerationRow(
                session=session,
                source_file_name=source_name,
                application_number=str(row.get("Application Number") or "").strip() or None,
                beneficiary_name=str(row.get("Beneficiary Name") or "").strip() or None,
                requested_item=str(row.get("Requested Item") or "").strip() or None,
                beneficiary_type=str(row.get("Beneficiary Type") or "").strip() or None,
                sequence_no=_phase2_parse_number(row.get("Sequence No")) or None,
                start_token_no=_phase2_parse_number(row.get("Start Token No")) or 0,
                end_token_no=_phase2_parse_number(row.get("End Token No")) or 0,
                row_data=row,
                headers=headers,
                sort_order=index + 1,
                created_by=user,
                updated_by=user,
            )
            for index, row in enumerate(rows)
        ]
    )

def _token_generation_saved_dataset(session):
    rows = list(
        models.TokenGenerationRow.objects.filter(session=session).order_by(
            "sort_order",
            F("sequence_no").asc(nulls_last=True),
            "requested_item",
            "application_number",
            "id",
        )
    )
    if not rows:
        return {"headers": [], "rows": [], "source_name": "", "saved_at": None}
    headers = _phase2_unique_headers(rows[0].headers or [])
    has_start_token_header = "Start Token No" in headers
    has_end_token_header = "End Token No" in headers
    prepared_rows = []
    for row in rows:
        row_data = dict(row.row_data or {})
        row_data["Application Number"] = row.application_number or row_data.get("Application Number") or ""
        row_data["Beneficiary Name"] = row.beneficiary_name or row_data.get("Beneficiary Name") or ""
        row_data["Requested Item"] = row.requested_item or row_data.get("Requested Item") or ""
        row_data["Beneficiary Type"] = row.beneficiary_type or row_data.get("Beneficiary Type") or ""
        row_data["Sequence No"] = row.sequence_no if row.sequence_no is not None else row_data.get("Sequence No") or ""
        include_start_token = has_start_token_header or "Start Token No" in row_data or (row.start_token_no or 0) > 0
        include_end_token = has_end_token_header or "End Token No" in row_data or (row.end_token_no or 0) > 0
        if include_start_token:
            row_data["Start Token No"] = row.start_token_no if row.start_token_no is not None else row_data.get("Start Token No") or 0
        else:
            row_data.pop("Start Token No", None)
        if include_end_token:
            row_data["End Token No"] = row.end_token_no if row.end_token_no is not None else row_data.get("End Token No") or 0
        else:
            row_data.pop("End Token No", None)
        existing_token_quantity = row_data.get("Token Quantity")
        if existing_token_quantity in {None, ""}:
            existing_token_quantity = max(
                (row.end_token_no or 0) - (row.start_token_no or 0) + 1,
                0,
            )
        row_data["Token Quantity"] = existing_token_quantity
        prepared_rows.append(row_data)
    return {
        "headers": headers,
        "rows": prepared_rows,
        "source_name": rows[0].source_file_name or "",
        "saved_at": rows[0].updated_at,
    }

def _token_generation_stage_state(request, session):
    state_map = request.session.get("token_generation_stage_state", {})
    return dict(state_map.get(str(session.pk), {}))

def _token_generation_set_stage_state(request, session, **updates):
    state_map = dict(request.session.get("token_generation_stage_state", {}))
    session_state = dict(state_map.get(str(session.pk), {}))
    session_state.update(updates)
    state_map[str(session.pk)] = session_state
    request.session["token_generation_stage_state"] = state_map
    request.session.modified = True

def _token_generation_latest_source_marker(session):
    latest_source_updated_at = (
        models.SeatAllocationRow.objects.filter(session=session)
        .order_by("-updated_at", "-created_at")
        .values_list("updated_at", flat=True)
        .first()
    )
    if not latest_source_updated_at:
        return ""
    return timezone.localtime(latest_source_updated_at).isoformat()

def _token_generation_sync_required(request, session, dataset=None):
    dataset = dataset or _token_generation_saved_dataset(session)
    if not dataset["rows"]:
        return False
    source_name = str(dataset.get("source_name") or "")
    if not source_name.startswith("Synced from Sequence List"):
        return False
    stage_state = _token_generation_stage_state(request, session)
    return str(stage_state.get("source_sync_marker") or "") != _token_generation_latest_source_marker(session)
