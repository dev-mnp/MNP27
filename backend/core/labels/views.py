from __future__ import annotations

"""Views for labels workflow."""

import io
import zipfile

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse, HttpResponseRedirect
from django.urls import reverse
from django.utils import timezone
from django.views.generic import TemplateView
from pypdf import PdfReader, PdfWriter

from core import models
from core.labels import services
from core.labels.services import LABELS_DEFAULT_2L_ITEMS
from core.labels.services import _labels_audit_download
from core.labels.services import _labels_available_requested_items
from core.labels.services import _labels_download_filename
from core.labels.services import _labels_expand_entries
from core.labels.services import _labels_has_generated_tokens
from core.labels.services import _labels_latest_source_marker
from core.labels.services import _labels_normalize_dataset
from core.labels.services import _labels_saved_dataset
from core.labels.services import _labels_set_stage_state
from core.labels.services import _labels_source_dataset
from core.labels.services import _labels_stage_state
from core.labels.services import _labels_store_dataset
from core.labels.services import _labels_sync_required
from core.shared.csv_utils import _tabular_rows_from_upload
from core.shared.phase2 import _phase2_parse_number
from core.shared.phase2 import _phase2_selected_session
from core.shared.permissions import RoleRequiredMixin


class LabelGenerationView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    module_key = models.ModuleKeyChoices.LABELS
    permission_action = "view"
    template_name = "labels/labels.html"

    def _build_download_response(self, request, session, download_kind):
        dataset = _labels_saved_dataset(session)
        rows = dataset["rows"]
        if not rows:
            messages.warning(request, "Sync or upload label data first.")
            return HttpResponseRedirect(f'{reverse("ui:labels")}?session={session.pk}')
        if _labels_sync_required(request, session, dataset):
            messages.warning(request, "Click Sync Data first to load the latest Token Generation data before downloading labels.")
            return HttpResponseRedirect(f'{reverse("ui:labels")}?session={session.pk}')
        if not _labels_has_generated_tokens(rows):
            messages.warning(request, "Generate token numbers in Token Generation before downloading labels.")
            return HttpResponseRedirect(f'{reverse("ui:labels")}?session={session.pk}')

        stage_state = _labels_stage_state(request, session)
        large_items = set(stage_state["large_items"])
        audit = _labels_audit_download(rows, download_kind=download_kind, large_items=large_items)
        if not audit["ready"]:
            if audit["expected_labels"] <= 0:
                messages.warning(request, audit["reason"] or "No matching labels are available for this download yet.")
            else:
                messages.warning(
                    request,
                    (
                        f"Label check failed for this download. Expected labels: {audit['expected_labels']}, "
                        f"generated labels: {audit['actual_labels']}, duplicate tokens: {audit['duplicate_tokens']}, "
                        f"invalid ranges: {audit['invalid_range_rows']}."
                    ),
                )
            return HttpResponseRedirect(f'{reverse("ui:labels")}?session={session.pk}')

        def token_qty(row):
            return (_phase2_parse_number(row.get("Token Quantity")) or 0)

        def is_printable_article(row):
            return token_qty(row) > 0 and (_phase2_parse_number(row.get("Token Print for ARTL")) or 0) != 0

        def sort_by_name_and_start(row):
            return (
                str(row.get("Names") or "").strip(),
                _phase2_parse_number(row.get("Start Token No")) or 0,
            )

        def sort_by_item_and_start(row):
            return (
                str(row.get("Token Name") or row.get("Requested Item") or "").strip(),
                str(row.get("Names") or "").strip(),
                _phase2_parse_number(row.get("Start Token No")) or 0,
            )

        label_buffer = None
        filename = None

        if download_kind == "article_12l_separate":
            if not stage_state.get("large_items_saved"):
                messages.warning(request, "Select 2L Items first before downloading article labels.")
                return HttpResponseRedirect(f'{reverse("ui:labels")}?session={session.pk}')
            entries = _labels_expand_entries(
                rows,
                row_filter=lambda row: is_printable_article(row) and str(row.get("Requested Item") or "").strip() not in large_items,
                group_by=lambda row: str(row.get("Token Name") or row.get("Requested Item") or "").strip(),
            )
            label_buffer = services.generate_mnp_labels_pdf(entries, layout="12L", mode="separate")
            filename = _labels_download_filename("1_Article_Labels_S")
        elif download_kind == "article_12l_continuous":
            if not stage_state.get("large_items_saved"):
                messages.warning(request, "Select 2L Items first before downloading article labels.")
                return HttpResponseRedirect(f'{reverse("ui:labels")}?session={session.pk}')
            entries = _labels_expand_entries(
                rows,
                row_filter=lambda row: is_printable_article(row) and str(row.get("Requested Item") or "").strip() not in large_items,
            )
            label_buffer = services.generate_mnp_labels_pdf(entries, layout="12L", mode="continuous")
            filename = _labels_download_filename("1_Article_Labels_C")
        elif download_kind == "article_2l_continuous":
            if not stage_state.get("large_items_saved"):
                messages.warning(request, "Select 2L Items first before downloading article labels.")
                return HttpResponseRedirect(f'{reverse("ui:labels")}?session={session.pk}')
            entries = _labels_expand_entries(
                rows,
                row_filter=lambda row: token_qty(row) > 0 and str(row.get("Requested Item") or "").strip() in large_items,
            )
            label_buffer = services.generate_mnp_labels_pdf(entries, layout="2L", mode="continuous")
            filename = _labels_download_filename("2_Article_2L_Labels")
        elif download_kind == "district_separate":
            entries = _labels_expand_entries(
                rows,
                row_filter=lambda row: token_qty(row) > 0 and str(row.get("Beneficiary Type") or "").strip() == "District",
                group_by=lambda row: str(row.get("Names") or "").strip(),
                sort_key=sort_by_name_and_start,
            )
            label_buffer = services.generate_mnp_labels_pdf(entries, layout="12L", mode="separate")
            filename = _labels_download_filename("3_District_Labels_S")
        elif download_kind == "district_continuous":
            entries = _labels_expand_entries(
                rows,
                row_filter=lambda row: token_qty(row) > 0 and str(row.get("Beneficiary Type") or "").strip() == "District",
                sort_key=sort_by_name_and_start,
            )
            label_buffer = services.generate_mnp_labels_pdf(entries, layout="12L", mode="continuous")
            filename = _labels_download_filename("3_District_Labels_C")
        elif download_kind == "institution":
            entries = _labels_expand_entries(
                rows,
                row_filter=lambda row: token_qty(row) > 0 and str(row.get("Beneficiary Type") or "").strip() == "Institutions",
                sort_key=sort_by_name_and_start,
            )
            label_buffer = services.generate_mnp_labels_pdf(entries, layout="12L", mode="continuous")
            filename = _labels_download_filename("5_Institution_Labels")
        elif download_kind == "public":
            entries = _labels_expand_entries(
                rows,
                row_filter=lambda row: token_qty(row) > 0 and str(row.get("Beneficiary Type") or "").strip() == "Public",
                sort_key=sort_by_item_and_start,
            )
            label_buffer = services.generate_mnp_labels_pdf(entries, layout="12L", mode="continuous")
            filename = _labels_download_filename("5_Public_Labels")
        elif download_kind == "chair_separate":
            entries = _labels_expand_entries(
                rows,
                row_filter=lambda row: token_qty(row) > 0,
                group_by=lambda row: str(row.get("Token Name") or row.get("Requested Item") or "").strip(),
            )
            label_buffer = services.generate_mnp_labels_pdf(entries, layout="12L", mode="separate")
            filename = _labels_download_filename("Chair_Labels_S")
        elif download_kind == "chair_continuous":
            entries = _labels_expand_entries(
                rows,
                row_filter=lambda row: token_qty(row) > 0,
            )
            label_buffer = services.generate_mnp_labels_pdf(entries, layout="12L", mode="continuous")
            filename = _labels_download_filename("Chair_Labels_C")
        else:
            messages.warning(request, "Unknown label download requested.")
            return HttpResponseRedirect(f'{reverse("ui:labels")}?session={session.pk}')

        response = HttpResponse(label_buffer.getvalue(), content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        session = kwargs.get("selected_session") or _phase2_selected_session(self.request)
        dataset = _labels_saved_dataset(session) if session else {"headers": [], "rows": [], "source_name": "", "saved_at": None}
        rows = dataset["rows"]
        stage_state = _labels_stage_state(self.request, session) if session else {"large_items": list(LABELS_DEFAULT_2L_ITEMS)}
        available_items = _labels_available_requested_items(rows)
        large_items = stage_state["large_items"] if session else list(LABELS_DEFAULT_2L_ITEMS)
        label_audits = {
            "article_12l_continuous": _labels_audit_download(rows, download_kind="article_12l_continuous", large_items=large_items) if rows else {},
            "article_12l_separate": _labels_audit_download(rows, download_kind="article_12l_separate", large_items=large_items) if rows else {},
            "article_2l_continuous": _labels_audit_download(rows, download_kind="article_2l_continuous", large_items=large_items) if rows else {},
            "district_continuous": _labels_audit_download(rows, download_kind="district_continuous", large_items=large_items) if rows else {},
            "district_separate": _labels_audit_download(rows, download_kind="district_separate", large_items=large_items) if rows else {},
            "institution": _labels_audit_download(rows, download_kind="institution", large_items=large_items) if rows else {},
            "public": _labels_audit_download(rows, download_kind="public", large_items=large_items) if rows else {},
            "chair_continuous": _labels_audit_download(rows, download_kind="chair_continuous", large_items=large_items) if rows else {},
            "chair_separate": _labels_audit_download(rows, download_kind="chair_separate", large_items=large_items) if rows else {},
        }
        context.update(
            {
                "page_title": "Labels",
                "selected_session": session,
                "label_row_count": len(rows),
                "label_column_count": len(dataset["headers"]),
                "label_saved_at_display": timezone.localtime(dataset["saved_at"]).strftime("%d/%m/%Y %I:%M %p") if dataset["saved_at"] else "",
                "label_source_name": str(dataset["source_name"] or "").replace(" (Event)", ""),
                "label_has_generated_tokens": _labels_has_generated_tokens(rows),
                "label_sync_required": _labels_sync_required(self.request, session, dataset) if session else False,
                "label_large_items_saved": bool(stage_state.get("large_items_saved")),
                "label_large_items": available_items,
                "label_selected_large_items": stage_state["large_items"],
                "label_audits": label_audits,
                "can_create_edit": self.request.user.has_module_permission(self.module_key, "create_edit"),
                "can_export": self.request.user.has_module_permission(self.module_key, "export"),
                "can_upload_replace": self.request.user.has_module_permission(self.module_key, "upload_replace"),
            }
        )
        return context

    def get(self, request, *args, **kwargs):
        session = _phase2_selected_session(request)
        if request.GET.get("download") and session and request.user.has_module_permission(self.module_key, "export"):
            return self._build_download_response(request, session, str(request.GET.get("download") or "").strip())
        return self.render_to_response(self.get_context_data(selected_session=session))

    def post(self, request, *args, **kwargs):
        session = _phase2_selected_session(request)
        if not session:
            messages.error(request, "Create or select a session first.")
            return HttpResponseRedirect(reverse("ui:labels"))
        if not request.user.has_module_permission(self.module_key, "create_edit"):
            messages.error(request, "You do not have permission to update label data.")
            return HttpResponseRedirect(f'{reverse("ui:labels")}?session={session.pk}')

        action = (request.POST.get("action") or "").strip()
        if action == "sync_data":
            dataset = _labels_source_dataset(session)
            _labels_store_dataset(
                session=session,
                dataset=dataset,
                source_name="Synced from Token Generation",
                user=request.user,
            )
            _labels_set_stage_state(
                request,
                session,
                source_sync_marker=_labels_latest_source_marker(session),
                large_items_saved=False,
            )
            messages.success(request, f"Labels synced {len(dataset['rows'])} row(s) from Token Generation.")
            return HttpResponseRedirect(f'{reverse("ui:labels")}?session={session.pk}')

        if action == "upload_csv":
            if not request.user.has_module_permission(self.module_key, "upload_replace"):
                messages.error(request, "You do not have permission to upload label data.")
                return HttpResponseRedirect(f'{reverse("ui:labels")}?session={session.pk}')
            uploaded_file = request.FILES.get("file")
            if not uploaded_file:
                messages.error(request, "Choose a CSV or Excel file to upload.")
                return HttpResponseRedirect(f'{reverse("ui:labels")}?session={session.pk}')
            dataset = {
                "headers": [],
                "rows": [],
            }
            dataset["headers"], dataset["rows"] = _tabular_rows_from_upload(uploaded_file)
            dataset = _labels_normalize_dataset(dataset)
            _labels_store_dataset(
                session=session,
                dataset=dataset,
                source_name=uploaded_file.name,
                user=request.user,
            )
            _labels_set_stage_state(
                request,
                session,
                source_sync_marker="",
                large_items_saved=False,
            )
            messages.success(request, f"Uploaded {len(dataset['rows'])} row(s) into Labels.")
            return HttpResponseRedirect(f'{reverse("ui:labels")}?session={session.pk}')

        if action == "save_large_items":
            selected_large_items = [
                value.strip()
                for value in request.POST.getlist("large_label_item")
                if str(value).strip()
            ]
            _labels_set_stage_state(request, session, large_items=selected_large_items, large_items_saved=True)
            messages.success(request, "2L article label selections saved.")
            return HttpResponseRedirect(f'{reverse("ui:labels")}?session={session.pk}')

        if action == "download_custom_labels":
            if not request.user.has_module_permission(self.module_key, "export"):
                messages.error(request, "You do not have permission to download labels.")
                return HttpResponseRedirect(f'{reverse("ui:labels")}?session={session.pk}')

            def _parse_custom_bulk(raw_text, layout):
                default_font_size = 72 if layout == "A4" else 54 if layout == "2L" else 30
                entries = []
                for raw_line in str(raw_text or "").splitlines():
                    line = str(raw_line or "").strip()
                    if not line:
                        continue
                    parts = [part.strip() for part in line.split(",")]
                    if len(parts) < 2:
                        continue
                    text_value = parts[0]
                    count_value = _phase2_parse_number(parts[1]) or 0
                    font_size_value = _phase2_parse_number(parts[2]) if len(parts) >= 3 else default_font_size
                    font_size_value = max(8, min(int(font_size_value or default_font_size), 120))
                    line_spacing_value = _phase2_parse_number(parts[3]) if len(parts) >= 4 else None
                    if line_spacing_value is not None:
                        line_spacing_value = max(0, min(int(line_spacing_value), 120))
                    if text_value and count_value > 0:
                        entries.append(
                            {
                                "text": text_value,
                                "count": count_value,
                                "font_size": font_size_value,
                                "line_spacing": line_spacing_value,
                            }
                        )
                return entries

            custom_bulks = request.POST.getlist("custom_label_bulk")
            custom_layouts = request.POST.getlist("custom_label_layout")
            groups = []
            for index, raw_bulk in enumerate(custom_bulks):
                layout_value = str(custom_layouts[index] if index < len(custom_layouts) else "12L" or "12L").strip().upper()
                if layout_value not in {"12L", "2L", "A4"}:
                    layout_value = "12L"
                entries = _parse_custom_bulk(raw_bulk, layout_value)
                if entries:
                    groups.append({"layout": layout_value, "entries": entries})

            if not groups:
                messages.error(request, "Paste at least one custom label row as Label text,count or Label text,count,font size,line spacing.")
                return HttpResponseRedirect(f'{reverse("ui:labels")}?session={session.pk}')

            if len(groups) == 1:
                label_buffer = services.generate_mnp_custom_labels_pdf(groups[0]["entries"], layout=groups[0]["layout"])
                response = HttpResponse(label_buffer.getvalue(), content_type="application/pdf")
                single_filename = _labels_download_filename("Custom_Labels_%s" % groups[0]["layout"])
                response["Content-Disposition"] = f'attachment; filename="{single_filename}"'
                return response

            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as bundle:
                for index, group in enumerate(groups, start=1):
                    label_buffer = services.generate_mnp_custom_labels_pdf(group["entries"], layout=group["layout"])
                    filename = _labels_download_filename(f"Custom_Labels_{index}_{group['layout']}")
                    bundle.writestr(filename, label_buffer.getvalue())
            zip_buffer.seek(0)
            timestamp = timezone.localtime().strftime("%d_%b_%y_%H_%M")
            response = HttpResponse(zip_buffer.getvalue(), content_type="application/zip")
            response["Content-Disposition"] = f'attachment; filename="Custom_Labels_{timestamp}.zip"'
            return response

        if action == "preview_custom_labels":
            if not request.user.has_module_permission(self.module_key, "export"):
                messages.error(request, "You do not have permission to preview labels.")
                return HttpResponseRedirect(f'{reverse("ui:labels")}?session={session.pk}')

            def _parse_custom_bulk(raw_text, layout):
                default_font_size = 72 if layout == "A4" else 54 if layout == "2L" else 30
                entries = []
                for raw_line in str(raw_text or "").splitlines():
                    line = str(raw_line or "").strip()
                    if not line:
                        continue
                    parts = [part.strip() for part in line.split(",")]
                    if len(parts) < 2:
                        continue
                    text_value = parts[0]
                    count_value = _phase2_parse_number(parts[1]) or 0
                    font_size_value = _phase2_parse_number(parts[2]) if len(parts) >= 3 else default_font_size
                    font_size_value = max(8, min(int(font_size_value or default_font_size), 120))
                    line_spacing_value = _phase2_parse_number(parts[3]) if len(parts) >= 4 else None
                    if line_spacing_value is not None:
                        line_spacing_value = max(0, min(int(line_spacing_value), 120))
                    if text_value and count_value > 0:
                        entries.append(
                            {
                                "text": text_value,
                                "count": count_value,
                                "font_size": font_size_value,
                                "line_spacing": line_spacing_value,
                            }
                        )
                return entries

            custom_bulks = request.POST.getlist("custom_label_bulk")
            custom_layouts = request.POST.getlist("custom_label_layout")
            groups = []
            for index, raw_bulk in enumerate(custom_bulks):
                layout_value = str(custom_layouts[index] if index < len(custom_layouts) else "12L" or "12L").strip().upper()
                if layout_value not in {"12L", "2L", "A4"}:
                    layout_value = "12L"
                entries = _parse_custom_bulk(raw_bulk, layout_value)
                if entries:
                    groups.append({"layout": layout_value, "entries": entries})

            if not groups:
                messages.error(request, "Paste at least one custom label row as Label text,count or Label text,count,font size,line spacing.")
                return HttpResponseRedirect(f'{reverse("ui:labels")}?session={session.pk}')

            if len(groups) == 1:
                label_buffer = services.generate_mnp_custom_labels_pdf(groups[0]["entries"], layout=groups[0]["layout"])
                response = HttpResponse(label_buffer.getvalue(), content_type="application/pdf")
                response["Content-Disposition"] = 'inline; filename="Custom_Labels_Preview.pdf"'
                return response

            merged_writer = PdfWriter()
            for group in groups:
                label_buffer = services.generate_mnp_custom_labels_pdf(group["entries"], layout=group["layout"])
                group_reader = PdfReader(io.BytesIO(label_buffer.getvalue()))
                for page in group_reader.pages:
                    merged_writer.add_page(page)
            merged_output = io.BytesIO()
            merged_writer.write(merged_output)
            merged_output.seek(0)
            response = HttpResponse(merged_output.getvalue(), content_type="application/pdf")
            response["Content-Disposition"] = 'inline; filename="Custom_Labels_Preview.pdf"'
            return response

        return HttpResponseRedirect(f'{reverse("ui:labels")}?session={session.pk}')
