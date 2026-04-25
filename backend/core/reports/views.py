from __future__ import annotations

"""Views for reports workflow."""

import base64
from datetime import date
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import FileResponse, HttpResponse, HttpResponseRedirect
from django.urls import reverse
from django.utils import timezone
from django.views.generic import TemplateView

from core import models
from core.reports import services
from core.reports.services import REPORTS_DISTRIBUTION_STATE_KEY
from core.reports.services import REPORTS_SEGREGATION_STATE_KEY
from core.reports.services import REPORTS_WAITING_HALL_STATE_KEY
from core.reports.services import STAGE_DISTRIBUTION_BENEFICIARY_FILTER_CHOICES
from core.reports.services import STAGE_DISTRIBUTION_ITEM_FILTER_CHOICES
from core.reports.services import STAGE_DISTRIBUTION_PREMISE_FILTER_CHOICES
from core.reports.services import SEGREGATION_BENEFICIARY_FILTER_CHOICES
from core.reports.services import SEGREGATION_ITEM_FILTER_CHOICES
from core.reports.services import _reports_active_session
from core.reports.services import _reports_district_signature_grouped
from core.reports.services import _reports_district_signature_rows_from_dataset
from core.reports.services import _reports_district_signature_rows_from_session
from core.reports.services import _reports_district_signature_session_state
from core.reports.services import _reports_public_ack_column_options
from core.reports.services import _reports_public_ack_field_map_from_post
from core.reports.services import _reports_public_ack_field_map_with_defaults
from core.reports.services import _reports_public_ack_normalize_dataset
from core.reports.services import _reports_public_ack_session_state
from core.reports.services import _reports_public_ack_template_fields
from core.reports.services import _reports_public_signature_item_options
from core.reports.services import _reports_public_signature_rows_from_dataset
from core.reports.services import _reports_public_signature_rows_from_session
from core.reports.services import _reports_public_signature_session_state
from core.reports.services import _reports_public_signature_sort_rows
from core.reports.services import _reports_set_district_signature_state
from core.reports.services import _reports_set_public_ack_state
from core.reports.services import _reports_set_public_signature_state
from core.reports.services import _reports_set_shared_logo_state
from core.reports.services import _reports_set_simple_report_state
from core.reports.services import _reports_set_token_lookup_state
from core.reports.services import _reports_shared_logo_state
from core.reports.services import _reports_simple_report_session_state
from core.reports.services import _reports_token_lookup_choice_values
from core.reports.services import _reports_token_lookup_data_rows
from core.reports.services import _reports_token_lookup_default_state
from core.reports.services import _reports_token_lookup_filter_rows
from core.reports.services import _reports_token_lookup_filters_from_post
from core.reports.services import _reports_token_lookup_rows_from_session
from core.reports.services import _reports_token_lookup_session_state
from core.reports.services import _reports_waiting_hall_grouped_data
from core.reports.services import _reports_waiting_hall_session_state
from core.reports.services import _stage_distribution_build_file1
from core.reports.services import _stage_distribution_build_beneficiary_article_file
from core.reports.services import _stage_distribution_build_article_beneficiary_file
from core.reports.services import _stage_distribution_build_file6
from core.reports.services import _stage_distribution_file1_sheet_rows
from core.reports.services import _stage_distribution_file6_sheet_rows
from core.reports.services import _stage_distribution_master_sheet_rows
from core.reports.services import _stage_distribution_file6_quantity_label
from core.reports.services import _stage_distribution_filter_rows
from core.reports.services import _stage_distribution_normalize_dataset
from core.reports.services import generate_stage_distribution_file1_pdf
from core.reports.services import generate_stage_distribution_file6_pdf
from core.reports.services import generate_stage_distribution_grouped_pdf
from core.reports.services import generate_stage_distribution_xlsx
from core.reports.services import _segregation_build_file1
from core.reports.services import _segregation_build_file2
from core.reports.services import _segregation_build_file3
from core.reports.services import _segregation_file1_sheet_rows
from core.reports.services import _segregation_file2_sheet_rows
from core.reports.services import _segregation_file3_sheet_rows
from core.reports.services import _segregation_filter_rows
from core.reports.services import _segregation_master_sheet_rows
from core.reports.services import _segregation_normalize_dataset
from core.shared.csv_utils import _tabular_rows_from_upload
from core.shared.permissions import RoleRequiredMixin
from core.shared.phase2 import _phase2_unique_headers
from core.shared.phase2 import _phase2_parse_number
from core.shared.token_generation import _token_generation_saved_dataset


def _reports_multi_value_list(data, key: str) -> list[str]:
    values: list[str] = []
    if hasattr(data, "getlist"):
        raw_values = list(data.getlist(key))
    else:
        raw_values = [data.get(key)] if data.get(key) is not None else []
    for raw_value in raw_values:
        for part in str(raw_value or "").split(","):
            value = str(part or "").strip()
            if value:
                values.append(value)
    seen: set[str] = set()
    unique_values: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        unique_values.append(value)
    return unique_values


def _reports_normalize_segmentation_filter(values: list[str], *, allowed_values: set[str]) -> list[str]:
    cleaned = [value for value in values if value in allowed_values]
    if not cleaned:
        return []
    if "all" in cleaned:
        return []
    if len(set(cleaned)) >= len(allowed_values):
        return []
    return cleaned


def _reports_selection_summary(selected_values: list[str], choices: list[tuple[str, str]]) -> str:
    selected_set = {str(value or "").strip() for value in selected_values if str(value or "").strip()}
    if not selected_set:
        return "All"
    labels = [label for value, label in choices if value in selected_set]
    if not labels:
        return "All"
    if len(labels) <= 3:
        return ", ".join(labels)
    return f"{len(labels)} selected"


def _stage_distribution_file5_title(selected_beneficiary_types: list[str]) -> str:
    label_map = {
        models.RecipientTypeChoices.DISTRICT: "District",
        models.RecipientTypeChoices.PUBLIC: "Public",
        models.RecipientTypeChoices.INSTITUTIONS: "Institutions",
        models.RecipientTypeChoices.OTHERS: "Others",
    }
    cleaned = [str(value or "").strip() for value in list(selected_beneficiary_types or []) if str(value or "").strip()]
    if not cleaned:
        return "Article wise List - All beneficiaries"

    labels = []
    seen = set()
    for value in cleaned:
        label = label_map.get(value)
        if not label or label in seen:
            continue
        seen.add(label)
        labels.append(label)

    if not labels or len(labels) >= len(label_map):
        return "Article wise List - All beneficiaries"
    return f"Article wise List - {', '.join(labels)}"


def _stage_distribution_file1_title(selected_premise: str) -> str:
    premise = str(selected_premise or "").strip().lower() or "all"
    if premise == "waiting_hall":
        return "Beneficiary List - Waiting Hall"
    if premise == "masm_hall":
        return "Beneficiary List - MASM Hall"
    return "All Beneficiary List"


def _stage_distribution_file6_title(selected_premise: str) -> str:
    premise = str(selected_premise or "").strip().lower() or "all"
    if premise == "waiting_hall":
        return "Article List - Waiting Hall"
    if premise == "masm_hall":
        return "Article List - MASM Hall"
    return "Article List - All"


class ReportsView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    module_key = models.ModuleKeyChoices.REPORTS
    permission_action = "view"
    template_name = "reports/reports.html"

    REPORT_TABS = (
        {
            "key": "token-lookup",
            "label": "Token Lookup",
            "description": "Search and inspect token-generated rows by token number, application number, name, district, or item.",
        },
        {
            "key": "waiting-hall-acknowledgment",
            "label": "Waiting Hall Acknowledgment",
            "description": "District-wise article acknowledgment sheets for waiting hall collections.",
        },
        {
            "key": "public-acknowledgment-form",
            "label": "Public Acknowledgment Form",
            "description": "Public beneficiary acknowledgment forms filled from an uploaded PDF template.",
        },
        {
            "key": "public-signature",
            "label": "Signatures",
            "description": "Signature reports for public and district print sheets.",
        },
        {
            "key": "reports-home",
            "label": "Reports",
            "description": "Segregation and distribution report staging cards.",
        },
    )

    def post(self, request, *args, **kwargs):
        active_tab = (request.POST.get("tab") or self.REPORT_TABS[0]["key"]).strip()
        shared_logo = _reports_shared_logo_state(request)
        if (request.POST.get("action") or "").strip() == "upload_shared_logo":
            uploaded_logo = request.FILES.get("shared_logo")
            if uploaded_logo:
                _reports_set_shared_logo_state(request, uploaded_logo=uploaded_logo)
                messages.success(request, "Reports logo updated.")
            else:
                messages.error(request, "Choose a logo file to upload.")
            target = active_tab or self.REPORT_TABS[0]["key"]
            return HttpResponseRedirect(f"{reverse('ui:reports')}?tab={target}")
        action = (request.POST.get("action") or "").strip()
        if active_tab == "reports-home":
            reports_panel = str(request.POST.get("reports_panel") or request.GET.get("reports_panel") or "").strip().lower()
            segregation_state = _reports_simple_report_session_state(request, REPORTS_SEGREGATION_STATE_KEY)
            distribution_state = _reports_simple_report_session_state(request, REPORTS_DISTRIBUTION_STATE_KEY)
            stage_distribution_beneficiary_types = _reports_normalize_segmentation_filter(
                _reports_multi_value_list(request.GET if request.method == "GET" else request.POST, "stage_beneficiary_type"),
                allowed_values={choice[0] for choice in STAGE_DISTRIBUTION_BENEFICIARY_FILTER_CHOICES},
            )
            stage_distribution_item_types = _reports_normalize_segmentation_filter(
                _reports_multi_value_list(request.GET if request.method == "GET" else request.POST, "stage_item_type"),
                allowed_values={choice[0] for choice in STAGE_DISTRIBUTION_ITEM_FILTER_CHOICES},
            )
            stage_distribution_premise = str(
                (request.GET if request.method == "GET" else request.POST).get("stage_premise") or ""
            ).strip().lower() or "all"
            stage_distribution_seq_start = _phase2_parse_number(
                (request.GET if request.method == "GET" else request.POST).get("stage_seq_start")
            )
            stage_distribution_seq_end = _phase2_parse_number(
                (request.GET if request.method == "GET" else request.POST).get("stage_seq_end")
            )
            segregation_beneficiary_types = _reports_normalize_segmentation_filter(
                _reports_multi_value_list(request.POST, "segregation_beneficiary_type"),
                allowed_values={choice[0] for choice in SEGREGATION_BENEFICIARY_FILTER_CHOICES},
            )
            segregation_item_types = _reports_normalize_segmentation_filter(
                _reports_multi_value_list(request.POST, "segregation_item_type"),
                allowed_values={choice[0] for choice in SEGREGATION_ITEM_FILTER_CHOICES},
            )

            def _reports_home_redirect():
                params = {
                    "tab": "reports-home",
                }
                panel = reports_panel or ("stage-distribution" if action.startswith("preview_reports_stage_distribution") or action.startswith("download_reports_stage_distribution") or action in {"sync_reports_distribution", "upload_reports_distribution"} else "segregation")
                if panel:
                    params["reports_panel"] = panel
                if segregation_beneficiary_types:
                    params["seg_beneficiary_type"] = segregation_beneficiary_types
                if segregation_item_types:
                    params["seg_item_type"] = segregation_item_types
                if stage_distribution_beneficiary_types:
                    params["stage_beneficiary_type"] = stage_distribution_beneficiary_types
                if stage_distribution_item_types:
                    params["stage_item_type"] = stage_distribution_item_types
                if stage_distribution_premise != "all":
                    params["stage_premise"] = stage_distribution_premise
                if stage_distribution_seq_start:
                    params["stage_seq_start"] = stage_distribution_seq_start
                if stage_distribution_seq_end:
                    params["stage_seq_end"] = stage_distribution_seq_end
                return HttpResponseRedirect(f"{reverse('ui:reports')}?{urlencode(params, doseq=True)}")

            def _simple_report_sync(state, label: str):
                session = _reports_active_session()
                dataset = _token_generation_saved_dataset(session) if session else {"rows": [], "headers": []}
                rows = [dict(row) for row in dataset.get("rows") or []]
                state.update(
                    {
                        "loaded": True,
                        "synced_at": timezone.localtime().strftime("%d %b %Y at %H:%M"),
                        "source": "Synced from Token Generation",
                        "session_id": getattr(session, "pk", None),
                        "rows": rows,
                        "headers": _phase2_unique_headers(dataset.get("headers") or []),
                    }
                )
                _reports_set_simple_report_state(request, label, state)
                return len(rows)

            def _simple_report_upload(state, label: str, uploaded_file):
                source_headers, source_rows = _tabular_rows_from_upload(uploaded_file)
                if not source_headers:
                    return None, None
                state.update(
                    {
                        "loaded": True,
                        "synced_at": timezone.localtime().strftime("%d %b %Y at %H:%M"),
                        "source": uploaded_file.name,
                        "session_id": None,
                        "rows": [dict(row) for row in source_rows],
                        "headers": _phase2_unique_headers(source_headers),
                    }
                )
                _reports_set_simple_report_state(request, label, state)
                return len(source_rows), source_headers

            if action == "sync_reports_segregation":
                rows_count = _simple_report_sync(segregation_state, REPORTS_SEGREGATION_STATE_KEY)
                messages.success(request, f"Segregation synced. Rows: {rows_count}.")
                return _reports_home_redirect()

            if action == "upload_reports_segregation":
                uploaded_file = request.FILES.get("file")
                if not uploaded_file:
                    messages.error(request, "Choose a CSV or Excel file to upload.")
                    return _reports_home_redirect()
                rows_count, source_headers = _simple_report_upload(segregation_state, REPORTS_SEGREGATION_STATE_KEY, uploaded_file)
                if rows_count is None:
                    messages.error(request, "Uploaded file is empty.")
                    return _reports_home_redirect()
                messages.success(request, f"Uploaded {rows_count} segregation row(s).")
                return _reports_home_redirect()

            if action in {
                "download_reports_segregation_excel",
                "download_reports_segregation_file1_pdf",
                "download_reports_segregation_file2_pdf",
                "download_reports_segregation_file3_pdf",
                "preview_reports_segregation_file1_pdf",
                "preview_reports_segregation_file2_pdf",
                "preview_reports_segregation_file3_pdf",
            }:
                normalized_dataset = _segregation_normalize_dataset(segregation_state)
                filtered_rows = _segregation_filter_rows(
                    normalized_dataset.get("rows") or [],
                    beneficiary_types=segregation_beneficiary_types,
                    item_types=segregation_item_types,
                )
                file1_data = _segregation_build_file1(filtered_rows)
                file2_data = _segregation_build_file2(filtered_rows)
                file3_data = _segregation_build_file3(filtered_rows)
                if action == "download_reports_segregation_excel":
                    workbook_stream = services.generate_segregation_xlsx(
                        master_rows=_segregation_master_sheet_rows(normalized_dataset.get("rows") or []),
                        file1_rows=_segregation_file1_sheet_rows(file1_data["groups"]),
                        file2_rows=_segregation_file2_sheet_rows(file2_data["groups"]),
                        file3_rows=_segregation_file3_sheet_rows(file3_data["rows"]),
                    )
                    return FileResponse(
                        workbook_stream,
                        as_attachment=True,
                        filename=f"segregation_reports_{timezone.localtime().strftime('%d_%b_%Y_%H_%M')}.xlsx",
                    )
                if action == "download_reports_segregation_file1_pdf":
                    pdf_stream = services.generate_segregation_file1_pdf(file1_data["groups"])
                    return FileResponse(
                        pdf_stream,
                        as_attachment=True,
                        filename=f"segregation_file_1_{timezone.localtime().strftime('%d_%b_%Y_%H_%M')}.pdf",
                    )
                if action == "preview_reports_segregation_file1_pdf":
                    pdf_stream = services.generate_segregation_file1_pdf(file1_data["groups"])
                    return FileResponse(
                        pdf_stream,
                        as_attachment=False,
                        filename="segregation_file_1_preview.pdf",
                    )
                if action == "download_reports_segregation_file2_pdf":
                    pdf_stream = services.generate_segregation_file2_pdf(file2_data["groups"])
                    return FileResponse(
                        pdf_stream,
                        as_attachment=True,
                        filename=f"segregation_file_2_{timezone.localtime().strftime('%d_%b_%Y_%H_%M')}.pdf",
                    )
                if action == "preview_reports_segregation_file2_pdf":
                    pdf_stream = services.generate_segregation_file2_pdf(file2_data["groups"])
                    return FileResponse(
                        pdf_stream,
                        as_attachment=False,
                        filename="segregation_file_2_preview.pdf",
                    )
                if action == "preview_reports_segregation_file3_pdf":
                    pdf_stream = services.generate_segregation_file3_pdf(file3_data["rows"])
                    return FileResponse(
                        pdf_stream,
                        as_attachment=False,
                        filename="segregation_file_3_preview.pdf",
                    )
                pdf_stream = services.generate_segregation_file3_pdf(file3_data["rows"])
                return FileResponse(
                    pdf_stream,
                    as_attachment=True,
                    filename=f"segregation_file_3_{timezone.localtime().strftime('%d_%b_%Y_%H_%M')}.pdf",
                )

            if action == "sync_reports_distribution":
                rows_count = _simple_report_sync(distribution_state, REPORTS_DISTRIBUTION_STATE_KEY)
                messages.success(request, f"Distribution synced. Rows: {rows_count}.")
                return _reports_home_redirect()

            if action == "upload_reports_distribution":
                uploaded_file = request.FILES.get("file")
                if not uploaded_file:
                    messages.error(request, "Choose a CSV or Excel file to upload.")
                    return _reports_home_redirect()
                rows_count, source_headers = _simple_report_upload(distribution_state, REPORTS_DISTRIBUTION_STATE_KEY, uploaded_file)
                if rows_count is None:
                    messages.error(request, "Uploaded file is empty.")
                    return _reports_home_redirect()
                messages.success(request, f"Uploaded {rows_count} distribution row(s).")
                return _reports_home_redirect()

            if action in {
                "download_reports_stage_distribution_excel",
                "download_reports_stage_distribution_file1_pdf",
                "preview_reports_stage_distribution_file1_pdf",
                "download_reports_stage_distribution_file2_pdf",
                "preview_reports_stage_distribution_file2_pdf",
                "download_reports_stage_distribution_file3_pdf",
                "preview_reports_stage_distribution_file3_pdf",
                "download_reports_stage_distribution_file4_pdf",
                "preview_reports_stage_distribution_file4_pdf",
                "download_reports_stage_distribution_file5_pdf",
                "preview_reports_stage_distribution_file5_pdf",
                "download_reports_stage_distribution_file6_pdf",
                "preview_reports_stage_distribution_file6_pdf",
            }:
                normalized_dataset = _stage_distribution_normalize_dataset(distribution_state)
                file5_title = _stage_distribution_file5_title(stage_distribution_beneficiary_types)
                file6_title = _stage_distribution_file6_title(stage_distribution_premise)
                rows_with_three_filters = _stage_distribution_filter_rows(
                    normalized_dataset.get("rows") or [],
                    beneficiary_types=stage_distribution_beneficiary_types,
                    item_types=stage_distribution_item_types,
                    premise=stage_distribution_premise,
                )
                rows_for_file1 = _stage_distribution_filter_rows(
                    normalized_dataset.get("rows") or [],
                    beneficiary_types=stage_distribution_beneficiary_types,
                    item_types=stage_distribution_item_types,
                    premise=stage_distribution_premise,
                    seq_start=int(stage_distribution_seq_start or 0) or None,
                    seq_end=int(stage_distribution_seq_end or 0) or None,
                )
                rows_for_file2_4 = _stage_distribution_filter_rows(
                    normalized_dataset.get("rows") or [],
                    item_types=stage_distribution_item_types,
                    premise=stage_distribution_premise,
                )
                logo_bytes = base64.b64decode(shared_logo["logo_base64"]) if shared_logo.get("logo_base64") else None
                if logo_bytes:
                    logo_bytes, _ = services._optimized_report_logo(
                        logo_bytes,
                        shared_logo.get("logo_content_type") or "image/png",
                    )
                if action == "download_reports_stage_distribution_excel":
                    file1_data = _stage_distribution_build_file1(rows_for_file1, premise=stage_distribution_premise)
                    file2_data = _stage_distribution_build_beneficiary_article_file(
                        rows_for_file2_4,
                        beneficiary_types={models.RecipientTypeChoices.DISTRICT},
                        premise=stage_distribution_premise,
                    )
                    file3_data = _stage_distribution_build_beneficiary_article_file(
                        rows_for_file2_4,
                        beneficiary_types={models.RecipientTypeChoices.PUBLIC},
                        premise=stage_distribution_premise,
                    )
                    file4_data = _stage_distribution_build_beneficiary_article_file(
                        rows_for_file2_4,
                        beneficiary_types={models.RecipientTypeChoices.INSTITUTIONS},
                        premise=stage_distribution_premise,
                    )
                    file5_data = _stage_distribution_build_article_beneficiary_file(
                        rows_with_three_filters,
                        premise=stage_distribution_premise,
                    )
                    file6_data = _stage_distribution_build_file6(
                        rows_with_three_filters,
                        premise=stage_distribution_premise,
                    )
                    workbook_stream = generate_stage_distribution_xlsx(
                        master_rows=_stage_distribution_master_sheet_rows(normalized_dataset.get("rows") or []),
                        file1_rows=_stage_distribution_file1_sheet_rows(file1_data["rows"]),
                        file2_groups=file2_data["groups"],
                        file3_groups=file3_data["groups"],
                        file4_groups=file4_data["groups"],
                        file5_groups=file5_data["groups"],
                        file6_rows=_stage_distribution_file6_sheet_rows(
                            file6_data["rows"],
                            quantity_label=_stage_distribution_file6_quantity_label(stage_distribution_premise),
                            include_token_columns=bool(file6_data.get("include_token_columns")),
                        ),
                        file5_title=file5_title,
                    )
                    return FileResponse(
                        workbook_stream,
                        as_attachment=True,
                        filename=f"stage_distribution_reports_{timezone.localtime().strftime('%d_%b_%Y_%H_%M')}.xlsx",
                        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )
                if action in {"download_reports_stage_distribution_file1_pdf", "preview_reports_stage_distribution_file1_pdf"}:
                    file1_data = _stage_distribution_build_file1(rows_for_file1, premise=stage_distribution_premise)
                    file1_title = _stage_distribution_file1_title(stage_distribution_premise)
                    pdf_stream = generate_stage_distribution_file1_pdf(
                        file1_data["rows"],
                        seq_start=int(stage_distribution_seq_start or 0) or None,
                        seq_end=int(stage_distribution_seq_end or 0) or None,
                        header_title_text=file1_title,
                        custom_logo=logo_bytes,
                    )
                    file_name_base = "stage_distribution_file_1"
                elif action in {"download_reports_stage_distribution_file2_pdf", "preview_reports_stage_distribution_file2_pdf"}:
                    file2_data = _stage_distribution_build_beneficiary_article_file(
                        rows_for_file2_4,
                        beneficiary_types={models.RecipientTypeChoices.DISTRICT},
                        premise=stage_distribution_premise,
                    )
                    pdf_stream = generate_stage_distribution_grouped_pdf(
                        file2_data["groups"],
                        section_title="District-wise Article List",
                        item_value_key="article_name",
                        name_column_label="District Name",
                        header_title_text="District-wise Article List",
                        include_token_columns=True,
                        custom_logo=logo_bytes,
                    )
                    file_name_base = "stage_distribution_file_2"
                elif action in {"download_reports_stage_distribution_file3_pdf", "preview_reports_stage_distribution_file3_pdf"}:
                    file3_data = _stage_distribution_build_beneficiary_article_file(
                        rows_for_file2_4,
                        beneficiary_types={models.RecipientTypeChoices.PUBLIC},
                        premise=stage_distribution_premise,
                    )
                    pdf_stream = generate_stage_distribution_grouped_pdf(
                        file3_data["groups"],
                        section_title="Public-wise Article List",
                        item_value_key="article_name",
                        name_column_label="Public Name",
                        header_title_text="Public-wise Article List",
                        include_token_columns=True,
                        custom_logo=logo_bytes,
                    )
                    file_name_base = "stage_distribution_file_3"
                elif action in {"download_reports_stage_distribution_file4_pdf", "preview_reports_stage_distribution_file4_pdf"}:
                    file4_data = _stage_distribution_build_beneficiary_article_file(
                        rows_for_file2_4,
                        beneficiary_types={models.RecipientTypeChoices.INSTITUTIONS},
                        premise=stage_distribution_premise,
                    )
                    pdf_stream = generate_stage_distribution_grouped_pdf(
                        file4_data["groups"],
                        section_title="Institution-wise Article List",
                        item_value_key="article_name",
                        name_column_label="Institution Name",
                        header_title_text="Institution-wise Article List",
                        include_token_columns=True,
                        custom_logo=logo_bytes,
                    )
                    file_name_base = "stage_distribution_file_4"
                else:
                    if action in {"download_reports_stage_distribution_file5_pdf", "preview_reports_stage_distribution_file5_pdf"}:
                        file5_data = _stage_distribution_build_article_beneficiary_file(
                            rows_with_three_filters,
                            premise=stage_distribution_premise,
                        )
                        pdf_stream = generate_stage_distribution_grouped_pdf(
                            file5_data["groups"],
                            section_title=file5_title,
                            item_value_key="beneficiary_name",
                            name_column_label="Article Name",
                            header_title_text=file5_title,
                            include_token_columns=True,
                            custom_logo=logo_bytes,
                        )
                        file_name_base = "stage_distribution_file_5"
                    else:
                        file6_data = _stage_distribution_build_file6(
                            rows_with_three_filters,
                            premise=stage_distribution_premise,
                        )
                        pdf_stream = generate_stage_distribution_file6_pdf(
                            file6_data["rows"],
                            quantity_label=_stage_distribution_file6_quantity_label(stage_distribution_premise),
                            include_token_columns=bool(file6_data.get("include_token_columns")),
                            header_title_text=file6_title,
                            custom_logo=logo_bytes,
                        )
                        file_name_base = "stage_distribution_file_6"
                return FileResponse(
                    pdf_stream,
                    as_attachment=action.startswith("download_reports_stage_distribution"),
                    filename=(
                        f"{file_name_base}_{timezone.localtime().strftime('%d_%b_%Y_%H_%M')}.pdf"
                        if action.startswith("download_reports_stage_distribution")
                        else f"{file_name_base}_preview.pdf"
                    ),
                )

            return _reports_home_redirect()

        if active_tab == "token-lookup":
            state = _reports_token_lookup_session_state(request)
            if action == "sync_token_lookup":
                session = _reports_active_session()
                dataset = _token_generation_saved_dataset(session) if session else {"rows": [], "headers": []}
                rows = _reports_token_lookup_rows_from_session(session) if session else []
                state.update(
                    {
                        "loaded": True,
                        "synced_at": timezone.localtime().strftime("%d %b %Y at %H:%M"),
                        "source": "Synced from Token Generation",
                        "session_id": getattr(session, "pk", None),
                        "rows": rows,
                        "headers": _phase2_unique_headers(dataset.get("headers") or []),
                    }
                )
                _reports_set_token_lookup_state(request, state)
                messages.success(request, f"Token Lookup synced. Rows: {len(rows)}.")
                return HttpResponseRedirect(f"{reverse('ui:reports')}?tab=token-lookup")

            if action == "upload_token_lookup":
                uploaded_file = request.FILES.get("file")
                if not uploaded_file:
                    messages.error(request, "Choose a CSV or Excel file to upload.")
                    return HttpResponseRedirect(f"{reverse('ui:reports')}?tab=token-lookup")
                source_headers, source_rows = _tabular_rows_from_upload(uploaded_file)
                if not source_headers:
                    messages.error(request, "Uploaded file is empty.")
                    return HttpResponseRedirect(f"{reverse('ui:reports')}?tab=token-lookup")
                rows = _reports_token_lookup_data_rows(source_rows)
                state.update(
                    {
                        "loaded": True,
                        "synced_at": timezone.localtime().strftime("%d %b %Y at %H:%M"),
                        "source": uploaded_file.name,
                        "session_id": None,
                        "rows": rows,
                        "headers": _phase2_unique_headers(source_headers),
                    }
                )
                _reports_set_token_lookup_state(request, state)
                messages.success(request, f"Uploaded {len(rows)} token lookup row(s).")
                return HttpResponseRedirect(f"{reverse('ui:reports')}?tab=token-lookup")

            if action == "clear_token_lookup_filters":
                state["filters"] = _reports_token_lookup_default_state()["filters"]
                _reports_set_token_lookup_state(request, state)
                return HttpResponseRedirect(f"{reverse('ui:reports')}?tab=token-lookup")

            if action == "search_token_lookup":
                if not state.get("loaded"):
                    messages.warning(request, "Sync Data or Upload a file first before searching tokens.")
                    return HttpResponseRedirect(f"{reverse('ui:reports')}?tab=token-lookup")
                state["filters"] = _reports_token_lookup_filters_from_post(request.POST)
                _reports_set_token_lookup_state(request, state)
                return HttpResponseRedirect(f"{reverse('ui:reports')}?tab=token-lookup")

            return HttpResponseRedirect(f"{reverse('ui:reports')}?tab=token-lookup")

        if active_tab == "public-acknowledgment-form":
            state = _reports_public_ack_session_state(request)
            if action == "sync_public_ack":
                session = _reports_active_session()
                dataset = _token_generation_saved_dataset(session) if session else {"rows": [], "headers": []}
                rows = _reports_public_ack_normalize_dataset(dataset.get("rows") or [])
                headers = _phase2_unique_headers(dataset.get("headers") or [])
                template_fields = list(state.get("template_fields") or [])
                state.update(
                    {
                        "loaded": True,
                        "synced_at": timezone.localtime().strftime("%d %b %Y at %H:%M"),
                        "source": "Synced from Token Generation",
                        "session_id": getattr(session, "pk", None),
                        "rows": rows,
                        "headers": headers,
                        "field_map": _reports_public_ack_field_map_with_defaults(
                            headers,
                            template_fields,
                            state.get("field_map"),
                        ),
                    }
                )
                _reports_set_public_ack_state(request, state)
                messages.success(request, f"Public Acknowledgment Form synced. Rows: {len(rows)}.")
                return HttpResponseRedirect(f"{reverse('ui:reports')}?tab=public-acknowledgment-form")

            if action == "upload_public_ack_data":
                uploaded_file = request.FILES.get("file")
                if not uploaded_file:
                    messages.error(request, "Choose a CSV or Excel file to upload.")
                    return HttpResponseRedirect(f"{reverse('ui:reports')}?tab=public-acknowledgment-form")
                source_headers, source_rows = _tabular_rows_from_upload(uploaded_file)
                if not source_headers:
                    messages.error(request, "Uploaded file is empty.")
                    return HttpResponseRedirect(f"{reverse('ui:reports')}?tab=public-acknowledgment-form")
                rows = _reports_public_ack_normalize_dataset(source_rows)
                template_fields = list(state.get("template_fields") or [])
                state.update(
                    {
                        "loaded": True,
                        "synced_at": timezone.localtime().strftime("%d %b %Y at %H:%M"),
                        "source": uploaded_file.name,
                        "session_id": None,
                        "rows": rows,
                        "headers": _phase2_unique_headers(source_headers),
                        "field_map": _reports_public_ack_field_map_with_defaults(
                            source_headers,
                            template_fields,
                            state.get("field_map"),
                        ),
                    }
                )
                _reports_set_public_ack_state(request, state)
                messages.success(request, f"Uploaded {len(rows)} public acknowledgment row(s).")
                return HttpResponseRedirect(f"{reverse('ui:reports')}?tab=public-acknowledgment-form")

            if action == "upload_public_ack_template":
                uploaded_template = request.FILES.get("template_pdf") or request.FILES.get("template")
                if not uploaded_template:
                    messages.error(request, "Choose a PDF template to upload.")
                    return HttpResponseRedirect(f"{reverse('ui:reports')}?tab=public-acknowledgment-form")
                template_bytes = uploaded_template.read()
                template_fields = _reports_public_ack_template_fields(template_bytes)
                if not template_fields:
                    messages.error(request, "No fillable fields were found in the uploaded PDF template.")
                    return HttpResponseRedirect(f"{reverse('ui:reports')}?tab=public-acknowledgment-form")
                state.update(
                    {
                        "template_name": uploaded_template.name,
                        "template_base64": base64.b64encode(template_bytes).decode("ascii"),
                        "template_content_type": "application/pdf",
                        "template_fields": template_fields,
                        "field_map": _reports_public_ack_field_map_with_defaults(
                            state.get("headers") or [],
                            template_fields,
                            state.get("field_map"),
                        ),
                    }
                )
                _reports_set_public_ack_state(request, state)
                messages.success(request, f"Template loaded with {len(template_fields)} fillable field(s).")
                return HttpResponseRedirect(f"{reverse('ui:reports')}?tab=public-acknowledgment-form")

            if action in {"download_public_ack", "preview_public_ack"}:
                if not state.get("loaded"):
                    messages.error(request, "Sync Data or Upload a file first before downloading this report.")
                    return HttpResponseRedirect(f"{reverse('ui:reports')}?tab=public-acknowledgment-form")
                if not state.get("template_base64"):
                    messages.error(request, "Upload a PDF template first.")
                    return HttpResponseRedirect(f"{reverse('ui:reports')}?tab=public-acknowledgment-form")
                rows = list(state.get("rows") or [])
                if not rows:
                    messages.error(request, "No public acknowledgment rows are available for the current selection.")
                    return HttpResponseRedirect(f"{reverse('ui:reports')}?tab=public-acknowledgment-form")
                template_fields = list(state.get("template_fields") or [])
                submitted_map = _reports_public_ack_field_map_from_post(request.POST, template_fields)
                field_map = _reports_public_ack_field_map_with_defaults(
                    state.get("headers") or [],
                    template_fields,
                    {**state.get("field_map", {}), **submitted_map},
                )
                state["field_map"] = field_map
                _reports_set_public_ack_state(request, state)
                template_bytes = base64.b64decode(state.get("template_base64") or "")
                if not template_bytes:
                    messages.error(request, "Upload a valid PDF template first.")
                    return HttpResponseRedirect(f"{reverse('ui:reports')}?tab=public-acknowledgment-form")
                field_name_map = {
                    field["field_name"]: field_map.get(field["field_key"], "")
                    for field in template_fields
                    if field_map.get(field["field_key"], "")
                }
                if not field_name_map:
                    messages.error(request, "Map at least one template field before downloading.")
                    return HttpResponseRedirect(f"{reverse('ui:reports')}?tab=public-acknowledgment-form")
                buffer = services.generate_public_acknowledgment_pdf(
                    template_bytes,
                    rows,
                    field_name_map,
                )
                filename = f"public_acknowledgment_{timezone.localtime().strftime('%d_%b_%y_%H_%M')}.pdf"
                response = HttpResponse(buffer.getvalue(), content_type="application/pdf")
                disposition = "inline" if action == "preview_public_ack" else "attachment"
                response["Content-Disposition"] = f'{disposition}; filename="{filename}"'
                return response

            return HttpResponseRedirect(f"{reverse('ui:reports')}?tab=public-acknowledgment-form")

        if active_tab == "public-signature":
            state = _reports_public_signature_session_state(request)
            district_state = _reports_district_signature_session_state(request)
            if action == "sync_public_signature":
                session = _reports_active_session()
                dataset = _token_generation_saved_dataset(session) if session else {"rows": [], "headers": []}
                rows = _reports_public_signature_rows_from_session(session) if session else []
                state.update(
                    {
                        "loaded": True,
                        "synced_at": timezone.localtime().strftime("%d %b %Y at %H:%M"),
                        "source": "Synced from Token Generation",
                        "session_id": getattr(session, "pk", None),
                        "rows": rows,
                        "headers": _phase2_unique_headers(dataset.get("headers") or []),
                        "selected_items": [],
                        "sort_modes": [],
                    }
                )
                _reports_set_public_signature_state(request, state)
                messages.success(request, f"Public Signature synced. Rows: {len(rows)}.")
                return HttpResponseRedirect(f"{reverse('ui:reports')}?tab=public-signature")

            if action == "upload_public_signature":
                uploaded_file = request.FILES.get("file")
                if not uploaded_file:
                    messages.error(request, "Choose a CSV or Excel file to upload.")
                    return HttpResponseRedirect(f"{reverse('ui:reports')}?tab=public-signature")
                source_headers, source_rows = _tabular_rows_from_upload(uploaded_file)
                if not source_headers:
                    messages.error(request, "Uploaded file is empty.")
                    return HttpResponseRedirect(f"{reverse('ui:reports')}?tab=public-signature")
                rows = _reports_public_signature_rows_from_dataset(source_rows)
                state.update(
                    {
                        "loaded": True,
                        "synced_at": timezone.localtime().strftime("%d %b %Y at %H:%M"),
                        "source": uploaded_file.name,
                        "session_id": None,
                        "rows": rows,
                        "headers": _phase2_unique_headers(source_headers),
                        "selected_items": [],
                        "sort_modes": [],
                    }
                )
                _reports_set_public_signature_state(request, state)
                messages.success(request, f"Uploaded {len(rows)} public signature row(s).")
                return HttpResponseRedirect(f"{reverse('ui:reports')}?tab=public-signature")

            if action == "set_public_signature_sort":
                ordered_modes = [
                    str(mode or "").strip()
                    for mode in (request.POST.get("sort_modes_order") or "").split(",")
                    if str(mode or "").strip() in {"application_number", "item_name", "token_number"}
                ]
                requested_modes = []
                for mode in ordered_modes:
                    if mode not in requested_modes:
                        requested_modes.append(mode)
                if not requested_modes:
                    requested_modes = [
                        str(mode or "").strip()
                        for mode in request.POST.getlist("sort_modes")
                        if str(mode or "").strip() in {"application_number", "item_name", "token_number"} and str(mode or "").strip() not in requested_modes
                    ]
                state["sort_modes"] = requested_modes
                _reports_set_public_signature_state(request, state)
                messages.success(request, "Public Signature sort updated.")
                return HttpResponseRedirect(f"{reverse('ui:reports')}?tab=public-signature")

            if action in {"download_public_signature", "preview_public_signature"}:
                if not state.get("loaded"):
                    messages.error(request, "Sync Data or Upload a file first before downloading this report.")
                    return HttpResponseRedirect(f"{reverse('ui:reports')}?tab=public-signature")
                download_format = "pdf" if action == "preview_public_signature" else (request.POST.get("download_format") or "pdf").strip().lower()
                selected_items = [
                    str(item or "").strip()
                    for item in request.POST.getlist("selected_items")
                    if str(item or "").strip()
                ]
                state["selected_items"] = selected_items
                _reports_set_public_signature_state(request, state)
                if not selected_items:
                    messages.error(request, "Select at least one public item before downloading.")
                    return HttpResponseRedirect(f"{reverse('ui:reports')}?tab=public-signature")
                selected_rows = [
                    row for row in list(state.get("rows") or [])
                    if str(row.get("item_name") or "").strip() in set(selected_items)
                ]
                if not selected_rows:
                    messages.error(request, "No public rows are available for the selected items.")
                    return HttpResponseRedirect(f"{reverse('ui:reports')}?tab=public-signature")
                selected_rows = _reports_public_signature_sort_rows(selected_rows, state.get("sort_modes"))
                stamp = timezone.localtime().strftime('%d_%b_%y_%H_%M')
                if download_format == "xlsx":
                    buffer = services.generate_public_signature_xlsx(selected_rows)
                    filename = f"public_signature_{stamp}.xlsx"
                    content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                else:
                    buffer = services.generate_public_signature_pdf(selected_rows)
                    filename = f"public_signature_{stamp}.pdf"
                    content_type = "application/pdf"
                response = HttpResponse(buffer.getvalue(), content_type=content_type)
                disposition = "inline" if action == "preview_public_signature" and content_type == "application/pdf" else "attachment"
                response["Content-Disposition"] = f'{disposition}; filename="{filename}"'
                return response

            if action == "sync_district_signature":
                session = _reports_active_session()
                dataset = _token_generation_saved_dataset(session) if session else {"rows": [], "headers": []}
                rows = _reports_district_signature_rows_from_session(session) if session else []
                district_state.update(
                    {
                        "loaded": True,
                        "synced_at": timezone.localtime().strftime("%d %b %Y at %H:%M"),
                        "source": "Synced from Token Generation",
                        "session_id": getattr(session, "pk", None),
                        "rows": rows,
                        "headers": _phase2_unique_headers(dataset.get("headers") or []),
                    }
                )
                _reports_set_district_signature_state(request, district_state)
                messages.success(request, f"District Signature synced. Rows: {len(rows)}.")
                return HttpResponseRedirect(f"{reverse('ui:reports')}?tab=public-signature")

            if action == "upload_district_signature":
                uploaded_file = request.FILES.get("file")
                if not uploaded_file:
                    messages.error(request, "Choose a CSV or Excel file to upload.")
                    return HttpResponseRedirect(f"{reverse('ui:reports')}?tab=public-signature")
                source_headers, source_rows = _tabular_rows_from_upload(uploaded_file)
                if not source_headers:
                    messages.error(request, "Uploaded file is empty.")
                    return HttpResponseRedirect(f"{reverse('ui:reports')}?tab=public-signature")
                rows = _reports_district_signature_rows_from_dataset(source_rows)
                district_state.update(
                    {
                        "loaded": True,
                        "synced_at": timezone.localtime().strftime("%d %b %Y at %H:%M"),
                        "source": uploaded_file.name,
                        "session_id": None,
                        "rows": rows,
                        "headers": _phase2_unique_headers(source_headers),
                    }
                )
                _reports_set_district_signature_state(request, district_state)
                messages.success(request, f"Uploaded {len(rows)} district signature row(s).")
                return HttpResponseRedirect(f"{reverse('ui:reports')}?tab=public-signature")

            if action in {"download_district_signature", "preview_district_signature"}:
                if not district_state.get("loaded"):
                    messages.error(request, "Sync Data or Upload a file first before downloading this report.")
                    return HttpResponseRedirect(f"{reverse('ui:reports')}?tab=public-signature")
                download_format = "pdf" if action == "preview_district_signature" else (request.POST.get("download_format") or "pdf").strip().lower()
                grouped = _reports_district_signature_grouped(district_state.get("rows") or [])
                if not grouped.get("districts"):
                    messages.error(request, "No district rows are available for this report.")
                    return HttpResponseRedirect(f"{reverse('ui:reports')}?tab=public-signature")
                stamp = timezone.localtime().strftime('%d_%b_%y_%H_%M')
                logo_bytes = base64.b64decode(shared_logo["logo_base64"]) if shared_logo.get("logo_base64") else None
                if logo_bytes:
                    logo_bytes, logo_mime = services._optimized_report_logo(
                        logo_bytes,
                        shared_logo.get("logo_content_type") or "image/png",
                        max_width_px=180,
                        max_height_px=180,
                    )
                else:
                    logo_mime = shared_logo.get("logo_content_type") or "image/png"
                if download_format == "xlsx":
                    buffer = services.generate_district_signature_xlsx(
                        grouped.get("districts") or [],
                        custom_logo=logo_bytes,
                        custom_logo_mime_type=logo_mime,
                    )
                    filename = f"district_signature_{stamp}.xlsx"
                    content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                else:
                    buffer = services.generate_district_signature_pdf(
                        grouped.get("districts") or [],
                        custom_logo=logo_bytes,
                    )
                    filename = f"district_signature_{stamp}.pdf"
                    content_type = "application/pdf"
                response = HttpResponse(buffer.getvalue(), content_type=content_type)
                disposition = "inline" if action == "preview_district_signature" and content_type == "application/pdf" else "attachment"
                response["Content-Disposition"] = f'{disposition}; filename="{filename}"'
                return response

            return HttpResponseRedirect(f"{reverse('ui:reports')}?tab=public-signature")

        if active_tab != "waiting-hall-acknowledgment":
            return HttpResponseRedirect(f"{reverse('ui:reports')}?tab={active_tab}")

        state = _reports_waiting_hall_session_state(request)
        shared_logo = _reports_shared_logo_state(request)

        if action == "sync_waiting_hall":
            session = _reports_active_session()
            dataset = _token_generation_saved_dataset(session) if session else {"rows": [], "headers": []}
            rows = [dict(row) for row in dataset.get("rows") or []]
            grouped = _reports_waiting_hall_grouped_data(rows, ignored_keys=[])
            state.update(
                {
                    "loaded": True,
                    "synced_at": timezone.localtime().strftime("%d %b %Y at %H:%M"),
                    "source": "Synced from Token Generation",
                    "session_id": getattr(session, "pk", None),
                    "ignored_keys": [],
                    "rows": rows,
                    "headers": list(dataset.get("headers") or []),
                    "beneficiary_type_filter": "",
                    "item_type_filter": models.ItemTypeChoices.AID,
                }
            )
            request.session[REPORTS_WAITING_HALL_STATE_KEY] = state
            request.session.modified = True
            messages.success(request, f"Waiting Hall Acknowledgment synced. Districts: {grouped['district_count']}, items: {grouped['item_count']}.")
            return HttpResponseRedirect(f"{reverse('ui:reports')}?tab=waiting-hall-acknowledgment")

        if action == "upload_waiting_hall":
            uploaded_file = request.FILES.get("file")
            if not uploaded_file:
                messages.error(request, "Choose a CSV or Excel file to upload.")
                return HttpResponseRedirect(f"{reverse('ui:reports')}?tab=waiting-hall-acknowledgment")
            source_headers, source_rows = _tabular_rows_from_upload(uploaded_file)
            if not source_headers:
                messages.error(request, "Uploaded file is empty.")
                return HttpResponseRedirect(f"{reverse('ui:reports')}?tab=waiting-hall-acknowledgment")
            grouped = _reports_waiting_hall_grouped_data(source_rows, ignored_keys=[])
            state.update(
                {
                    "loaded": True,
                    "synced_at": timezone.localtime().strftime("%d %b %Y at %H:%M"),
                    "source": uploaded_file.name,
                    "session_id": None,
                    "ignored_keys": [],
                    "rows": source_rows,
                    "headers": source_headers,
                    "beneficiary_type_filter": "",
                    "item_type_filter": models.ItemTypeChoices.AID,
                }
            )
            request.session[REPORTS_WAITING_HALL_STATE_KEY] = state
            request.session.modified = True
            messages.success(request, f"Uploaded {len(source_rows)} row(s) into Waiting Hall Acknowledgment.")
            return HttpResponseRedirect(f"{reverse('ui:reports')}?tab=waiting-hall-acknowledgment")

        selected_ignored = request.POST.getlist("ignored_keys")
        state["ignored_keys"] = selected_ignored
        if "beneficiary_type_filter" in request.POST:
            state["beneficiary_type_filter"] = str(request.POST.get("beneficiary_type_filter") or "").strip()
        else:
            state["beneficiary_type_filter"] = str(state.get("beneficiary_type_filter") or "").strip()
        if "item_type_filter" in request.POST:
            state["item_type_filter"] = str(request.POST.get("item_type_filter") or "").strip()
        else:
            state["item_type_filter"] = str(state.get("item_type_filter") or models.ItemTypeChoices.AID).strip()

        request.session[REPORTS_WAITING_HALL_STATE_KEY] = state
        request.session.modified = True

        if action == "save_waiting_hall":
            messages.success(request, "Waiting Hall Acknowledgment selections saved.")
            return HttpResponseRedirect(f"{reverse('ui:reports')}?tab=waiting-hall-acknowledgment")

        if action in {"download_waiting_hall", "preview_waiting_hall"}:
            if not state.get("loaded"):
                messages.error(request, "Sync Data or Upload a file first before downloading this report.")
                return HttpResponseRedirect(f"{reverse('ui:reports')}?tab=waiting-hall-acknowledgment")
            grouped = _reports_waiting_hall_grouped_data(
                state.get("rows") or [],
                ignored_keys=state.get("ignored_keys"),
                beneficiary_type_filter=state.get("beneficiary_type_filter"),
                item_type_filter=state.get("item_type_filter"),
            )
            report_groups = [group for group in grouped["districts"] if group["items"]]
            if not report_groups:
                messages.error(request, "No printable waiting hall rows are available for the current filter. Check whether all rows under this filter were ignored.")
                return HttpResponseRedirect(f"{reverse('ui:reports')}?tab=waiting-hall-acknowledgment")
            event_year = timezone.localdate().year
            event_date = date(event_year, 3, 3)
            age_label = services._ordinal(max(event_date.year - 1940, 1))
            logo_bytes = base64.b64decode(shared_logo["logo_base64"]) if shared_logo.get("logo_base64") else None
            output_format = "pdf" if action == "preview_waiting_hall" else (request.POST.get("download_format") or "pdf").strip().lower()
            if output_format == "pdf":
                buffer = services.generate_waiting_hall_acknowledgment_pdf(
                    report_groups,
                    event_age_label=age_label,
                    event_date=event_date,
                    custom_logo=logo_bytes,
                )
                filename = f"district_waiting_hall_acknowledgment_{timezone.localtime().strftime('%d_%b_%y_%H_%M')}.pdf"
                response = HttpResponse(buffer.getvalue(), content_type="application/pdf")
                disposition = "inline" if action == "preview_waiting_hall" else "attachment"
                response["Content-Disposition"] = f'{disposition}; filename="{filename}"'
                return response
            document_bytes = services.generate_waiting_hall_acknowledgment_doc(
                report_groups,
                event_age_label=age_label,
                event_date=event_date,
                custom_logo=logo_bytes,
                custom_logo_mime_type=shared_logo.get("logo_content_type") or "image/png",
            )
            filename = f"district_waiting_hall_acknowledgment_{timezone.localtime().strftime('%d_%b_%y_%H_%M')}.docx"
            response = HttpResponse(
                document_bytes,
                content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
            response["Content-Disposition"] = f'attachment; filename="{filename}"'
            return response

        return HttpResponseRedirect(f"{reverse('ui:reports')}?tab=waiting-hall-acknowledgment")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        active_tab = (self.request.GET.get("tab") or self.REPORT_TABS[0]["key"]).strip()
        tab_keys = {tab["key"] for tab in self.REPORT_TABS}
        if active_tab not in tab_keys:
            active_tab = self.REPORT_TABS[0]["key"]
        active_tab_meta = next(tab for tab in self.REPORT_TABS if tab["key"] == active_tab)
        token_lookup_state = _reports_token_lookup_session_state(self.request)
        token_lookup_rows = list(token_lookup_state.get("rows") or [])
        token_lookup_filtered_rows = _reports_token_lookup_filter_rows(token_lookup_rows, token_lookup_state.get("filters"))
        token_lookup_item_options = _reports_token_lookup_choice_values(token_lookup_rows, "item_name")
        token_lookup_item_type_options = _reports_token_lookup_choice_values(token_lookup_rows, "item_type")
        public_signature_state = _reports_public_signature_session_state(self.request)
        public_signature_rows = list(public_signature_state.get("rows") or [])
        public_signature_item_options = _reports_public_signature_item_options(public_signature_rows)
        district_signature_state = _reports_district_signature_session_state(self.request)
        district_signature_rows = list(district_signature_state.get("rows") or [])
        district_signature_grouped = _reports_district_signature_grouped(district_signature_rows) if district_signature_state.get("loaded") else {
            "districts": [],
            "district_count": 0,
            "item_count": 0,
            "total_quantity": 0,
            "total_token_quantity": 0,
        }
        waiting_hall_state = _reports_waiting_hall_session_state(self.request)
        waiting_hall_grouped = _reports_waiting_hall_grouped_data(
            waiting_hall_state.get("rows") or [],
            ignored_keys=waiting_hall_state.get("ignored_keys"),
        ) if waiting_hall_state.get("loaded") else {
            "districts": [],
            "district_count": 0,
            "item_count": 0,
            "total_quantity": 0,
            "available_keys": [],
        }
        public_ack_state = _reports_public_ack_session_state(self.request)
        public_ack_template_fields = list(public_ack_state.get("template_fields") or [])
        public_ack_rows = list(public_ack_state.get("rows") or [])
        segregation_state = _reports_simple_report_session_state(self.request, REPORTS_SEGREGATION_STATE_KEY)
        segregation_rows = list(segregation_state.get("rows") or [])
        segregation_beneficiary_types = _reports_normalize_segmentation_filter(
            _reports_multi_value_list(self.request.GET, "seg_beneficiary_type"),
            allowed_values={choice[0] for choice in SEGREGATION_BENEFICIARY_FILTER_CHOICES},
        )
        segregation_item_types = _reports_normalize_segmentation_filter(
            _reports_multi_value_list(self.request.GET, "seg_item_type"),
            allowed_values={choice[0] for choice in SEGREGATION_ITEM_FILTER_CHOICES},
        )
        segregation_dataset = _segregation_normalize_dataset(segregation_state)
        segregation_filtered_rows = _segregation_filter_rows(
            segregation_dataset.get("rows") or [],
            beneficiary_types=segregation_beneficiary_types,
            item_types=segregation_item_types,
        )
        segregation_file1 = _segregation_build_file1(segregation_filtered_rows)
        segregation_file2 = _segregation_build_file2(segregation_filtered_rows)
        segregation_file3 = _segregation_build_file3(segregation_filtered_rows)
        distribution_state = _reports_simple_report_session_state(self.request, REPORTS_DISTRIBUTION_STATE_KEY)
        distribution_rows = list(distribution_state.get("rows") or [])
        stage_distribution_beneficiary_types = _reports_normalize_segmentation_filter(
            _reports_multi_value_list(self.request.GET, "stage_beneficiary_type"),
            allowed_values={choice[0] for choice in STAGE_DISTRIBUTION_BENEFICIARY_FILTER_CHOICES},
        )
        stage_distribution_item_types = _reports_normalize_segmentation_filter(
            _reports_multi_value_list(self.request.GET, "stage_item_type"),
            allowed_values={choice[0] for choice in STAGE_DISTRIBUTION_ITEM_FILTER_CHOICES},
        )
        stage_distribution_premise = str(self.request.GET.get("stage_premise") or "").strip().lower() or "all"
        stage_distribution_seq_start = _phase2_parse_number(self.request.GET.get("stage_seq_start"))
        stage_distribution_seq_end = _phase2_parse_number(self.request.GET.get("stage_seq_end"))
        stage_distribution_dataset = _stage_distribution_normalize_dataset(distribution_state)
        stage_distribution_filtered_rows = _stage_distribution_filter_rows(
            stage_distribution_dataset.get("rows") or [],
            beneficiary_types=stage_distribution_beneficiary_types,
            item_types=stage_distribution_item_types,
            premise=stage_distribution_premise,
        )
        stage_distribution_file2_4_rows = _stage_distribution_filter_rows(
            stage_distribution_dataset.get("rows") or [],
            item_types=stage_distribution_item_types,
            premise=stage_distribution_premise,
        )
        stage_distribution_file1 = _stage_distribution_build_file1(
            stage_distribution_filtered_rows,
            premise=stage_distribution_premise,
        )
        stage_distribution_file2 = _stage_distribution_build_beneficiary_article_file(
            stage_distribution_file2_4_rows,
            beneficiary_types={models.RecipientTypeChoices.DISTRICT},
            premise=stage_distribution_premise,
        )
        stage_distribution_file3 = _stage_distribution_build_beneficiary_article_file(
            stage_distribution_file2_4_rows,
            beneficiary_types={models.RecipientTypeChoices.PUBLIC},
            premise=stage_distribution_premise,
        )
        stage_distribution_file4 = _stage_distribution_build_beneficiary_article_file(
            stage_distribution_file2_4_rows,
            beneficiary_types={models.RecipientTypeChoices.INSTITUTIONS},
            premise=stage_distribution_premise,
        )
        stage_distribution_file5 = _stage_distribution_build_article_beneficiary_file(
            stage_distribution_filtered_rows,
            premise=stage_distribution_premise,
        )
        stage_distribution_file6 = _stage_distribution_build_file6(
            stage_distribution_filtered_rows,
            premise=stage_distribution_premise,
        )
        stage_distribution_file1_title = _stage_distribution_file1_title(stage_distribution_premise)
        stage_distribution_file5_title = _stage_distribution_file5_title(stage_distribution_beneficiary_types)
        stage_distribution_file6_title = _stage_distribution_file6_title(stage_distribution_premise)
        reports_home_open_panel = str(self.request.GET.get("reports_panel") or "").strip().lower()
        if reports_home_open_panel not in {"segregation", "stage-distribution"}:
            reports_home_open_panel = ""
        context.update(
            {
                "page_title": "Reports",
                "report_tabs": self.REPORT_TABS,
                "active_report_tab": active_tab,
                "active_report_tab_meta": active_tab_meta,
                "token_lookup_state": token_lookup_state,
                "token_lookup_row_count": len(token_lookup_rows),
                "token_lookup_filtered_rows": token_lookup_filtered_rows,
                "token_lookup_match_count": len(token_lookup_filtered_rows),
                "token_lookup_total_token_quantity": sum(int(row.get("token_quantity") or 0) for row in token_lookup_filtered_rows),
                "token_lookup_item_options": token_lookup_item_options,
                "token_lookup_item_type_options": token_lookup_item_type_options,
                "public_signature_state": public_signature_state,
                "public_signature_row_count": len(public_signature_rows),
                "public_signature_item_options": public_signature_item_options,
                "district_signature_state": district_signature_state,
                "district_signature_row_count": len(district_signature_rows),
                "district_signature_grouped": district_signature_grouped,
                "waiting_hall_state": waiting_hall_state,
                "waiting_hall_grouped": waiting_hall_grouped,
                "reports_shared_logo": _reports_shared_logo_state(self.request),
                "public_ack_state": public_ack_state,
                "public_ack_rows": public_ack_rows,
                "public_ack_row_count": len(public_ack_rows),
                "public_ack_template_fields": public_ack_template_fields,
                "segregation_state": segregation_state,
                "segregation_row_count": len(segregation_rows),
                "segregation_filter_values": {
                    "beneficiary_types": segregation_beneficiary_types,
                    "item_types": segregation_item_types,
                },
                "segregation_beneficiary_type_choices": SEGREGATION_BENEFICIARY_FILTER_CHOICES,
                "segregation_item_type_choices": SEGREGATION_ITEM_FILTER_CHOICES,
                "segregation_beneficiary_summary": _reports_selection_summary(
                    segregation_beneficiary_types,
                    SEGREGATION_BENEFICIARY_FILTER_CHOICES,
                ),
                "segregation_item_summary": _reports_selection_summary(
                    segregation_item_types,
                    SEGREGATION_ITEM_FILTER_CHOICES,
                ),
                "segregation_filtered_row_count": len(segregation_filtered_rows),
                "segregation_file1": segregation_file1,
                "segregation_file2": segregation_file2,
                "segregation_file3": segregation_file3,
                "distribution_state": distribution_state,
                "distribution_row_count": len(distribution_rows),
                "stage_distribution_filter_values": {
                    "beneficiary_types": stage_distribution_beneficiary_types,
                    "item_types": stage_distribution_item_types,
                    "premise": stage_distribution_premise,
                    "seq_start": int(stage_distribution_seq_start or 0) if stage_distribution_seq_start else "",
                    "seq_end": int(stage_distribution_seq_end or 0) if stage_distribution_seq_end else "",
                },
                "stage_distribution_beneficiary_type_choices": STAGE_DISTRIBUTION_BENEFICIARY_FILTER_CHOICES,
                "stage_distribution_item_type_choices": STAGE_DISTRIBUTION_ITEM_FILTER_CHOICES,
                "stage_distribution_premise_choices": STAGE_DISTRIBUTION_PREMISE_FILTER_CHOICES,
                "stage_distribution_beneficiary_summary": _reports_selection_summary(
                    stage_distribution_beneficiary_types,
                    STAGE_DISTRIBUTION_BENEFICIARY_FILTER_CHOICES,
                ),
                "stage_distribution_item_summary": _reports_selection_summary(
                    stage_distribution_item_types,
                    STAGE_DISTRIBUTION_ITEM_FILTER_CHOICES,
                ),
                "stage_distribution_premise_summary": _reports_selection_summary(
                    [stage_distribution_premise] if stage_distribution_premise != "all" else [],
                    STAGE_DISTRIBUTION_PREMISE_FILTER_CHOICES,
                ),
                "stage_distribution_file1": stage_distribution_file1,
                "stage_distribution_file1_title": stage_distribution_file1_title,
                "stage_distribution_file2": stage_distribution_file2,
                "stage_distribution_file3": stage_distribution_file3,
                "stage_distribution_file4": stage_distribution_file4,
                "stage_distribution_file5": stage_distribution_file5,
                "stage_distribution_file5_title": stage_distribution_file5_title,
                "stage_distribution_file6": stage_distribution_file6,
                "stage_distribution_file6_title": stage_distribution_file6_title,
                "reports_home_open_panel": reports_home_open_panel,
                "public_ack_field_rows": [
                    {
                        "field_name": field.get("field_name") or "",
                        "field_key": field.get("field_key") or "",
                        "selected_value": public_ack_state.get("field_map", {}).get(field.get("field_key") or "", ""),
                    }
                    for field in public_ack_template_fields
                ],
                "public_ack_column_options": _reports_public_ack_column_options(public_ack_state.get("headers") or []),
                "waiting_hall_beneficiary_type_choices": [
                    ("", "All"),
                    (models.RecipientTypeChoices.DISTRICT, "District"),
                    (models.RecipientTypeChoices.PUBLIC, "Public"),
                    (models.RecipientTypeChoices.INSTITUTIONS, "Institutions"),
                    (models.RecipientTypeChoices.OTHERS, "Others"),
                ],
                "waiting_hall_item_type_choices": [
                    (models.ItemTypeChoices.AID, "Aid"),
                    (models.ItemTypeChoices.ARTICLE, "Article"),
                    ("", "All"),
                ],
            }
        )
        return context
