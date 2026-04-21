from __future__ import annotations

"""Views for sequence list workflow."""

import csv

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.db.models import F
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.urls import reverse
from django.utils import timezone
from django.views.generic import TemplateView

from core import models
from core.application_entry.views import EXPORT_COLUMNS
from core.sequence_list.sequence_defaults import SEQUENCE_DEFAULT_ITEMS
from core.shared.csv_utils import _tabular_rows_from_upload
from core.shared.export import _phase2_master_export_rows
from core.shared.export import _sequence_exact_compare
from core.shared.export import _sequence_final_export_rows
from core.shared.export import _sequence_project_rows
from core.shared.export import _sequence_seat_allocation_integrity
from core.shared.phase2 import _phase2_export_rows
from core.shared.phase2 import _phase2_build_rows_from_master_export_rows
from core.shared.phase2 import _phase2_get_or_create_default_session
from core.shared.phase2 import _phase2_normalize_text
from core.shared.phase2 import _phase2_parse_number
from core.shared.phase2 import _phase2_preserve_existing_split_state
from core.shared.phase2 import _phase2_replace_session_rows
from core.shared.phase2 import _phase2_selected_session
from core.shared.permissions import RoleRequiredMixin


class SequenceListView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    module_key = models.ModuleKeyChoices.SEQUENCE_LIST
    permission_action = "view"
    template_name = "sequence_list/sequence_list.html"

    def _master_items(self):
        grouped = {}
        for row in _phase2_master_export_rows():
            item = str(row.get("Requested Item") or "").strip()
            if not item:
                continue
            grouped.setdefault(
                item,
                {
                    "item": item,
                    "category": str(row.get("Article Category") or row.get("Category") or "").strip() or "Uncategorized",
                },
            )
        return list(grouped.values())

    def _uploaded_source_rows_from_file(self, uploaded_file):
        headers, uploaded_rows = _tabular_rows_from_upload(uploaded_file)
        if not headers:
            raise ValueError("Uploaded file is empty.")

        normalized_headers = {_phase2_normalize_text(header): header for header in headers if str(header or "").strip()}

        def find_header(candidates):
            for candidate in candidates:
                match = normalized_headers.get(_phase2_normalize_text(candidate))
                if match:
                    return match
            return None

        item_header = find_header(["Requested Item", "Item", "Article", "Article Name", "requested_item"])
        token_header = find_header(["Token Quantity", "Token Qty", "token_quantity", "Token"])
        sequence_header = find_header(["Sequence No", "Sequence List", "sequence_no", "sequence list"])
        if not item_header:
            raise ValueError("Uploaded file missing item column. Expected Requested Item / Item / Article.")

        source_rows = []
        for source_row in uploaded_rows:
            requested_item = str(source_row.get(item_header) or "").strip()
            if not requested_item:
                continue
            source_rows.append(
                {
                    "requested_item": requested_item,
                    "token_quantity": _phase2_parse_number(source_row.get(token_header)) if token_header else 0,
                    "sequence_no": (_phase2_parse_number(source_row.get(sequence_header)) or None) if sequence_header else None,
                    "row_map": {header: source_row.get(header, "") for header in headers},
                    "headers": headers,
                }
            )
        return {"headers": headers, "rows": source_rows}

    def _source_rows(self, session):
        rows = list(
            models.SeatAllocationRow.objects.filter(session=session).order_by(
                F("sequence_no").asc(nulls_last=True),
                "sort_order",
                "requested_item",
                "application_number",
                "id",
            )
        )
        payload = []
        for row in rows:
            base_headers = [
                header
                for header in (row.master_headers or [])
                if _phase2_normalize_text(header) not in {"waiting hall quantity", "token quantity", "sequence no", "sequence list"}
            ]
            headers = [*base_headers, "Waiting Hall Quantity", "Token Quantity"]
            row_map = {}
            master_row = row.master_row or {}
            for header in base_headers:
                row_map[header] = master_row.get(header, "")
            row_map["Waiting Hall Quantity"] = int(row.waiting_hall_quantity or 0)
            row_map["Token Quantity"] = int(row.token_quantity or 0)
            payload.append(
                {
                    "source_id": str(row.id),
                    "requested_item": row.requested_item or "",
                    "token_quantity": int(row.token_quantity or 0),
                    "sequence_no": int(row.sequence_no) if row.sequence_no else None,
                    "row_map": row_map,
                    "headers": headers,
                }
            )
        return payload

    def _saved_sequence_items(self, session):
        return list(
            models.SequenceListItem.objects.filter(session=session)
            .order_by("sequence_no", "sort_order", "item_name")
            .values("item_name", "sequence_no", "sort_order")
        )

    def _seat_allocation_grouped_rows(self, session):
        rows = list(models.SeatAllocationRow.objects.filter(session=session))
        return [
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
            for row in rows
        ]

    def _sequence_reconciliation_state(self, session):
        master_item_names = {
            str(row.get("item") or "").strip()
            for row in self._master_items()
            if str(row.get("item") or "").strip()
        }
        seat_allocation_items = {
            str(item).strip()
            for item in models.SeatAllocationRow.objects.filter(session=session).values_list("requested_item", flat=True)
            if str(item).strip()
        }
        saved_sequence_items = {
            str(item).strip()
            for item in models.SequenceListItem.objects.filter(session=session).values_list("item_name", flat=True)
            if str(item).strip()
        }
        return {
            "master_items": master_item_names,
            "seat_allocation_items": seat_allocation_items,
            "saved_sequence_items": saved_sequence_items,
            "missing_in_seat_allocation": sorted(master_item_names - seat_allocation_items),
            "extra_in_seat_allocation": sorted(seat_allocation_items - master_item_names),
            "new_to_sequence": sorted(master_item_names - saved_sequence_items),
            "extra_in_sequence": sorted(saved_sequence_items - master_item_names),
        }

    def _sequence_submit_result(self, *, reconciliation_state, sequence_item_names, sequence_number_count, exact_checks, seat_integrity):
        master_item_count = len(reconciliation_state["master_items"])
        seat_item_count = len(reconciliation_state["seat_allocation_items"])
        sequence_item_count = len(sequence_item_names)
        missing_in_seat = reconciliation_state["missing_in_seat_allocation"]
        extra_in_seat = reconciliation_state["extra_in_seat_allocation"]
        unassigned_master = sorted(reconciliation_state["master_items"] - sequence_item_names)
        extra_in_sequence = sorted(sequence_item_names - reconciliation_state["master_items"])
        split_check = seat_integrity["split_check"]
        base_integrity_ok = (
            all(check["matched"] for check in seat_integrity["checks"])
            and split_check["rowwise_matched"]
            and split_check["overall_matched"]
            and exact_checks["master_match"]["matched"]
            and exact_checks["seat_match"]["matched"]
        )

        checks = [
            {
                "label": "Final data integrity",
                "matched": base_integrity_ok,
                "details": (
                    "Master Data, Seat Allocation, split totals, and final sequence output all matched."
                    if base_integrity_ok
                    else "One or more Master Data / Seat Allocation / split / final output checks failed."
                ),
            },
            *[
                {
                    "label": f"Master Data vs Seat Allocation {check['label']}",
                    "matched": check["matched"],
                    "details": (
                        f"Matched {check['source']}"
                        if check["matched"]
                        else f"Master {check['source']}, Seat Allocation {check['grouped']}"
                    ),
                }
                for check in seat_integrity["checks"]
            ],
            {
                "label": "Seat Allocation row-wise split",
                "matched": split_check["rowwise_matched"],
                "details": (
                    f"All {split_check['row_count']} row(s) matched"
                    if split_check["rowwise_matched"]
                    else f"{split_check['row_mismatch_count']} row(s) have Quantity != Waiting Hall + Token"
                ),
            },
            {
                "label": "Seat Allocation overall split",
                "matched": split_check["overall_matched"],
                "details": (
                    f"Waiting Hall {split_check['total_waiting']}, Token {split_check['total_token']}, Total Quantity {split_check['total_quantity']}"
                ),
            },
            {
                "label": "Final Sequence vs Master Data",
                "matched": exact_checks["master_match"]["matched"],
                "details": exact_checks["master_match"]["details"],
            },
            {
                "label": "Final Sequence vs Seat Allocation",
                "matched": exact_checks["seat_match"]["matched"],
                "details": exact_checks["seat_match"]["details"],
            },
            {
                "label": "Master Data items vs Sequence List",
                "matched": not unassigned_master and not extra_in_sequence,
                "details": (
                    f"Matched {master_item_count} item(s)"
                    if not unassigned_master and not extra_in_sequence
                    else " | ".join(
                        part
                        for part in [
                            (
                                f"Unassigned master item(s): {', '.join(unassigned_master[:5])}"
                                + (f" and {len(unassigned_master) - 5} more" if len(unassigned_master) > 5 else "")
                            ) if unassigned_master else "",
                            (
                                f"Removed/stale sequence item(s): {', '.join(extra_in_sequence[:5])}"
                                + (f" and {len(extra_in_sequence) - 5} more" if len(extra_in_sequence) > 5 else "")
                            ) if extra_in_sequence else "",
                        ]
                        if part
                    ),
                ),
            },
            {
                "label": "Item uniqueness",
                "matched": sequence_item_count == len(sequence_item_names),
                "details": f"{len(sequence_item_names)} unique item(s) in Sequence List",
            },
            {
                "label": "Sequence number uniqueness",
                "matched": sequence_number_count == sequence_item_count,
                "details": (
                    f"{sequence_number_count} unique sequence number(s) for {sequence_item_count} item(s)"
                    if sequence_number_count == sequence_item_count
                    else f"{sequence_number_count} unique sequence number(s) for {sequence_item_count} item(s)"
                ),
            },
            {
                "label": "Sequence coverage on Seat Allocation",
                "matched": seat_item_count == sequence_item_count and not missing_in_seat and not extra_in_seat,
                "details": (
                    f"Sequence will apply to all {seat_item_count} Seat Allocation item(s)"
                    if seat_item_count == sequence_item_count and not missing_in_seat and not extra_in_seat
                    else f"Seat Allocation items: {seat_item_count}, Sequence items: {sequence_item_count}"
                ),
            },
        ]
        return {
            "all_matched": all(check["matched"] for check in checks),
            "checks": checks,
            "checked_at_display": timezone.localtime().strftime("%d/%m/%Y %I:%M %p"),
        }

    def _item_summaries(self, session):
        rows = list(
            models.SeatAllocationRow.objects.filter(session=session).order_by(
                "sequence_no", "requested_item", "application_number", "id"
            )
        )
        include_only_token = (self.request.GET.get("token_only") or "").strip() == "1"
        if include_only_token:
            rows = [row for row in rows if int(row.token_quantity or 0) > 0]

        q = (self.request.GET.get("q") or "").strip().lower()
        grouped = {}
        for row in rows:
            item = (row.requested_item or "").strip()
            if not item:
                continue
            summary = grouped.setdefault(
                item,
                {
                    "item": item,
                    "beneficiary_type": row.beneficiary_type or "",
                    "item_type": row.item_type or "",
                    "row_count": 0,
                    "quantity": 0,
                    "waiting_hall_quantity": 0,
                    "token_quantity": 0,
                    "sequence_no": row.sequence_no,
                },
            )
            summary["row_count"] += 1
            summary["quantity"] += int(row.quantity or 0)
            summary["waiting_hall_quantity"] += int(row.waiting_hall_quantity or 0)
            summary["token_quantity"] += int(row.token_quantity or 0)
            if summary["sequence_no"] in {None, ""} and row.sequence_no:
                summary["sequence_no"] = row.sequence_no

        items = list(grouped.values())
        if q:
            items = [
                item for item in items
                if q in str(item["item"]).lower()
                or q in str(item["beneficiary_type"]).lower()
                or q in str(item["item_type"]).lower()
            ]
        items.sort(key=lambda item: (item["sequence_no"] is None, item["sequence_no"] or 999999, item["item"].lower()))
        return items

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        session = kwargs.get("selected_session") or _phase2_selected_session(self.request)
        items = self._item_summaries(session) if session else []
        submit_result = self.request.session.pop("sequence_submit_result", None)
        context.update(
            {
                "page_title": "Sequence List",
                "selected_session": session,
                "event_sessions": list(models.EventSession.objects.order_by("-is_active", "-event_year", "session_name")),
                "sequence_items": items,
                "sequence_source_rows": self._source_rows(session) if session else [],
                "sequence_saved_items": self._saved_sequence_items(session) if session else [],
                "sequence_master_items": self._master_items(),
                "sequence_source_name": session.phase2_source_name if session else "",
                "sequence_source_is_uploaded": bool(session and session.phase2_source_name and session.phase2_source_name != "master-entry-db"),
                "sequence_default_items": SEQUENCE_DEFAULT_ITEMS,
                "filters": {
                    "q": self.request.GET.get("q", ""),
                    "token_only": self.request.GET.get("token_only", ""),
                    "start_from": self.request.GET.get("start_from", "1"),
                },
                "can_create_edit": self.request.user.has_module_permission(models.ModuleKeyChoices.SEQUENCE_LIST, "create_edit"),
                "can_export": self.request.user.has_module_permission(models.ModuleKeyChoices.SEQUENCE_LIST, "export"),
                "sequence_reconciliation_state": self._sequence_reconciliation_state(session) if session else {},
                "submit_result": submit_result,
            }
        )
        return context

    def get(self, request, *args, **kwargs):
        session = _phase2_selected_session(request)
        if request.GET.get("export") and session and request.user.has_module_permission(self.module_key, "export"):
            export_rows, export_headers = _phase2_export_rows(
                models.SeatAllocationRow.objects.filter(session=session).order_by(
                    F("sequence_no").asc(nulls_last=True),
                    "sort_order",
                    "requested_item",
                    "application_number",
                    "id",
                ),
                include_sequence=True,
            )
            response = HttpResponse(content_type="text/csv")
            timestamp = timezone.localtime().strftime("%d_%b_%y_%H_%M")
            response["Content-Disposition"] = f'attachment; filename="3_Master_Data_Seq_{timestamp}.csv"'
            writer = csv.DictWriter(response, fieldnames=export_headers)
            writer.writeheader()
            for row in export_rows:
                writer.writerow(row)
            return response
        return self.render_to_response(self.get_context_data(selected_session=session))

    def post(self, request, *args, **kwargs):
        session = _phase2_selected_session(request)
        action = (request.POST.get("action") or "").strip()
        if action == "sync_data" and not session:
            session = _phase2_get_or_create_default_session()
        if not session:
            messages.error(request, "Create or select a session first.")
            return HttpResponseRedirect(reverse("ui:sequence-list"))
        if not request.user.has_module_permission(self.module_key, "create_edit"):
            messages.error(request, "You do not have permission to update sequence rows.")
            return HttpResponseRedirect(f'{reverse("ui:sequence-list")}?session={session.pk}')
        start_from = _phase2_parse_number(request.POST.get("start_from")) or 1

        if action == "sync_data":
            source_rows = _phase2_master_export_rows()
            upload_result = _phase2_build_rows_from_master_export_rows(source_rows, source_file_name="master-entry-db")
            preserve_result = _phase2_preserve_existing_split_state(session, upload_result["rows"])
            _phase2_replace_session_rows(
                session,
                preserve_result["rows"],
                source_file_name="master-entry-db",
                user=request.user,
                reconciliation=upload_result,
            )
            messages.success(
                request,
                f"Synced {upload_result['source_row_count']} master row(s) into {upload_result['grouped_row_count']} seat-allocation working row(s). "
                f"Preserved {preserve_result['preserved_count']} existing split row(s), added {preserve_result['new_count']}, removed {preserve_result['removed_count']}.",
            )
            return HttpResponseRedirect(f'{reverse("ui:sequence-list")}?session={session.pk}')

        if action == "parse_upload":
            uploaded_file = request.FILES.get("file")
            if not uploaded_file:
                return JsonResponse({"error": "Choose a CSV or Excel file to upload."}, status=400)
            try:
                upload_result = self._uploaded_source_rows_from_file(uploaded_file)
            except ValueError as exc:
                return JsonResponse({"error": str(exc)}, status=400)
            return JsonResponse(
                {
                    "rows": upload_result["rows"],
                    "file_name": uploaded_file.name,
                    "source_label": "Loaded Uploaded File",
                }
            )

        if action == "auto_assign":
            items = self._item_summaries(session)
            existing_sequences = {int(item["sequence_no"]) for item in items if item["sequence_no"]}
            next_sequence = start_from
            for item in items:
                if item["sequence_no"]:
                    continue
                while next_sequence in existing_sequences:
                    next_sequence += 1
                models.SeatAllocationRow.objects.filter(session=session, requested_item=item["item"]).update(
                    sequence_no=next_sequence,
                    updated_by=request.user,
                    updated_at=timezone.now(),
                )
                existing_sequences.add(next_sequence)
                next_sequence += 1
            messages.success(request, "Blank sequence numbers were assigned.")
            return HttpResponseRedirect(f'{reverse("ui:sequence-list")}?session={session.pk}')

        if action == "save_sequences":
            item_names = request.POST.getlist("item_name")
            sequence_values = request.POST.getlist("sequence_no")
            attempted_sequence_names = {str(item_name or "").strip() for item_name in item_names if str(item_name or "").strip()}
            attempted_sequence_numbers = {
                _phase2_parse_number(raw_value)
                for raw_value in sequence_values
                if str(raw_value).strip() and _phase2_parse_number(raw_value)
            }
            reconciliation_state = self._sequence_reconciliation_state(session)
            seat_integrity = _sequence_seat_allocation_integrity(session)
            submitted_rows = []
            seen_items = set()
            seen_sequences = set()
            validation_errors = []

            for idx, item_name in enumerate(item_names):
                item_name = str(item_name or "").strip()
                raw_value = sequence_values[idx] if idx < len(sequence_values) else ""
                if not item_name:
                    continue
                if item_name in seen_items:
                    validation_errors.append(f"Duplicate item in sequence list: {item_name}.")
                    continue
                sequence_no = _phase2_parse_number(raw_value) if str(raw_value).strip() else None
                if not sequence_no:
                    validation_errors.append(f"Missing sequence number for {item_name}.")
                    continue
                if sequence_no in seen_sequences:
                    validation_errors.append(f"Sequence number {sequence_no} is used more than once.")
                    continue
                seen_items.add(item_name)
                seen_sequences.add(sequence_no)
                submitted_rows.append(
                    {
                        "item_name": item_name,
                        "sequence_no": sequence_no,
                        "sort_order": idx + 1,
                    }
                )

            sequence_map = {row["item_name"]: row["sequence_no"] for row in submitted_rows}
            final_export = _sequence_final_export_rows(session, sequence_map)
            master_export_rows = _phase2_master_export_rows()
            exact_checks = {
                "master_match": _sequence_exact_compare(
                    left_rows=_sequence_project_rows(final_export["final_rows"], EXPORT_COLUMNS),
                    left_headers=EXPORT_COLUMNS,
                    right_rows=_sequence_project_rows(master_export_rows, EXPORT_COLUMNS),
                    right_headers=EXPORT_COLUMNS,
                    matched_label=f"Matched {len(master_export_rows)} row(s) across {len(EXPORT_COLUMNS)} column(s)",
                    mismatch_label="Master Data comparison failed",
                ),
                "seat_match": _sequence_exact_compare(
                    left_rows=_sequence_project_rows(final_export["final_rows"], final_export["seat_headers"]),
                    left_headers=final_export["seat_headers"],
                    right_rows=final_export["seat_rows"],
                    right_headers=final_export["seat_headers"],
                    matched_label=f"Matched {len(final_export['seat_rows'])} row(s) across {len(final_export['seat_headers'])} column(s)",
                    mismatch_label="Seat Allocation comparison failed",
                ),
            }

            if validation_errors:
                request.session["sequence_submit_result"] = {
                    "all_matched": False,
                    "checks": [
                        *[
                            {
                                "label": f"Master Data vs Seat Allocation {check['label']}",
                                "matched": check["matched"],
                                "details": (
                                    f"Matched {check['source']}"
                                    if check["matched"]
                                    else f"Master {check['source']}, Seat Allocation {check['grouped']}"
                                ),
                            }
                            for check in seat_integrity["checks"]
                        ],
                        {
                            "label": "Seat Allocation row-wise split",
                            "matched": seat_integrity["split_check"]["rowwise_matched"],
                            "details": (
                                f"All {seat_integrity['split_check']['row_count']} row(s) matched"
                                if seat_integrity["split_check"]["rowwise_matched"]
                                else f"{seat_integrity['split_check']['row_mismatch_count']} row(s) have Quantity != Waiting Hall + Token"
                            ),
                        },
                        {
                            "label": "Seat Allocation overall split",
                            "matched": seat_integrity["split_check"]["overall_matched"],
                            "details": (
                                f"Waiting Hall {seat_integrity['split_check']['total_waiting']}, Token {seat_integrity['split_check']['total_token']}, Total Quantity {seat_integrity['split_check']['total_quantity']}"
                            ),
                        },
                        {
                            "label": "Final Sequence vs Master Data",
                            "matched": exact_checks["master_match"]["matched"],
                            "details": exact_checks["master_match"]["details"],
                        },
                        {
                            "label": "Final Sequence vs Seat Allocation",
                            "matched": exact_checks["seat_match"]["matched"],
                            "details": exact_checks["seat_match"]["details"],
                        },
                        {
                            "label": "Sequence validation",
                            "matched": False,
                            "details": validation_errors[0],
                        }
                    ],
                    "checked_at_display": timezone.localtime().strftime("%d/%m/%Y %I:%M %p"),
                }
                return HttpResponseRedirect(f'{reverse("ui:sequence-list")}?session={session.pk}')

            with transaction.atomic():
                master_item_names = reconciliation_state["master_items"]
                sequence_item_names = {row["item_name"] for row in submitted_rows}
                unassigned_master_items = sorted(master_item_names - sequence_item_names)
                extra_sequence_items = sorted(sequence_item_names - master_item_names)
                submit_result = self._sequence_submit_result(
                    reconciliation_state=reconciliation_state,
                    sequence_item_names=sequence_item_names,
                    sequence_number_count=len(seen_sequences),
                    exact_checks=exact_checks,
                    seat_integrity=seat_integrity,
                )

                models.SequenceListItem.objects.filter(session=session).delete()
                models.SequenceListItem.objects.bulk_create(
                    [
                        models.SequenceListItem(
                            session=session,
                            item_name=row["item_name"],
                            sequence_no=row["sequence_no"],
                            sort_order=row["sort_order"],
                            created_by=request.user,
                            updated_by=request.user,
                        )
                        for row in submitted_rows
                    ]
                )

                source_is_uploaded = bool(session.phase2_source_name and session.phase2_source_name != "master-entry-db")
                allow_apply = source_is_uploaded or (submit_result["all_matched"] and not unassigned_master_items and not extra_sequence_items)
                if allow_apply:
                    models.SeatAllocationRow.objects.filter(session=session).update(
                        sequence_no=None,
                        updated_by=request.user,
                        updated_at=timezone.now(),
                    )
                    for row in submitted_rows:
                        models.SeatAllocationRow.objects.filter(
                            session=session,
                            requested_item=row["item_name"],
                        ).update(
                            sequence_no=row["sequence_no"],
                            updated_by=request.user,
                            updated_at=timezone.now(),
                        )
                    if source_is_uploaded and not submit_result["all_matched"]:
                        messages.warning(
                            request,
                            "Sequence list was applied to the uploaded Seat Allocation working copy. Current Master Data reconciliation still shows differences.",
                        )
                else:
                    messages.warning(
                        request,
                        "Sequence list was saved, but it was not applied to Seat Allocation because reconciliation is not clean yet.",
                    )
                request.session["sequence_submit_result"] = submit_result
            return HttpResponseRedirect(f'{reverse("ui:sequence-list")}?session={session.pk}')

        return HttpResponseRedirect(f'{reverse("ui:sequence-list")}?session={session.pk}')
