from __future__ import annotations

"""Labels helper/service functions extracted from legacy web_views."""

import io

from django.db import transaction
from django.db.models import F
from django.utils import timezone
from django.utils.html import escape

from reportlab.lib.pagesizes import A4, landscape, portrait
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph
from core import models
from core.shared.phase2 import _phase2_parse_number
from core.shared.phase2 import _phase2_unique_headers
from core.shared.token_generation import _token_generation_saved_dataset


LABELS_DEFAULT_2L_ITEMS = [
    "Tiffen Set",
    "Tiffen Set + Alu Idli Box + MS Stove 2 Burner",
    "Tiffen Set + MS Stove 2 Burner",
    "Tiffen Set + Tea Can 10 Ltrs SS",
    "Push Cart Without Top",
    "Push Cart With Top",
    "Push Cart With Top + Alu Idli Box + MS Stove 2 Burner",
    "Office Table 4 X 2",
    "S Type Chair",
    "Steel Cupboard 6 1/2'",
]


def _labels_article_name(row):
    token_name = str(row.get("Token Name") or "").strip()
    if token_name:
        return token_name
    return str(row.get("Requested Item") or "").strip()


LABEL_LAYOUTS = {
    "12L": {
        "page_size": portrait(A4),
        "top_margin": 9 * mm,
        "side_margin": 4 * mm,
        "vertical_pitch": 47 * mm,
        "horizontal_pitch": 102 * mm,
        "label_height": 44 * mm,
        "label_width": 100 * mm,
        "number_across": 2,
        "number_down": 6,
        "token_font": 60,
        "token_font_medium": 50,
        "token_font_small": 47,
        "line_font": 15,
        "line_leading": 16,
        "name_leading": 14,
        "name_space_after": 20,
        "article_y": 6 * mm,
        "name_vertical_factor": 0.85,
    },
    "2L": {
        "page_size": portrait(A4),
        "top_margin": 2.5 * mm,
        "side_margin": 5 * mm,
        "vertical_pitch": 146 * mm,
        "horizontal_pitch": 200 * mm,
        "label_height": 146 * mm,
        "label_width": 200 * mm,
        "number_across": 1,
        "number_down": 2,
        "token_font": 80,
        "token_font_medium": 80,
        "token_font_small": 70,
        "line_font": 35,
        "line_leading": 35,
        "name_leading": 35,
        "name_space_after": 0,
        "article_y": 35 * mm,
        "name_vertical_factor": 0.66,
    },
    "A4": {
        "page_size": landscape(A4),
        "top_margin": 12 * mm,
        "side_margin": 12 * mm,
        "vertical_pitch": 0,
        "horizontal_pitch": 0,
        "label_height": landscape(A4)[1] - 24 * mm,
        "label_width": landscape(A4)[0] - 24 * mm,
        "number_across": 1,
        "number_down": 1,
    },
}


def _label_token_font_size(token_text: str, config: dict) -> int:
    if len(token_text) >= 4:
        return config["token_font_small"]
    if len(token_text) == 3:
        return config["token_font_medium"]
    return config["token_font"]


def _draw_standard_label(pdf_canvas, entry: dict, *, x: float, y: float, config: dict) -> None:
    token_text = str(entry.get("token") or "")
    name_text = str(entry.get("name") or "")
    article_text = str(entry.get("article") or "")

    token_style = ParagraphStyle(
        name=f"token-{config['label_width']}",
        fontSize=_label_token_font_size(token_text, config),
        alignment=0,
    )
    article_style = ParagraphStyle(
        name=f"article-{config['label_width']}",
        fontSize=config["line_font"],
        leading=config["line_leading"],
        alignment=1,
    )
    name_style = ParagraphStyle(
        name=f"name-{config['label_width']}",
        fontSize=config["line_font"],
        leading=config["name_leading"],
        spaceAfter=config.get("name_space_after", 0),
        alignment=1,
    )

    token_para = Paragraph(f"<b>{escape(token_text)}</b>", token_style)
    article_para = Paragraph(f"<b>{escape(article_text)}</b>", article_style)
    name_para = Paragraph(f"<b>{escape(name_text)}</b>", name_style)

    label_width = config["label_width"]
    label_height = config["label_height"]

    token_width, token_height = token_para.wrap(label_width / 2, label_height)
    token_para.drawOn(pdf_canvas, x + 8 * mm, y + 0.66 * (label_height - token_height))

    name_width, name_height = name_para.wrap(label_width / 2, label_height)
    name_para.drawOn(
        pdf_canvas,
        x + 0.8 * (label_width - name_width),
        y + config["name_vertical_factor"] * (label_height - name_height),
    )

    article_width, article_height = article_para.wrap(label_width / 2, label_height)
    article_para.drawOn(pdf_canvas, x + 0.8 * (label_width - article_width), y + config["article_y"])


def generate_mnp_labels_pdf(entries: list[dict], *, layout: str = "12L", mode: str = "continuous") -> io.BytesIO:
    config = LABEL_LAYOUTS[layout]
    buffer = io.BytesIO()
    pdf_canvas = canvas.Canvas(buffer, pagesize=config["page_size"])
    _width, height = config["page_size"]
    per_page = config["number_across"] * config["number_down"]
    slot_index = 0
    current_group = None

    for entry in entries:
        group_key = str(entry.get("group") or "")
        if mode == "separate" and current_group is not None and group_key != current_group:
            pdf_canvas.showPage()
            slot_index = 0
        elif slot_index and slot_index % per_page == 0:
            pdf_canvas.showPage()
            slot_index = 0

        current_group = group_key if mode == "separate" else current_group
        col = slot_index % config["number_across"]
        row = slot_index // config["number_across"] % config["number_down"]
        x = config["side_margin"] + col * config["horizontal_pitch"]
        y = height - config["top_margin"] - row * config["vertical_pitch"] - config["label_height"]
        _draw_standard_label(pdf_canvas, entry, x=x, y=y, config=config)
        slot_index += 1

    pdf_canvas.save()
    buffer.seek(0)
    return buffer


def generate_mnp_custom_labels_pdf(entries, *, layout: str = "12L") -> io.BytesIO:
    config = LABEL_LAYOUTS[layout]
    buffer = io.BytesIO()
    pdf_canvas = canvas.Canvas(buffer, pagesize=config["page_size"])
    _width, height = config["page_size"]
    per_page = config["number_across"] * config["number_down"]
    default_font_size = 72 if layout == "A4" else 30 if layout == "12L" else 54

    normalized_entries = []
    if isinstance(entries, list):
        for entry in entries:
            if isinstance(entry, dict):
                text = str(entry.get("text") or "").strip()
                count = int(entry.get("count") or 0)
                font_size = int(entry.get("font_size") or default_font_size)
                line_spacing = entry.get("line_spacing")
            elif isinstance(entry, (list, tuple)) and len(entry) >= 2:
                text = str(entry[0] or "").strip()
                count = int(entry[1] or 0)
                font_size = int(entry[2] or default_font_size) if len(entry) >= 3 else default_font_size
                line_spacing = int(entry[3] or 0) if len(entry) >= 4 else None
            else:
                text = str(entry or "").strip()
                count = 1
                font_size = default_font_size
                line_spacing = None
            font_size = max(8, min(font_size, 120))
            if line_spacing is not None:
                line_spacing = max(0, min(int(line_spacing), 120))
            if text and count > 0:
                normalized_entries.extend([{"text": text, "font_size": font_size, "line_spacing": line_spacing}] * count)
    else:
        text = str(entries or "").strip()
        if text:
            normalized_entries.append({"text": text, "font_size": default_font_size, "line_spacing": None})

    def _custom_label_markup(raw_text: str) -> str:
        escaped = escape(str(raw_text or "").strip())
        escaped = escaped.replace("\r\n", "\n").replace("\r", "\n")
        escaped = escaped.replace("|", "<br/>").replace("\n", "<br/>")
        return escaped

    for index, entry in enumerate(normalized_entries):
        text = str(entry.get("text") or "").strip()
        font_size = int(entry.get("font_size") or default_font_size)
        line_spacing = entry.get("line_spacing")
        line_leading = font_size + (6 if layout == "A4" else 2 if layout == "12L" else 4)
        if line_spacing is not None:
            line_leading = font_size + max(0, min(int(line_spacing), 120))
        if index and index % per_page == 0:
            pdf_canvas.showPage()
        slot_index = index % per_page
        col = slot_index % config["number_across"]
        row = slot_index // config["number_across"] % config["number_down"]
        x = config["side_margin"] + col * config["horizontal_pitch"]
        y = height - config["top_margin"] - row * config["vertical_pitch"] - config["label_height"]

        style = ParagraphStyle(
            name=f"custom-{layout}-{font_size}",
            fontSize=font_size,
            leading=line_leading,
            alignment=1,
        )
        para = Paragraph(f"<b>{_custom_label_markup(text)}</b>", style)
        wrapped_width, wrapped_height = para.wrap(config["label_width"] - 10 * mm, config["label_height"] - 10 * mm)
        para.drawOn(
            pdf_canvas,
            x + (config["label_width"] - wrapped_width) / 2,
            y + (config["label_height"] - wrapped_height) / 2,
        )

    pdf_canvas.save()
    buffer.seek(0)
    return buffer


def _labels_saved_dataset(session):
    rows = list(
        models.LabelGenerationRow.objects.filter(session=session).order_by(
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
    return {
        "headers": headers,
        "rows": [dict(row.row_data or {}) for row in rows],
        "source_name": rows[0].source_file_name or "",
        "saved_at": rows[0].updated_at,
    }


def _labels_store_dataset(*, session, dataset, source_name, user):
    rows = [dict(row) for row in list(dataset.get("rows") or [])]
    headers = _phase2_unique_headers(dataset.get("headers") or [])
    with transaction.atomic():
        models.LabelGenerationRow.objects.filter(session=session).delete()
        models.LabelGenerationRow.objects.bulk_create(
            [
                models.LabelGenerationRow(
                    session=session,
                    source_file_name=source_name or "",
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


def _labels_source_dataset(session):
    dataset = _token_generation_saved_dataset(session)
    return _labels_normalize_dataset({
        "headers": _phase2_unique_headers(dataset.get("headers") or []),
        "rows": [dict(row) for row in list(dataset.get("rows") or [])],
    })


def _labels_stage_state(request, session):
    state_map = request.session.get("labels_stage_state", {})
    session_state = dict(state_map.get(str(session.pk), {}))
    selected_items = session_state.get("large_items")
    if not isinstance(selected_items, list):
        selected_items = list(LABELS_DEFAULT_2L_ITEMS)
    session_state["large_items"] = selected_items
    session_state["large_items_saved"] = bool(session_state.get("large_items_saved"))
    return session_state


def _labels_set_stage_state(request, session, **updates):
    state_map = dict(request.session.get("labels_stage_state", {}))
    session_state = dict(state_map.get(str(session.pk), {}))
    session_state.update(updates)
    state_map[str(session.pk)] = session_state
    request.session["labels_stage_state"] = state_map
    request.session.modified = True


def _labels_latest_source_marker(session):
    latest_source_updated_at = (
        models.TokenGenerationRow.objects.filter(session=session)
        .order_by("-updated_at", "-created_at")
        .values_list("updated_at", flat=True)
        .first()
    )
    if not latest_source_updated_at:
        return ""
    return timezone.localtime(latest_source_updated_at).isoformat()


def _labels_sync_required(request, session, dataset=None):
    dataset = dataset or _labels_saved_dataset(session)
    if not dataset["rows"]:
        return False
    source_name = str(dataset.get("source_name") or "")
    if not source_name.startswith("Synced from Token Generation"):
        return False
    stage_state = _labels_stage_state(request, session)
    return str(stage_state.get("source_sync_marker") or "") != _labels_latest_source_marker(session)


def _labels_has_generated_tokens(rows):
    return bool(rows) and all(
        _phase2_parse_number(row.get("Start Token No")) is not None
        and _phase2_parse_number(row.get("End Token No")) is not None
        for row in rows
    )


def _labels_available_requested_items(rows):
    items = []
    seen = set()
    for row in rows:
        requested_item = str(row.get("Requested Item") or "").strip()
        if not requested_item or requested_item in seen:
            continue
        seen.add(requested_item)
        items.append(requested_item)
    return items


def _labels_expand_entries(rows, *, row_filter=None, group_by=None, sort_key=None):
    filtered_rows = []
    for row in rows:
        if row_filter and not row_filter(row):
            continue
        filtered_rows.append(dict(row))
    if sort_key:
        filtered_rows.sort(key=sort_key)

    entries = []
    for row in filtered_rows:
        start = _phase2_parse_number(row.get("Start Token No")) or 0
        end = _phase2_parse_number(row.get("End Token No")) or 0
        if start <= 0 or end < start:
            continue
        name_value = str(row.get("Names") or row.get("Beneficiary Name") or "").strip()
        article_value = _labels_article_name(row)
        group_value = group_by(row) if group_by else ""
        for token in range(start, end + 1):
            entries.append(
                {
                    "token": str(token),
                    "name": name_value,
                    "article": article_value,
                    "group": str(group_value or ""),
                }
            )
    return entries


def _labels_audit_download(rows, *, download_kind, large_items):
    large_items = set(large_items or [])

    def token_qty(row):
        return max(_phase2_parse_number(row.get("Token Quantity")) or 0, 0)

    def is_printable_article(row):
        return token_qty(row) > 0 and (_phase2_parse_number(row.get("Token Print for ARTL")) or 0) != 0

    def sort_by_name_and_start(row):
        return (
            str(row.get("Names") or "").strip(),
            _phase2_parse_number(row.get("Start Token No")) or 0,
        )

    def sort_by_item_and_start(row):
        return (
            _labels_article_name(row),
            str(row.get("Names") or "").strip(),
            _phase2_parse_number(row.get("Start Token No")) or 0,
        )

    row_filter = None
    group_by = None
    sort_key = None
    labels_per_page = 12

    if download_kind in {"article_12l_separate", "article_12l_continuous"}:
        row_filter = lambda row: is_printable_article(row) and str(row.get("Requested Item") or "").strip() not in large_items
        if download_kind == "article_12l_separate":
            group_by = lambda row: _labels_article_name(row)
    elif download_kind == "article_2l_continuous":
        row_filter = lambda row: token_qty(row) > 0 and str(row.get("Requested Item") or "").strip() in large_items
        labels_per_page = 2
    elif download_kind in {"district_separate", "district_continuous"}:
        row_filter = lambda row: token_qty(row) > 0 and str(row.get("Beneficiary Type") or "").strip() == "District"
        sort_key = sort_by_name_and_start
        if download_kind == "district_separate":
            group_by = lambda row: str(row.get("Names") or "").strip()
    elif download_kind == "institution":
        row_filter = lambda row: token_qty(row) > 0 and str(row.get("Beneficiary Type") or "").strip() == "Institutions"
        sort_key = sort_by_name_and_start
    elif download_kind == "others":
        row_filter = lambda row: token_qty(row) > 0 and str(row.get("Beneficiary Type") or "").strip() == "Others"
        sort_key = sort_by_name_and_start
    elif download_kind == "public":
        row_filter = lambda row: token_qty(row) > 0 and str(row.get("Beneficiary Type") or "").strip() == "Public"
        sort_key = sort_by_item_and_start
    elif download_kind in {"chair_separate", "chair_continuous"}:
        if download_kind == "chair_separate":
            row_filter = lambda row: token_qty(row) > 0
            group_by = lambda row: _labels_article_name(row)
        else:
            row_filter = lambda row: token_qty(row) > 0
    else:
        return {
            "ready": False,
            "status_label": "Needs Review",
            "status_class": "bad",
            "reason": "Unknown label download type.",
            "included_rows": 0,
            "expected_labels": 0,
            "actual_labels": 0,
            "first_token": 0,
            "last_token": 0,
            "duplicate_tokens": 0,
            "invalid_range_rows": 0,
            "missing_labels": 0,
            "page_count": 0,
        }

    filtered_rows = [dict(row) for row in rows if not row_filter or row_filter(row)]
    expected_labels = sum(token_qty(row) for row in filtered_rows)
    invalid_range_rows = 0
    for row in filtered_rows:
        start = _phase2_parse_number(row.get("Start Token No")) or 0
        end = _phase2_parse_number(row.get("End Token No")) or 0
        qty = token_qty(row)
        if qty <= 0:
            continue
        if start <= 0 or end < start or (end - start + 1) != qty:
            invalid_range_rows += 1

    entries = _labels_expand_entries(filtered_rows, group_by=group_by, sort_key=sort_key)
    tokens = [int(entry["token"]) for entry in entries if str(entry.get("token") or "").strip().isdigit()]
    actual_labels = len(entries)
    duplicate_tokens = max(actual_labels - len(set(tokens)), 0)
    missing_labels = max(expected_labels - actual_labels, 0)
    page_count = 0
    if actual_labels:
        if group_by:
            grouped_counts = {}
            for entry in entries:
                group_key = str(entry.get("group") or "")
                grouped_counts[group_key] = grouped_counts.get(group_key, 0) + 1
            page_count = sum(((count - 1) // labels_per_page) + 1 for count in grouped_counts.values() if count > 0)
        else:
            page_count = ((actual_labels - 1) // labels_per_page) + 1
    ready = expected_labels > 0 and duplicate_tokens == 0 and invalid_range_rows == 0 and missing_labels == 0
    reason = ""
    status_label = "Data Ready"
    status_class = "ok"
    if expected_labels <= 0:
        status_label = "No Matching Rows"
        status_class = "neutral"
        reason = "No matching token rows are currently available for this label type."
    elif duplicate_tokens > 0:
        status_label = "Needs Review"
        status_class = "bad"
        reason = f"{duplicate_tokens} duplicate token number(s) found."
    elif invalid_range_rows > 0:
        status_label = "Needs Review"
        status_class = "bad"
        reason = f"{invalid_range_rows} row(s) have invalid token ranges."
    elif missing_labels > 0:
        status_label = "Needs Review"
        status_class = "bad"
        reason = f"{missing_labels} expected label(s) are missing from token ranges."

    return {
        "ready": ready,
        "status_label": status_label,
        "status_class": status_class,
        "reason": reason,
        "included_rows": len(filtered_rows),
        "expected_labels": expected_labels,
        "actual_labels": actual_labels,
        "first_token": min(tokens) if tokens else 0,
        "last_token": max(tokens) if tokens else 0,
        "duplicate_tokens": duplicate_tokens,
        "invalid_range_rows": invalid_range_rows,
        "missing_labels": missing_labels,
        "page_count": page_count,
    }


def _labels_normalize_row(row):
    normalized = dict(row or {})
    if "Token Name" not in normalized or not str(normalized.get("Token Name") or "").strip():
        legacy_token_name = str(normalized.get("Requested Item Tk") or "").strip()
        normalized["Token Name"] = legacy_token_name or str(normalized.get("Requested Item") or "").strip()
    if "Start Token No" not in normalized:
        normalized["Start Token No"] = normalized.get("Start Token No.", "")
    if "End Token No" not in normalized:
        normalized["End Token No"] = normalized.get("End Token No.", "")
    if "Names" not in normalized or not str(normalized.get("Names") or "").strip():
        application_number = str(normalized.get("Application Number") or "").strip()
        beneficiary_name = str(normalized.get("Beneficiary Name") or "").strip()
        beneficiary_type = str(normalized.get("Beneficiary Type") or "").strip()
        if beneficiary_type == "District":
            normalized["Names"] = beneficiary_name
        else:
            normalized["Names"] = f"{application_number} - {beneficiary_name}".strip(" -") if (application_number or beneficiary_name) else ""
    start_token = _phase2_parse_number(normalized.get("Start Token No"))
    end_token = _phase2_parse_number(normalized.get("End Token No"))
    if "Token Quantity" not in normalized or not str(normalized.get("Token Quantity") or "").strip():
        normalized["Token Quantity"] = str(max(end_token - start_token + 1, 0) if start_token and end_token >= start_token else 0)
    if "Token Print for ARTL" not in normalized or not str(normalized.get("Token Print for ARTL") or "").strip():
        normalized["Token Print for ARTL"] = "1" if (_phase2_parse_number(normalized.get("Token Quantity")) or 0) > 0 else "0"
    return normalized


def _labels_normalize_headers(headers, rows):
    normalized_headers = []
    for header in _phase2_unique_headers(headers):
        if header == "Requested Item Tk":
            if "Token Name" not in normalized_headers:
                normalized_headers.append("Token Name")
            continue
        if header == "Start Token No.":
            if "Start Token No" not in normalized_headers:
                normalized_headers.append("Start Token No")
            continue
        if header == "End Token No.":
            if "End Token No" not in normalized_headers:
                normalized_headers.append("End Token No")
            continue
        if header not in normalized_headers:
            normalized_headers.append(header)
    for required_header in ["Names", "Token Name", "Token Quantity", "Token Print for ARTL", "Start Token No", "End Token No"]:
        if any(required_header in row for row in rows) and required_header not in normalized_headers:
            normalized_headers.append(required_header)
    return _phase2_unique_headers(normalized_headers)


def _labels_normalize_dataset(dataset):
    rows = [_labels_normalize_row(row) for row in list(dataset.get("rows") or [])]
    headers = _labels_normalize_headers(dataset.get("headers") or [], rows)
    return {
        "headers": headers,
        "rows": rows,
    }


def _labels_download_filename(prefix):
    timestamp = timezone.localtime().strftime("%d_%b_%y_%H_%M")
    return f"{prefix}_{timestamp}.pdf"
