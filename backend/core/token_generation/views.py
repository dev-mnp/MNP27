from __future__ import annotations

"""Views for token generation workflow."""

import csv

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse, HttpResponseRedirect
from django.urls import reverse
from django.utils import timezone
from django.views.generic import TemplateView

from core import models
from core.shared.csv_utils import _tabular_rows_from_upload
from core.shared.permissions import RoleRequiredMixin
from core.shared.phase2 import _phase2_parse_number
from core.shared.phase2 import _phase2_selected_session
from core.shared.token_generation import _token_generation_article_toggle_rows
from core.shared.token_generation import _token_generation_edit_candidates
from core.shared.token_generation import _token_generation_empty_value_summary
from core.shared.token_generation import _token_generation_filter_rows
from core.shared.token_generation import _token_generation_filter_state
from core.shared.token_generation import _token_generation_generate_dataset
from core.shared.token_generation import _token_generation_has_active_filters
from core.shared.token_generation import _token_generation_invalid_value_summary
from core.shared.token_generation import _token_generation_is_generated
from core.shared.token_generation import _token_generation_is_sorted
from core.shared.token_generation import _token_generation_latest_source_marker
from core.shared.token_generation import _token_generation_prepare_dataset
from core.shared.token_generation import _token_generation_quality_checks
from core.shared.token_generation import _token_generation_saved_dataset
from core.shared.token_generation import _token_generation_set_stage_state
from core.shared.token_generation import _token_generation_sort_dataset
from core.shared.token_generation import _token_generation_source_dataset
from core.shared.token_generation import _token_generation_stage_state
from core.shared.token_generation import _token_generation_store_dataset
from core.shared.token_generation import _token_generation_sync_required
from core.shared.token_generation import _token_generation_token_print_flag

class TokenGenerationView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    module_key = models.ModuleKeyChoices.TOKEN_GENERATION
    permission_action = "view"
    template_name = "token_generation/token_generation.html"

    def _token_open_section(self, session, filter_state):
        requested = str(self.request.GET.get("open_section") or "").strip()
        if requested:
            return requested
        stored = self.request.session.pop("token_generation_open_section", None)
        if stored:
            return stored
        if _token_generation_has_active_filters(filter_state):
            return "transformations"
        return ""

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        session = kwargs.get("selected_session") or _phase2_selected_session(self.request)
        dataset = _token_generation_saved_dataset(session) if session else {"headers": [], "rows": [], "source_name": "", "saved_at": None}
        rows = dataset["rows"]
        stage_state = _token_generation_stage_state(self.request, session) if session else {}
        filter_state = _token_generation_filter_state(self.request)
        open_section = self._token_open_section(session, filter_state)
        name_length_limit = _phase2_parse_number(self.request.GET.get("name_limit")) or 25
        preview_rows = rows[:10]
        preview_table = [
            [row.get(header, "") for header in dataset["headers"]]
            for row in preview_rows
        ]
        blank_summary = _token_generation_empty_value_summary(rows, dataset["headers"]) if rows else []
        empty_fill_approved = bool(stage_state.get("empty_fill_approved"))
        show_empty_fill_approval = bool(stage_state.get("show_empty_fill_approval"))
        quality_checks = _token_generation_quality_checks(rows) if rows else {
            "sequence_item_conflicts": [],
            "article_sequence_conflicts": [],
            "missing_sequences": [],
            "token_quantity_total": 0,
            "printable_token_total": 0,
            "zero_token_rows": 0,
        }
        prep_validation_summary = self.request.session.pop("token_generation_prep_validation_summary", None)
        token_is_prepared = bool(rows) and all("Names" in row for row in rows)
        is_sorted = _token_generation_is_sorted(rows)
        is_generated = _token_generation_is_generated(rows)
        token_step3_saved = bool(stage_state.get("token_print_saved")) and token_is_prepared
        generated_start_tokens = [
            _phase2_parse_number(row.get("Start Token No"))
            for row in rows
            if (_phase2_parse_number(row.get("Start Token No")) or 0) > 0
        ]
        generated_end_tokens = [
            _phase2_parse_number(row.get("End Token No"))
            for row in rows
            if (_phase2_parse_number(row.get("End Token No")) or 0) > 0
        ]
        token_start_no = min(generated_start_tokens) if generated_start_tokens else 0
        token_end_no = max(generated_end_tokens) if generated_end_tokens else 0
        prep_checks = [
            {"label": "Names column created", "passed": token_is_prepared and all("Names" in row for row in rows)},
            {"label": "Empty-value review approved", "passed": (not blank_summary) or empty_fill_approved},
            {"label": "Sorted by sequence, beneficiary type, handicapped status, and names", "passed": token_is_prepared and is_sorted},
            {"label": "Quantity, Cost Per Unit, and Total Value are all greater than 0", "passed": token_is_prepared and not prep_validation_summary},
            {"label": "Duplicate row check complete", "passed": token_is_prepared},
        ]
        edit_candidates = _token_generation_edit_candidates(rows, length_limit=name_length_limit) if token_is_prepared else []
        article_toggle_rows = _token_generation_article_toggle_rows(rows) if token_is_prepared else []
        filtered_rows = _token_generation_filter_rows(rows, filter_state) if rows else []
        excluded_rows = list(stage_state.get("excluded_rows") or [])
        context.update(
            {
                "page_title": "Token Generation",
                "selected_session": session,
                "token_rows": preview_table,
                "token_headers": dataset["headers"],
                "token_row_count": len(rows),
                "token_source_name": dataset["source_name"],
                "token_saved_at_display": timezone.localtime(dataset["saved_at"]).strftime("%d/%m/%Y %I:%M %p") if dataset["saved_at"] else "",
                "token_blank_summary": blank_summary,
                "token_prep_validation_summary": prep_validation_summary,
                "token_quality_checks": quality_checks,
                "token_column_count": len(dataset["headers"]),
                "token_prep_checks": prep_checks,
                "token_empty_fill_approved": empty_fill_approved,
                "token_show_empty_fill_approval": show_empty_fill_approval,
                "token_is_prepared": token_is_prepared,
                "token_is_sorted": is_sorted,
                "token_is_generated": is_generated,
                "token_step3_saved": token_step3_saved,
                "token_start_no": token_start_no,
                "token_end_no": token_end_no,
                "token_edit_candidates": edit_candidates,
                "token_name_length_limit": int(name_length_limit),
                "token_article_toggles": article_toggle_rows,
                "token_filter_state": filter_state,
                "token_filtered_rows": filtered_rows,
                "token_excluded_rows": excluded_rows,
                "token_open_section": open_section,
                "token_sync_required": _token_generation_sync_required(self.request, session, dataset) if session else False,
                "can_create_edit": self.request.user.has_module_permission(self.module_key, "create_edit"),
                "can_export": self.request.user.has_module_permission(self.module_key, "export"),
                "can_upload_replace": self.request.user.has_module_permission(self.module_key, "upload_replace"),
            }
        )
        return context

    def get(self, request, *args, **kwargs):
        session = _phase2_selected_session(request)
        if request.GET.get("export") and session and request.user.has_module_permission(self.module_key, "export"):
            dataset = _token_generation_saved_dataset(session)
            if not dataset["rows"]:
                messages.warning(request, "Sync or upload token data first.")
                return HttpResponseRedirect(f'{reverse("ui:token-generation")}?session={session.pk}')
            response = HttpResponse(content_type="text/csv")
            timestamp = timezone.localtime().strftime("%d_%b_%y_%H_%M")
            response["Content-Disposition"] = f'attachment; filename="4_Master_Data_Token_{timestamp}.csv"'
            writer = csv.DictWriter(response, fieldnames=dataset["headers"])
            writer.writeheader()
            for row in dataset["rows"]:
                writer.writerow(row)
            return response
        return self.render_to_response(self.get_context_data(selected_session=session))

    def post(self, request, *args, **kwargs):
        session = _phase2_selected_session(request)
        if not session:
            messages.error(request, "Create or select a session first.")
            return HttpResponseRedirect(reverse("ui:token-generation"))
        if not request.user.has_module_permission(self.module_key, "create_edit"):
            messages.error(request, "You do not have permission to update token data.")
            return HttpResponseRedirect(f'{reverse("ui:token-generation")}?session={session.pk}')

        action = (request.POST.get("action") or "").strip()
        if action == "sync_data":
            dataset = _token_generation_source_dataset(session)
            _token_generation_store_dataset(
                session=session,
                dataset=dataset,
                source_name=f"Synced from Sequence List ({session.session_name})",
                user=request.user,
            )
            _token_generation_set_stage_state(
                request,
                session,
                token_print_saved=False,
                source_sync_marker=_token_generation_latest_source_marker(session),
                empty_fill_approved=False,
                show_empty_fill_approval=False,
                excluded_rows=[],
            )
            request.session["token_generation_open_section"] = ""
            messages.success(
                request,
                (
                    f"Token Generation synced {len(dataset['rows'])} row(s). "
                    f"Previous-stage data loaded successfully."
                ),
            )
            return HttpResponseRedirect(f'{reverse("ui:token-generation")}?session={session.pk}')

        if action == "upload_csv":
            if not request.user.has_module_permission(self.module_key, "upload_replace"):
                messages.error(request, "You do not have permission to upload token data.")
                return HttpResponseRedirect(f'{reverse("ui:token-generation")}?session={session.pk}')
            uploaded_file = request.FILES.get("file")
            if not uploaded_file:
                messages.error(request, "Choose a CSV or Excel file to upload.")
                return HttpResponseRedirect(f'{reverse("ui:token-generation")}?session={session.pk}')
            source_headers, source_rows = _tabular_rows_from_upload(uploaded_file)
            if not source_headers:
                messages.error(request, "Uploaded file is empty.")
                return HttpResponseRedirect(f'{reverse("ui:token-generation")}?session={session.pk}')
            dataset = {
                "headers": source_headers,
                "rows": source_rows,
                "blank_summary": _token_generation_empty_value_summary(source_rows, source_headers),
                "quality_checks": _token_generation_quality_checks(source_rows),
            }
            _token_generation_store_dataset(
                session=session,
                dataset=dataset,
                source_name=uploaded_file.name,
                user=request.user,
            )
            _token_generation_set_stage_state(
                request,
                session,
                token_print_saved=False,
                source_sync_marker="",
                empty_fill_approved=False,
                show_empty_fill_approval=False,
                excluded_rows=[],
            )
            request.session["token_generation_open_section"] = ""
            messages.success(
                request,
                (
                    f"Uploaded {len(dataset['rows'])} row(s) into Token Generation. "
                    f"Previous-stage data loaded successfully."
                ),
            )
            return HttpResponseRedirect(f'{reverse("ui:token-generation")}?session={session.pk}')

        saved_dataset = _token_generation_saved_dataset(session)
        if not saved_dataset["rows"]:
            messages.warning(request, "Sync or upload token data first.")
            return HttpResponseRedirect(f'{reverse("ui:token-generation")}?session={session.pk}')
        if _token_generation_sync_required(request, session, saved_dataset):
            messages.warning(request, "Click Sync Data first to load the latest Sequence List data before continuing.")
            return HttpResponseRedirect(f'{reverse("ui:token-generation")}?session={session.pk}')

        if action == "exclude_selected_rows":
            selected_indices = {
                _phase2_parse_number(value)
                for value in request.POST.getlist("selected_row_index")
                if str(value).strip()
            }
            selected_indices = {int(value) for value in selected_indices if value is not None}
            original_rows = [dict(row) for row in saved_dataset["rows"]]
            excluded_rows = [dict(row) for index, row in enumerate(original_rows) if index in selected_indices]
            filtered_rows = [
                row for index, row in enumerate(original_rows)
                if index not in selected_indices
            ]
            removed_count = len(original_rows) - len(filtered_rows)
            filtered_headers = [
                header for header in list(saved_dataset["headers"] or [])
                if header not in {"Start Token No", "End Token No"}
            ]
            for row in filtered_rows:
                row.pop("Start Token No", None)
                row.pop("End Token No", None)
            saved_dataset["headers"] = filtered_headers
            saved_dataset["rows"] = filtered_rows
            _token_generation_store_dataset(
                session=session,
                dataset=saved_dataset,
                source_name=saved_dataset["source_name"] or f"Rule-filtered Token Data ({session.session_name})",
                user=request.user,
            )
            _token_generation_set_stage_state(
                request,
                session,
                token_print_saved=False,
                empty_fill_approved=False,
                show_empty_fill_approval=False,
                excluded_rows=[
                    {
                        "row_index": index,
                        "application_number": str(row.get("Application Number") or "").strip(),
                        "beneficiary_name": str(row.get("Beneficiary Name") or "").strip(),
                        "beneficiary_type": str(row.get("Beneficiary Type") or "").strip(),
                        "requested_item": str(row.get("Requested Item") or "").strip(),
                        "item_type": str(row.get("Item Type") or "").strip(),
                        "row_data": row,
                    }
                    for index, row in enumerate(excluded_rows)
                ],
            )
            request.session["token_generation_open_section"] = "transformations"
            messages.success(
                request,
                f"Transformation rules applied. Removed {removed_count} selected row(s). Source data is unchanged.",
            )
            return HttpResponseRedirect(f'{reverse("ui:token-generation")}?session={session.pk}')

        if action == "restore_excluded_rows":
            excluded_pool = list(stage_state.get("excluded_rows") or [])
            restore_indices = {
                _phase2_parse_number(value)
                for value in request.POST.getlist("restore_row_index")
                if str(value).strip()
            }
            restore_indices = {int(value) for value in restore_indices if value is not None}
            if not excluded_pool:
                messages.warning(request, "No excluded rows to restore.")
                return HttpResponseRedirect(f'{reverse("ui:token-generation")}?session={session.pk}')
            restored_rows = []
            remaining_excluded = []
            for index, row in enumerate(excluded_pool):
                if index in restore_indices:
                    restored_row = dict(row.get("row_data") or {})
                    if restored_row:
                        restored_rows.append(restored_row)
                else:
                    remaining_excluded.append(row)
            if not restored_rows:
                messages.warning(request, "Select at least one excluded row to restore.")
                return HttpResponseRedirect(f'{reverse("ui:token-generation")}?session={session.pk}')
            active_rows = [dict(row) for row in saved_dataset["rows"]]
            active_rows.extend(restored_rows)
            saved_dataset["rows"] = active_rows
            saved_dataset["headers"] = [
                header for header in list(saved_dataset["headers"] or [])
                if header not in {"Start Token No", "End Token No"}
            ]
            for row in saved_dataset["rows"]:
                row.pop("Start Token No", None)
                row.pop("End Token No", None)
            _token_generation_store_dataset(
                session=session,
                dataset=saved_dataset,
                source_name=saved_dataset["source_name"] or f"Rule-filtered Token Data ({session.session_name})",
                user=request.user,
            )
            _token_generation_set_stage_state(
                request,
                session,
                token_print_saved=False,
                empty_fill_approved=False,
                show_empty_fill_approval=False,
                excluded_rows=remaining_excluded,
            )
            request.session["token_generation_open_section"] = "transformations"
            messages.success(
                request,
                f"Restored {len(restored_rows)} excluded row(s) back into the active token list.",
            )
            return HttpResponseRedirect(f'{reverse("ui:token-generation")}?session={session.pk}')

        if action == "run_data_prep":
            prefill_empty_summary = _token_generation_empty_value_summary(saved_dataset["rows"], saved_dataset["headers"])
            approved = str(request.POST.get("approve_empty_fill") or "").strip() == "1"
            if prefill_empty_summary and not approved:
                request.session["token_generation_open_section"] = "step1"
                _token_generation_set_stage_state(request, session, show_empty_fill_approval=True)
                messages.warning(
                    request,
                    "Step 1 is waiting for your approval. Review the empty-value column counts and confirm to proceed with fill.",
                )
                return HttpResponseRedirect(f'{reverse("ui:token-generation")}?session={session.pk}')
            prepared_dataset = _token_generation_prepare_dataset(saved_dataset["rows"], saved_dataset["headers"])
            invalid_value_summary = _token_generation_invalid_value_summary(prepared_dataset["rows"], saved_dataset["headers"])
            if invalid_value_summary:
                request.session["token_generation_prep_validation_summary"] = invalid_value_summary
                request.session["token_generation_open_section"] = "step1"
                issue_text = ", ".join(
                    f"{entry['label']} ({entry['count']})"
                    for entry in invalid_value_summary
                )
                messages.error(
                    request,
                    f"Step 1 data prep is blocked. After filling empty values, values below 1 were found in: {issue_text}. Please fix the source data first.",
                )
                return HttpResponseRedirect(f'{reverse("ui:token-generation")}?session={session.pk}')
            _token_generation_store_dataset(
                session=session,
                dataset=prepared_dataset,
                source_name=saved_dataset["source_name"] or f"Prepared Token Data ({session.session_name})",
                user=request.user,
            )
            _token_generation_set_stage_state(
                request,
                session,
                token_print_saved=False,
                empty_fill_approved=True,
                show_empty_fill_approval=False,
            )
            request.session["token_generation_open_section"] = "step1"
            messages.success(request, "Step 1 data prep completed. Names, blanks, sorting, and duplicate checks are ready.")
            return HttpResponseRedirect(f'{reverse("ui:token-generation")}?session={session.pk}')

        if action in {"sort_data", "save_adjustments"}:
            if not (bool(saved_dataset["rows"]) and all("Names" in row for row in saved_dataset["rows"])):
                request.session["token_generation_open_section"] = "step2"
                messages.warning(request, "Run Step 1 data prep before saving name changes.")
                return HttpResponseRedirect(f'{reverse("ui:token-generation")}?session={session.pk}')
            rows = [dict(row) for row in saved_dataset["rows"]]
            replacements_applied = 0
            for original_name, replacement_name in request.POST.items():
                if original_name.startswith("replace_name__"):
                    source = original_name.replace("replace_name__", "", 1)
                    source = source.replace("__SLASH__", "/")
                    replacement = (replacement_name or "").strip()
                    if replacement:
                        for row in rows:
                            if str(row.get("Names") or "") == source:
                                row["Names"] = replacement
                                replacements_applied += 1
                if original_name.startswith("replace_token_name__"):
                    source = original_name.replace("replace_token_name__", "", 1)
                    source = source.replace("__SLASH__", "/")
                    replacement = (replacement_name or "").strip()
                    if replacement:
                        for row in rows:
                            if str(row.get("Token Name") or "") == source:
                                row["Token Name"] = replacement
                                replacements_applied += 1
            saved_dataset["rows"] = _token_generation_sort_dataset(rows)
            _token_generation_store_dataset(
                session=session,
                dataset=saved_dataset,
                source_name=saved_dataset["source_name"] or f"Sorted Token Data ({session.session_name})",
                user=request.user,
            )
            _token_generation_set_stage_state(
                request,
                session,
                token_print_saved=False,
                empty_fill_approved=False,
                show_empty_fill_approval=False,
            )
            request.session["token_generation_open_section"] = "step2"
            messages.success(request, f"Step 2 adjustments saved. {replacements_applied} replacement(s) were applied.")
            return HttpResponseRedirect(f'{reverse("ui:token-generation")}?session={session.pk}')

        if action == "save_token_print":
            if not (bool(saved_dataset["rows"]) and all("Names" in row for row in saved_dataset["rows"])):
                request.session["token_generation_open_section"] = "step3"
                messages.warning(request, "Run Step 1 data prep before updating token print settings.")
                return HttpResponseRedirect(f'{reverse("ui:token-generation")}?session={session.pk}')
            rows = [dict(row) for row in saved_dataset["rows"]]
            skip_items = {
                value.strip()
                for value in request.POST.getlist("skip_label_item")
                if str(value).strip()
            }
            for row in rows:
                requested_item = str(row.get("Requested Item") or "").strip()
                if requested_item in skip_items:
                    row["Token Print for ARTL"] = "0"
                else:
                    _token_generation_token_print_flag(row)
            saved_dataset["rows"] = rows
            _token_generation_store_dataset(
                session=session,
                dataset=saved_dataset,
                source_name=saved_dataset["source_name"] or f"Token Print Updated ({session.session_name})",
                user=request.user,
            )
            _token_generation_set_stage_state(
                request,
                session,
                token_print_saved=True,
                empty_fill_approved=False,
                show_empty_fill_approval=False,
            )
            request.session["token_generation_open_section"] = "step3"
            messages.success(request, "Step 3 token print settings were saved.")
            return HttpResponseRedirect(f'{reverse("ui:token-generation")}?session={session.pk}')

        if action == "generate_tokens":
            rows = saved_dataset["rows"]
            if not (bool(rows) and all("Names" in row for row in rows)):
                request.session["token_generation_open_section"] = "step4"
                messages.warning(request, "Run Step 1 data prep before generating token numbers.")
                return HttpResponseRedirect(f'{reverse("ui:token-generation")}?session={session.pk}')
            if not _token_generation_is_sorted(rows):
                request.session["token_generation_open_section"] = "step4"
                messages.warning(request, "Complete Step 2 adjustments before generating token numbers.")
                return HttpResponseRedirect(f'{reverse("ui:token-generation")}?session={session.pk}')
            if not _token_generation_stage_state(request, session).get("token_print_saved"):
                request.session["token_generation_open_section"] = "step4"
                messages.warning(request, "Complete Step 3 token print review before generating token numbers.")
                return HttpResponseRedirect(f'{reverse("ui:token-generation")}?session={session.pk}')
            generated_dataset = _token_generation_generate_dataset(rows, saved_dataset["headers"])
            saved_dataset["rows"] = generated_dataset["rows"]
            saved_dataset["headers"] = generated_dataset["headers"]
            _token_generation_store_dataset(
                session=session,
                dataset=saved_dataset,
                source_name=saved_dataset["source_name"] or f"Generated Token Data ({session.session_name})",
                user=request.user,
            )
            request.session["token_generation_open_section"] = "step4"
            start_numbers = [
                _phase2_parse_number(row.get("Start Token No")) or 0
                for row in saved_dataset["rows"]
                if (_phase2_parse_number(row.get("Start Token No")) or 0) > 0
            ]
            end_numbers = [
                _phase2_parse_number(row.get("End Token No")) or 0
                for row in saved_dataset["rows"]
                if (_phase2_parse_number(row.get("End Token No")) or 0) > 0
            ]
            start_no = min(start_numbers) if start_numbers else 0
            end_no = max(end_numbers) if end_numbers else 0
            messages.success(request, f"Token numbers generated. Starting: {start_no}, Ending: {end_no}")
            return HttpResponseRedirect(f'{reverse("ui:token-generation")}?session={session.pk}')

        return HttpResponseRedirect(f'{reverse("ui:token-generation")}?session={session.pk}')
