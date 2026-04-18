from __future__ import annotations

"""Views for inventory planning (order management) screens."""

import csv

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.utils import timezone
from django.views.generic import TemplateView

from core import models
from core.shared.inventory import build_order_management_rows
from core.shared.permissions import RoleRequiredMixin


def _order_management_metrics(rows):
    metrics = []
    for item_type in models.ItemTypeChoices:
        typed_rows = [row for row in rows if row["item_type"] == item_type.value]
        metrics.append(
            {
                "label": item_type.label,
                "count": len(typed_rows),
                "needed": sum(row["total_quantity"] for row in typed_rows),
                "ordered": sum(row["quantity_ordered"] for row in typed_rows),
                "pending": sum(row["quantity_pending"] for row in typed_rows),
                "excess": sum(row["quantity_excess"] for row in typed_rows),
            }
        )
    return metrics


def _partition_order_management_rows_by_application_status(rows, application_status_filter):
    if not application_status_filter:
        return rows

    status_priority = [
        models.BeneficiaryStatusChoices.SUBMITTED,
        models.BeneficiaryStatusChoices.DRAFT,
    ]

    partitioned_rows = []
    for row in rows:
        all_beneficiaries = row["beneficiaries"]
        beneficiaries = [
            item for item in all_beneficiaries
            if (item.get("application_status") or item.get("status") or "") == application_status_filter
        ]
        if not beneficiaries:
            continue

        filtered_row = dict(row)
        filtered_row["beneficiaries"] = beneficiaries
        filtered_row["breakdown"] = {"district": 0, "public": 0, "institutions": 0}
        filtered_row["total_quantity"] = 0
        filtered_row["quantity_ordered"] = 0
        filtered_row["quantity_pending"] = 0
        filtered_row["quantity_excess"] = 0
        filtered_row["statuses"] = {application_status_filter}
        filtered_row["source_status"] = application_status_filter
        filtered_row["order_statuses"] = {item.get("order_status") or "" for item in beneficiaries}

        quantities_by_status = {status: 0 for status in status_priority}
        for item in all_beneficiaries:
            item_status = (item.get("application_status") or item.get("status") or "").strip()
            if item_status in quantities_by_status:
                quantities_by_status[item_status] += int(item.get("quantity") or 0)

        filtered_total_quantity = sum(int(item.get("quantity") or 0) for item in beneficiaries)
        ordered_pool = int(row.get("quantity_ordered") or 0)

        if application_status_filter == models.BeneficiaryStatusChoices.SUBMITTED:
            ordered_for_filtered = min(ordered_pool, filtered_total_quantity)
        elif application_status_filter == models.BeneficiaryStatusChoices.DRAFT:
            ordered_after_submitted = max(
                ordered_pool - quantities_by_status.get(models.BeneficiaryStatusChoices.SUBMITTED, 0),
                0,
            )
            ordered_for_filtered = min(ordered_after_submitted, filtered_total_quantity)
        else:
            ordered_reserved_for_prior = 0
            for status in status_priority:
                if status == application_status_filter:
                    break
                ordered_reserved_for_prior += quantities_by_status.get(status, 0)
            ordered_for_filtered = min(max(ordered_pool - ordered_reserved_for_prior, 0), filtered_total_quantity)

        filtered_row["quantity_ordered"] = ordered_for_filtered
        filtered_row["quantity_pending"] = max(filtered_total_quantity - ordered_for_filtered, 0)

        for item in beneficiaries:
            quantity = int(item.get("quantity") or 0)
            filtered_row["total_quantity"] += quantity
            if item.get("beneficiary_type") == "District":
                filtered_row["breakdown"]["district"] += quantity
            elif item.get("beneficiary_type") == "Public":
                filtered_row["breakdown"]["public"] += quantity
            else:
                filtered_row["breakdown"]["institutions"] += quantity
        filtered_row["beneficiary_names_display"] = ", ".join(
            f'{item["beneficiary_type"]}: {item["beneficiary_name"]}' for item in beneficiaries
        )
        partitioned_rows.append(filtered_row)

    return partitioned_rows


def _partition_order_management_rows_by_order_status(rows, order_status_filter):
    if not order_status_filter:
        return rows

    partitioned_rows = []
    for row in rows:
        beneficiaries = [
            item for item in row["beneficiaries"]
            if (item.get("order_status") or "") == order_status_filter
        ]
        if not beneficiaries:
            continue

        filtered_row = dict(row)
        filtered_row["beneficiaries"] = beneficiaries
        filtered_row["breakdown"] = {"district": 0, "public": 0, "institutions": 0}
        filtered_row["total_quantity"] = 0
        filtered_row["quantity_ordered"] = 0
        filtered_row["quantity_pending"] = 0
        filtered_row["quantity_excess"] = 0
        filtered_row["order_statuses"] = {order_status_filter}

        statuses = {item.get("status") or "" for item in beneficiaries if item.get("status")}
        filtered_row["statuses"] = statuses
        if models.BeneficiaryStatusChoices.SUBMITTED in statuses:
            filtered_row["source_status"] = models.BeneficiaryStatusChoices.SUBMITTED
        elif models.BeneficiaryStatusChoices.DRAFT in statuses:
            filtered_row["source_status"] = models.BeneficiaryStatusChoices.DRAFT
        else:
            filtered_row["source_status"] = ""

        for item in beneficiaries:
            quantity = int(item.get("quantity") or 0)
            filtered_row["total_quantity"] += quantity
            if item.get("beneficiary_type") == "District":
                filtered_row["breakdown"]["district"] += quantity
            elif item.get("beneficiary_type") == "Public":
                filtered_row["breakdown"]["public"] += quantity
            else:
                filtered_row["breakdown"]["institutions"] += quantity

            ordered_quantity = int(item.get("ordered_quantity") or 0)
            if order_status_filter == "Fund Raised":
                filtered_row["quantity_ordered"] += ordered_quantity
            elif order_status_filter == "Partial":
                filtered_row["quantity_ordered"] += ordered_quantity
                filtered_row["quantity_pending"] += max(quantity - ordered_quantity, 0)
            else:
                filtered_row["quantity_pending"] += quantity

        filtered_row["beneficiary_names_display"] = ", ".join(
            f'{item["beneficiary_type"]}: {item["beneficiary_name"]}' for item in beneficiaries
        )
        partitioned_rows.append(filtered_row)

    return partitioned_rows


class OrderManagementView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    module_key = models.ModuleKeyChoices.INVENTORY_PLANNING
    permission_action = "view"
    template_name = "inventory_planning/order_management.html"

    def get(self, request, *args, **kwargs):
        if (request.GET.get("export") or "").strip().lower() == "csv":
            return self._export_csv()
        return super().get(request, *args, **kwargs)

    def _get_all_rows(self):
        cache_name = "_order_management_all_rows"
        if hasattr(self, cache_name):
            return getattr(self, cache_name)
        rows = build_order_management_rows()
        setattr(self, cache_name, rows)
        return rows

    def _get_filtered_rows(self):
        rows = self._get_all_rows()
        status_filter = self.request.GET.get("status")
        if status_filter is None:
            status_filter = ""
        status_filter = status_filter.strip()
        order_status_filter = (self.request.GET.get("order_status") or "").strip()
        combo_filter = (self.request.GET.get("combo") or "").strip()
        balance_filter = (self.request.GET.get("balance") or "").strip()
        q = (self.request.GET.get("q") or "").strip().casefold()
        item_type = (self.request.GET.get("item_type") or "").strip()
        rows = _partition_order_management_rows_by_application_status(rows, status_filter)
        rows = _partition_order_management_rows_by_order_status(rows, order_status_filter)
        if combo_filter == "combo":
            rows = [row for row in rows if row["combo_related"]]
        elif combo_filter == "separate":
            rows = [row for row in rows if not row["combo_related"]]
        if q:
            rows = [
                row for row in rows
                if q in row["article_name"].casefold()
                or q in row["source_items_display"].casefold()
                or q in row["beneficiary_names_display"].casefold()
                or any(
                    q in item["application_number"].casefold()
                    or q in item["beneficiary_name"].casefold()
                    for item in row["beneficiaries"]
                )
            ]
        if item_type:
            rows = [row for row in rows if row["item_type"] == item_type]
        if balance_filter == "pending":
            rows = [row for row in rows if row["quantity_pending"] > 0]
        elif balance_filter == "excess":
            rows = [row for row in rows if row["quantity_excess"] > 0]

        sort = (self.request.GET.get("sort") or "article_name").strip()
        direction = (self.request.GET.get("dir") or "asc").strip().lower()
        allowed_sorts = {
            "article_name": lambda row: row["article_name"].casefold(),
            "total_quantity": lambda row: row["total_quantity"],
            "quantity_ordered": lambda row: row["quantity_ordered"],
            "quantity_pending": lambda row: row["quantity_pending"],
            "district": lambda row: row["breakdown"]["district"],
            "public": lambda row: row["breakdown"]["public"],
            "institutions": lambda row: row["breakdown"]["institutions"],
        }
        sort_key = allowed_sorts.get(sort, allowed_sorts["article_name"])
        rows = sorted(rows, key=sort_key, reverse=(direction == "desc"))
        previous_combo_related = None
        for index, row in enumerate(rows):
            row["group_break_before"] = index > 0 and previous_combo_related != row["combo_related"]
            previous_combo_related = row["combo_related"]
        return rows

    def _query_string_without_page(self):
        params = self.request.GET.copy()
        return params.urlencode()

    def _query_string_without(self, *keys):
        params = self.request.GET.copy()
        for key in keys:
            if key in params:
                del params[key]
        return params.urlencode()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        all_rows = self._get_all_rows()
        rows = self._get_filtered_rows()
        article_rows = [row for row in all_rows if row["item_type"] == models.ItemTypeChoices.ARTICLE]
        aid_rows = [row for row in all_rows if row["item_type"] == models.ItemTypeChoices.AID]
        project_rows = [row for row in all_rows if row["item_type"] == models.ItemTypeChoices.PROJECT]
        context.update(
            {
                "rows": rows,
                "metrics": _order_management_metrics(all_rows),
                "item_type_choices": models.ItemTypeChoices.choices,
                "status_choices": [
                    ("", "All"),
                    (models.BeneficiaryStatusChoices.DRAFT, "Draft"),
                    (models.BeneficiaryStatusChoices.SUBMITTED, "Submitted"),
                ],
                "combo_choices": [
                    ("", "All"),
                    ("separate", "Separate"),
                    ("combo", "Combo / Split"),
                ],
                "order_status_choices": [
                    ("", "All"),
                    ("Fund Raised", "Fund Raised"),
                    ("Partial", "Partial"),
                    ("No", "No"),
                ],
                "balance_choices": [
                    ("", "All"),
                    ("pending", "Pending"),
                    ("excess", "Excess"),
                ],
                "filters": {
                    "q": self.request.GET.get("q", ""),
                    "item_type": self.request.GET.get("item_type", ""),
                    "status": (self.request.GET.get("status") if self.request.GET.get("status") is not None else ""),
                    "order_status": self.request.GET.get("order_status", ""),
                    "combo": self.request.GET.get("combo", ""),
                    "balance": self.request.GET.get("balance", ""),
                },
                "current_sort": (self.request.GET.get("sort") or "article_name").strip(),
                "current_dir": (self.request.GET.get("dir") or "asc").strip().lower(),
                "query_string_without_page": self._query_string_without_page(),
                "query_string_without_sort": self._query_string_without("sort", "dir", "export"),
                "article_count": len(article_rows),
                "aid_count": len(aid_rows),
                "project_count": len(project_rows),
                "all_item_count": len(all_rows),
                "filtered_item_count": len(rows),
            }
        )
        return context

    def _export_csv(self):
        rows = self._get_filtered_rows()
        export_mode = (self.request.GET.get("export_mode") or "overview").strip().lower()
        if export_mode not in {"overview", "complete"}:
            export_mode = "overview"
        timestamp = timezone.localtime().strftime("%Y_%m_%d_%I_%M_%p")
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = f'attachment; filename="inventory-planning-{export_mode}_{timestamp}.csv"'
        writer = csv.writer(response)
        if export_mode == "complete":
            writer.writerow(
                [
                    "Order Item",
                    "Item Type",
                    "Combo / Separate",
                    "Application Status Filtered",
                    "Source Items",
                    "Total Quantity Needed",
                    "Quantity Ordered",
                    "Quantity Pending",
                    "Quantity Excess",
                    "District",
                    "Public",
                    "Institutions & Others",
                    "Beneficiary Type",
                    "Application Number",
                    "Beneficiary",
                    "Beneficiary Quantity",
                    "Application Status",
                    "Order Status",
                    "Source Item",
                    "Notes",
                ]
            )
            for row in rows:
                beneficiaries = row["beneficiaries"] or [None]
                for item in beneficiaries:
                    writer.writerow(
                        [
                            row["article_name"],
                            row["item_type"],
                            "Combo / Split" if row["combo_related"] else "Separate",
                            row.get("source_status", ""),
                            row["source_items_display"],
                            row["total_quantity"],
                            row["quantity_ordered"],
                            row["quantity_pending"],
                            row["quantity_excess"],
                            row["breakdown"]["district"],
                            row["breakdown"]["public"],
                            row["breakdown"]["institutions"],
                            item.get("beneficiary_type") if item else "",
                            item.get("application_number") if item else "",
                            item.get("beneficiary_name") if item else "",
                            item.get("quantity") if item else "",
                            item.get("application_status") if item else "",
                            item.get("order_status") if item else "",
                            item.get("source_item") if item else "",
                            item.get("notes") if item else "",
                        ]
                    )
            return response

        writer.writerow(
            [
                "Order Item",
                "Item Type",
                "Combo / Separate",
                "Source Status",
                "Source Items",
                "Beneficiaries",
                "Total Quantity Needed",
                "Quantity Ordered",
                "Quantity Pending",
                "Quantity Excess",
                "District",
                "Public",
                "Institutions & Others",
            ]
        )
        for row in rows:
            writer.writerow(
                [
                    row["article_name"],
                    row["item_type"],
                    "Combo / Split" if row["combo_related"] else "Separate",
                    row.get("source_status", ""),
                    row["source_items_display"],
                    row["beneficiary_names_display"],
                    row["total_quantity"],
                    row["quantity_ordered"],
                    row["quantity_pending"],
                    row["quantity_excess"],
                    row["breakdown"]["district"],
                    row["breakdown"]["public"],
                    row["breakdown"]["institutions"],
                ]
            )
        return response

