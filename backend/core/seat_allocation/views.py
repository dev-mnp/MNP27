from __future__ import annotations

"""Views for seat allocation workflow."""

import csv

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.db.models import F
from django.http import HttpResponse, HttpResponseRedirect
from django.urls import reverse
from django.utils import timezone
from django.views.generic import TemplateView

from core import models
from core.shared.phase2 import _phase2_build_rows_from_master_export_rows
from core.shared.phase2 import _phase2_build_upload_rows
from core.shared.phase2 import _phase2_export_rows
from core.shared.phase2 import _phase2_get_or_create_default_session
from core.shared.phase2 import _phase2_master_change_state
from core.shared.phase2 import _phase2_master_export_rows
from core.shared.phase2 import _phase2_normalize_text
from core.shared.phase2 import _phase2_parse_number
from core.shared.phase2 import _phase2_preserve_existing_split_state
from core.shared.phase2 import _phase2_preview_sync_state
from core.shared.phase2 import _phase2_reconciliation_checks
from core.shared.phase2 import _phase2_redirect_url
from core.shared.phase2 import _phase2_replace_session_rows
from core.shared.phase2 import _phase2_selected_session
from core.shared.phase2 import _phase2_split_reconciliation
from core.shared.phase2 import _phase2_url_with_extra_params
from core.shared.permissions import RoleRequiredMixin


class SeatAllocationListView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    module_key = models.ModuleKeyChoices.SEAT_ALLOCATION
    permission_action = "view"
    template_name = "seat_allocation/seat_allocation_list.html"
    preserved_filter_keys = ("q", "beneficiary_type", "district_filter", "item_filter", "sort", "dir")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        submit_result = self.request.session.pop("seat_allocation_submit_result", None)
        session = kwargs.get("selected_session") or _phase2_selected_session(self.request)
        all_rows = []
        if session:
            all_rows = list(
                models.SeatAllocationRow.objects.filter(session=session).order_by(
                    "sort_order", "district", "requested_item", "application_number", "id"
                )
            )

        beneficiary_type_filter = (self.request.GET.get("beneficiary_type") or "all").strip()
        q = (self.request.GET.get("q") or "").strip().lower()
        district_filter = (self.request.GET.get("district_filter") or "all").strip()
        item_filter = (self.request.GET.get("item_filter") or "all").strip()
        sort_key = (self.request.GET.get("sort") or "").strip()
        sort_dir = "asc" if (self.request.GET.get("dir") or "asc").lower() == "asc" else "desc"

        normalized_type = _phase2_normalize_text(beneficiary_type_filter)
        is_district_type = normalized_type == "district"
        is_institution_like_type = normalized_type in {"institutions", "others"}

        type_scoped_rows = [
            row for row in all_rows
            if beneficiary_type_filter == "all"
            or (normalized_type == "institutions" and _phase2_normalize_text(row.beneficiary_type) in {"institution", "institutions", "instn"})
            or _phase2_normalize_text(row.beneficiary_type) == normalized_type
        ]
        district_options_source = type_scoped_rows
        if item_filter != "all":
            district_options_source = [row for row in district_options_source if row.requested_item == item_filter]
        if is_district_type:
            district_options = sorted({row.district for row in district_options_source if row.district})
        elif is_institution_like_type:
            district_options = sorted({row.beneficiary_name for row in district_options_source if row.beneficiary_name})
        else:
            district_options = []

        article_options_source = type_scoped_rows
        if district_filter != "all":
            if is_district_type:
                article_options_source = [row for row in article_options_source if row.district == district_filter]
            elif is_institution_like_type:
                article_options_source = [row for row in article_options_source if row.beneficiary_name == district_filter]
        article_options = sorted({row.requested_item for row in article_options_source if row.requested_item})

        rows = type_scoped_rows
        if district_filter != "all":
            if is_district_type:
                rows = [row for row in rows if row.district == district_filter]
            elif is_institution_like_type:
                rows = [row for row in rows if row.beneficiary_name == district_filter]
        if item_filter != "all":
            rows = [row for row in rows if row.requested_item == item_filter]
        if q:
            rows = [
                row for row in rows
                if q in str(row.application_number or "").lower()
                or q in str(row.beneficiary_name or "").lower()
                or q in str(row.district or "").lower()
                or q in str(row.requested_item or "").lower()
                or q in str(row.comments or "").lower()
            ]

        sort_map = {
            "district": lambda row: row.district or "",
            "application_number": lambda row: row.application_number or "",
            "beneficiary_name": lambda row: row.beneficiary_name or "",
            "requested_item": lambda row: row.requested_item or "",
            "quantity": lambda row: int(row.quantity or 0),
            "waiting_hall_quantity": lambda row: int(row.waiting_hall_quantity or 0),
            "token_quantity": lambda row: int(row.token_quantity or 0),
        }
        if sort_key in sort_map:
            rows = sorted(rows, key=sort_map[sort_key], reverse=(sort_dir == "desc"))

        totals = {
            "quantity": sum(int(row.quantity or 0) for row in rows),
            "waiting_hall_quantity": sum(int(row.waiting_hall_quantity or 0) for row in rows),
            "token_quantity": sum(int(row.token_quantity or 0) for row in rows),
        }
        overall_totals = {
            "quantity": sum(int(row.quantity or 0) for row in all_rows),
            "waiting_hall_quantity": sum(int(row.waiting_hall_quantity or 0) for row in all_rows),
            "token_quantity": sum(int(row.token_quantity or 0) for row in all_rows),
        }
        all_rows_count = len(all_rows)
        seat_unique_item_count = len({str(row.requested_item or "").strip() for row in all_rows if str(row.requested_item or "").strip()})
        last_saved_at = None
        if all_rows:
            last_saved_at = max((row.updated_at or row.created_at) for row in all_rows)
        elif session:
            last_saved_at = session.updated_at
        if last_saved_at:
            last_saved_at = timezone.localtime(last_saved_at)
        sync_preview = None
        if session and self.request.GET.get("preview_sync") == "1":
            source_rows = _phase2_master_export_rows()
            preview_upload_result = _phase2_build_rows_from_master_export_rows(source_rows, source_file_name="master-entry-db")
            sync_preview = {
                **_phase2_preview_sync_state(session, preview_upload_result["rows"]),
                "source_row_count": preview_upload_result["source_row_count"],
                "grouped_row_count": preview_upload_result["grouped_row_count"],
            }
        master_change_state = None
        if session:
            source_rows = _phase2_master_export_rows()
            current_master_result = _phase2_build_rows_from_master_export_rows(source_rows, source_file_name="master-entry-db")
            master_change_state = _phase2_master_change_state(session, current_master_result["rows"])
        reconciliation_snapshot = (session.phase2_reconciliation_snapshot or {}) if session else {}
        reconciliation_checks = _phase2_reconciliation_checks(reconciliation_snapshot) if session else []

        def build_sort_params(column):
            params = self.request.GET.copy()
            params["session"] = str(session.pk) if session else ""
            params["sort"] = column
            params["dir"] = "desc" if sort_key == column and sort_dir == "asc" else "asc"
            return params.urlencode()

        context.update(
            {
                "page_title": "Seat Allocation",
                "selected_session": session,
                "event_sessions": list(models.EventSession.objects.order_by("-is_active", "-event_year", "session_name")),
                "seat_rows": rows,
                "totals": totals,
                "overall_totals": overall_totals,
                "percentages": {
                    "waiting_hall": round((totals["waiting_hall_quantity"] / totals["quantity"]) * 100, 1) if totals["quantity"] else 0,
                    "token": round((totals["token_quantity"] / totals["quantity"]) * 100, 1) if totals["quantity"] else 0,
                },
                "all_rows_count": all_rows_count,
                "seat_unique_item_count": seat_unique_item_count,
                "last_saved_at": last_saved_at,
                "filters": {
                    "q": self.request.GET.get("q", ""),
                    "beneficiary_type": beneficiary_type_filter,
                    "district_filter": district_filter,
                    "item_filter": item_filter,
                    "sort": sort_key,
                    "dir": sort_dir,
                },
                "district_options": district_options,
                "article_options": article_options,
                "beneficiary_type_choices": [
                    (models.RecipientTypeChoices.DISTRICT, "District"),
                    (models.RecipientTypeChoices.PUBLIC, "Public"),
                    (models.RecipientTypeChoices.INSTITUTIONS, "Institutions"),
                    (models.RecipientTypeChoices.OTHERS, "Others"),
                    ("all", "All Types"),
                ],
                "is_district_type": is_district_type,
                "is_institution_like_type": is_institution_like_type,
                "sort_querystrings": {
                    "district": build_sort_params("district"),
                    "application_number": build_sort_params("application_number"),
                    "beneficiary_name": build_sort_params("beneficiary_name"),
                    "requested_item": build_sort_params("requested_item"),
                    "quantity": build_sort_params("quantity"),
                    "waiting_hall_quantity": build_sort_params("waiting_hall_quantity"),
                    "token_quantity": build_sort_params("token_quantity"),
                },
                "current_sort": sort_key,
                "current_dir": sort_dir,
                "can_create_edit": self.request.user.has_module_permission(models.ModuleKeyChoices.SEAT_ALLOCATION, "create_edit"),
                "can_export": self.request.user.has_module_permission(models.ModuleKeyChoices.SEAT_ALLOCATION, "export"),
                "can_upload_replace": self.request.user.has_module_permission(models.ModuleKeyChoices.SEAT_ALLOCATION, "upload_replace"),
                "reconciliation": {
                    "source_name": session.phase2_source_name if session else "",
                    "checks": reconciliation_checks,
                    "all_matched": bool(reconciliation_checks) and all(check["matched"] for check in reconciliation_checks),
                    "last_checked_at": timezone.localtime(session.updated_at) if session and reconciliation_snapshot else None,
                },
                "sync_preview": sync_preview,
                "master_change_state": master_change_state,
                "preview_sync_url": _phase2_url_with_extra_params(
                    self.request,
                    "ui:seat-allocation-list",
                    session,
                    filter_keys=self.preserved_filter_keys,
                    extra_params={"preview_sync": "1"},
                ) if session else reverse("ui:seat-allocation-list"),
                "clear_preview_url": _phase2_url_with_extra_params(
                    self.request,
                    "ui:seat-allocation-list",
                    session,
                    filter_keys=self.preserved_filter_keys,
                    extra_params={"preview_sync": None},
                ) if session else reverse("ui:seat-allocation-list"),
                "submit_result": submit_result,
            }
        )
        return context

    def get(self, request, *args, **kwargs):
        session = _phase2_selected_session(request)
        if request.GET.get("export") and session and request.user.has_module_permission(self.module_key, "export"):
            export_rows, export_headers = _phase2_export_rows(
                models.SeatAllocationRow.objects.filter(session=session).order_by(
                    "sort_order", "district", "requested_item", "application_number", "id"
                ),
                include_sequence=False,
            )
            response = HttpResponse(content_type="text/csv")
            timestamp = timezone.localtime().strftime("%d_%b_%y_%H_%M")
            response["Content-Disposition"] = f'attachment; filename="2_Master_Data_Seat_{timestamp}.csv"'
            writer = csv.DictWriter(response, fieldnames=export_headers)
            writer.writeheader()
            for row in export_rows:
                writer.writerow(row)
            return response
        return self.render_to_response(self.get_context_data(selected_session=session))

    def post(self, request, *args, **kwargs):
        action = (request.POST.get("action") or "").strip()
        session = _phase2_selected_session(request)

        if action == "create_session":
            if not request.user.has_module_permission(self.module_key, "create_edit"):
                messages.error(request, "You do not have permission to create sessions.")
                return HttpResponseRedirect(reverse("ui:seat-allocation-list"))
            session_name = (request.POST.get("session_name") or "").strip()
            event_year = _phase2_parse_number(request.POST.get("event_year")) or timezone.localdate().year
            if not session_name:
                messages.error(request, "Enter a session name.")
                return HttpResponseRedirect(reverse("ui:seat-allocation-list"))
            session = models.EventSession.objects.create(
                session_name=session_name,
                event_year=event_year,
                is_active=bool(request.POST.get("is_active")),
                notes=(request.POST.get("notes") or "").strip(),
            )
            messages.success(request, f'Session "{session.session_name}" created.')
            return HttpResponseRedirect(
                _phase2_redirect_url(request, "ui:seat-allocation-list", session, filter_keys=self.preserved_filter_keys)
            )

        if not session and action in {"upload_csv", "use_existing", "sync_data", "save_splits", "submit_splits", "reset_splits", "reset_filtered_splits", "bulk_waiting_full", "bulk_waiting_zero"}:
            session = _phase2_get_or_create_default_session()

        if action == "activate_session":
            if not request.user.has_module_permission(self.module_key, "create_edit"):
                messages.error(request, "You do not have permission to activate sessions.")
                return HttpResponseRedirect(
                    _phase2_redirect_url(request, "ui:seat-allocation-list", session, filter_keys=self.preserved_filter_keys)
                )
            session.is_active = True
            session.save(update_fields=["is_active", "updated_at"])
            messages.success(request, f"{session.session_name} is now the active event session.")
            return HttpResponseRedirect(
                _phase2_redirect_url(request, "ui:seat-allocation-list", session, filter_keys=self.preserved_filter_keys)
            )

        if action == "upload_csv":
            if not request.user.has_module_permission(self.module_key, "upload_replace"):
                messages.error(request, "You do not have permission to upload seat allocation data.")
                return HttpResponseRedirect(
                    _phase2_redirect_url(request, "ui:seat-allocation-list", session, filter_keys=self.preserved_filter_keys)
                )
            uploaded = request.FILES.get("file")
            if not uploaded:
                messages.error(request, "Choose a master-entry export CSV or Excel file.")
                return HttpResponseRedirect(
                    _phase2_redirect_url(request, "ui:seat-allocation-list", session, filter_keys=self.preserved_filter_keys)
                )
            try:
                upload_result = _phase2_build_upload_rows(uploaded)
            except ValueError as exc:
                messages.error(request, str(exc))
                return HttpResponseRedirect(
                    _phase2_redirect_url(request, "ui:seat-allocation-list", session, filter_keys=self.preserved_filter_keys)
                )
            upload_rows = upload_result["rows"]
            _phase2_replace_session_rows(
                session,
                upload_rows,
                source_file_name=uploaded.name,
                user=request.user,
                reconciliation=upload_result,
            )
            messages.success(
                request,
                f"Uploaded {upload_result['source_row_count']} master row(s) into {session.session_name} and created "
                f"{upload_result['grouped_row_count']} seat-allocation working row(s).",
            )
            return HttpResponseRedirect(
                _phase2_url_with_extra_params(
                    request,
                    "ui:seat-allocation-list",
                    session,
                    filter_keys=self.preserved_filter_keys,
                    extra_params={"preview_sync": None},
                )
            )

        if action in {"use_existing", "sync_data"}:
            if not request.user.has_module_permission(self.module_key, "upload_replace"):
                messages.error(request, "You do not have permission to load existing master-entry data.")
                return HttpResponseRedirect(
                    _phase2_redirect_url(request, "ui:seat-allocation-list", session, filter_keys=self.preserved_filter_keys)
                )
            source_rows = _phase2_master_export_rows()
            upload_result = _phase2_build_rows_from_master_export_rows(source_rows, source_file_name="master-entry-db")
            preserve_result = _phase2_preserve_existing_split_state(session, upload_result["rows"])
            upload_rows = preserve_result["rows"]
            _phase2_replace_session_rows(
                session,
                upload_rows,
                source_file_name="master-entry-db",
                user=request.user,
                reconciliation=upload_result,
            )
            messages.success(
                request,
                f"Synced {upload_result['source_row_count']} master row(s) into {upload_result['grouped_row_count']} seat-allocation working row(s). "
                f"Preserved {preserve_result['preserved_count']} existing split row(s), added {preserve_result['new_count']}, removed {preserve_result['removed_count']}.",
            )
            if preserve_result["removed_count"]:
                messages.warning(
                    request,
                    f"Master sync removed {preserve_result['removed_count']} seat-allocation row(s) that no longer exist in master data.",
                )
            return HttpResponseRedirect(
                _phase2_url_with_extra_params(
                    request,
                    "ui:seat-allocation-list",
                    session,
                    filter_keys=self.preserved_filter_keys,
                    extra_params={"preview_sync": None},
                )
            )

        if action == "save_splits":
            if not request.user.has_module_permission(self.module_key, "create_edit"):
                messages.error(request, "You do not have permission to update seat allocation rows.")
                return HttpResponseRedirect(
                    _phase2_redirect_url(request, "ui:seat-allocation-list", session, filter_keys=self.preserved_filter_keys)
                )
            row_ids = request.POST.getlist("row_id")
            waiting_values = request.POST.getlist("waiting_hall_quantity")
            updated_count = 0
            rows_by_id = {
                str(row.id): row
                for row in models.SeatAllocationRow.objects.filter(session=session, id__in=row_ids)
            }
            with transaction.atomic():
                for idx, row_id in enumerate(row_ids):
                    row = rows_by_id.get(str(row_id))
                    if not row:
                        continue
                    waiting_hall_quantity = _phase2_parse_number(waiting_values[idx] if idx < len(waiting_values) else 0)
                    waiting_hall_quantity = min(waiting_hall_quantity, int(row.quantity or 0))
                    row.waiting_hall_quantity = waiting_hall_quantity
                    row.token_quantity = max(int(row.quantity or 0) - waiting_hall_quantity, 0)
                    row.updated_by = request.user
                    row.save(update_fields=["waiting_hall_quantity", "token_quantity", "updated_by", "updated_at"])
                    updated_count += 1
            messages.success(request, f"Saved split values for {updated_count} row(s).")
            return HttpResponseRedirect(
                _phase2_redirect_url(request, "ui:seat-allocation-list", session, filter_keys=self.preserved_filter_keys)
            )

        if action == "submit_splits":
            if not request.user.has_module_permission(self.module_key, "create_edit"):
                messages.error(request, "You do not have permission to validate seat allocation rows.")
                return HttpResponseRedirect(
                    _phase2_redirect_url(request, "ui:seat-allocation-list", session, filter_keys=self.preserved_filter_keys)
                )
            row_ids = request.POST.getlist("row_id")
            waiting_values = request.POST.getlist("waiting_hall_quantity")
            pending_waiting_by_id = {}
            for idx, row_id in enumerate(row_ids):
                raw_value = waiting_values[idx] if idx < len(waiting_values) else 0
                pending_waiting_by_id[str(row_id)] = _phase2_parse_number(raw_value)
            rows_by_id = {
                str(row.id): row
                for row in models.SeatAllocationRow.objects.filter(session=session, id__in=row_ids)
            }
            with transaction.atomic():
                for idx, row_id in enumerate(row_ids):
                    row = rows_by_id.get(str(row_id))
                    if not row:
                        continue
                    waiting_hall_quantity = _phase2_parse_number(waiting_values[idx] if idx < len(waiting_values) else 0)
                    waiting_hall_quantity = min(waiting_hall_quantity, int(row.quantity or 0))
                    row.waiting_hall_quantity = waiting_hall_quantity
                    row.token_quantity = max(int(row.quantity or 0) - waiting_hall_quantity, 0)
                    row.updated_by = request.user
                    row.save(update_fields=["waiting_hall_quantity", "token_quantity", "updated_by", "updated_at"])

            all_rows = list(models.SeatAllocationRow.objects.filter(session=session))
            source_checks = _phase2_reconciliation_checks(session.phase2_reconciliation_snapshot or {})
            split_check = _phase2_split_reconciliation(all_rows)
            source_ok = bool(source_checks) and all(check["matched"] for check in source_checks)
            split_ok = split_check["rowwise_matched"] and split_check["overall_matched"]

            submit_checks = []
            for check in source_checks:
                submit_checks.append(
                    {
                        "label": check["label"],
                        "matched": check["matched"],
                        "details": "Matched" if check["matched"] else f"Master {check['source']}, Working Copy {check['grouped']}",
                    }
                )
            submit_checks.append(
                {
                    "label": "Row-wise split quantities",
                    "matched": split_check["rowwise_matched"],
                    "details": (
                        f"All {split_check['row_count']} row(s) matched"
                        if split_check["rowwise_matched"]
                        else f"{split_check['row_mismatch_count']} row(s) have Quantity != Waiting Hall + Token"
                    ),
                }
            )
            submit_checks.append(
                {
                    "label": "Overall split quantities",
                    "matched": split_check["overall_matched"],
                    "details": f"Waiting Hall {split_check['total_waiting']}, Token {split_check['total_token']}, Total Quantity {split_check['total_quantity']}",
                }
            )

            request.session["seat_allocation_submit_result"] = {
                "all_matched": source_ok and split_ok,
                "checks": submit_checks,
                "checked_at_display": timezone.localtime().strftime("%d/%m/%Y %I:%M %p"),
            }
            return HttpResponseRedirect(
                _phase2_redirect_url(request, "ui:seat-allocation-list", session, filter_keys=self.preserved_filter_keys)
            )

        if action == "reset_splits":
            if not request.user.has_module_permission(self.module_key, "create_edit"):
                messages.error(request, "You do not have permission to reset split values.")
                return HttpResponseRedirect(
                    _phase2_redirect_url(request, "ui:seat-allocation-list", session, filter_keys=self.preserved_filter_keys)
                )
            models.SeatAllocationRow.objects.filter(session=session).update(
                waiting_hall_quantity=0,
                token_quantity=F("quantity"),
                updated_by=request.user,
                updated_at=timezone.now(),
            )
            messages.success(request, "Waiting hall and token quantities were reset.")
            return HttpResponseRedirect(
                _phase2_redirect_url(request, "ui:seat-allocation-list", session, filter_keys=self.preserved_filter_keys)
            )

        if action == "reset_filtered_splits":
            if not request.user.has_module_permission(self.module_key, "create_edit"):
                messages.error(request, "You do not have permission to reset split values.")
                return HttpResponseRedirect(
                    _phase2_redirect_url(request, "ui:seat-allocation-list", session, filter_keys=self.preserved_filter_keys)
                )
            row_ids = request.POST.getlist("visible_row_id")
            rows = list(models.SeatAllocationRow.objects.filter(session=session, id__in=row_ids))
            with transaction.atomic():
                for row in rows:
                    row.waiting_hall_quantity = 0
                    row.token_quantity = int(row.quantity or 0)
                    row.updated_by = request.user
                    row.save(update_fields=["waiting_hall_quantity", "token_quantity", "updated_by", "updated_at"])
            messages.success(request, f"Reset split values for {len(rows)} filtered row(s).")
            return HttpResponseRedirect(
                _phase2_redirect_url(request, "ui:seat-allocation-list", session, filter_keys=self.preserved_filter_keys)
            )

        if action in {"bulk_waiting_full", "bulk_waiting_zero"}:
            if not request.user.has_module_permission(self.module_key, "create_edit"):
                messages.error(request, "You do not have permission to bulk update split values.")
                return HttpResponseRedirect(
                    _phase2_redirect_url(request, "ui:seat-allocation-list", session, filter_keys=self.preserved_filter_keys)
                )
            row_ids = request.POST.getlist("visible_row_id")
            rows = list(models.SeatAllocationRow.objects.filter(session=session, id__in=row_ids))
            with transaction.atomic():
                for row in rows:
                    waiting_value = int(row.quantity or 0) if action == "bulk_waiting_full" else 0
                    row.waiting_hall_quantity = waiting_value
                    row.token_quantity = max(int(row.quantity or 0) - waiting_value, 0)
                    row.updated_by = request.user
                    row.save(update_fields=["waiting_hall_quantity", "token_quantity", "updated_by", "updated_at"])
            messages.success(
                request,
                f'Updated {len(rows)} filtered row(s): Waiting Hall set to {"full quantity" if action == "bulk_waiting_full" else "0"}.',
            )
            return HttpResponseRedirect(
                _phase2_redirect_url(request, "ui:seat-allocation-list", session, filter_keys=self.preserved_filter_keys)
            )

        return HttpResponseRedirect(
            _phase2_redirect_url(request, "ui:seat-allocation-list", session, filter_keys=self.preserved_filter_keys)
        )
