from __future__ import annotations

"""Views for application audit logs."""

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.views.generic import ListView

from core import models
from core.shared.permissions import AdminRequiredMixin


AUDIT_FIELD_LABELS = {
    "district_name": "District",
    "president_name": "President",
    "mobile_number": "Mobile Number",
    "allotted_budget": "Allotted Budget",
    "name": "Name",
    "aadhar_number": "Aadhaar Number",
    "is_handicapped": "Disability Category",
    "gender": "Gender",
    "female_status": "Gender Category",
    "address": "Address",
    "mobile": "Mobile Number",
    "article_name": "Requested Item",
    "item_type": "Item Type",
    "quantity": "Quantity",
    "unit_cost": "Unit Price",
    "total_amount": "Total Value",
    "cheque_rtgs_in_favour": "Cheque / RTGS in Favour",
    "notes": "Comments",
    "internal_notes": "Internal Notes",
    "institution_name": "Institution Name",
    "institution_type": "Institution Type",
    "total_value": "Total Value",
}


def _application_audit_label(log):
    details = log.details or {}
    after = details.get("after") or {}
    before = details.get("before") or {}
    snapshot = after or before
    if log.entity_type == "district_application":
        return snapshot.get("application_number") or snapshot.get("district_name") or log.entity_id or "-"
    if log.entity_type == "public_application":
        application_number = snapshot.get("application_number") or log.entity_id or "-"
        name = snapshot.get("name") or ""
        return f"{application_number} - {name}".strip(" -")
    if log.entity_type == "institution_application":
        application_number = snapshot.get("application_number") or log.entity_id or "-"
        name = snapshot.get("institution_name") or ""
        return f"{application_number} - {name}".strip(" -")
    return log.entity_id or "-"


def _format_audit_value(value):
    if value is None or value == "":
        return "-"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    return str(value)


def _audit_user_label(user):
    if not user:
        return "System"
    if user.first_name:
        return user.first_name
    return user.email


def _audit_item_key(item):
    if item.get("id"):
        return ("id", str(item.get("id")))
    return ("article", item.get("article_id") or "", item.get("article_name") or "")


def _application_audit_change_lines(log):
    details = log.details or {}
    before = details.get("before") or {}
    after = details.get("after") or {}

    if log.action_type == models.ActionTypeChoices.CREATE:
        item_count = after.get("item_count")
        if item_count is not None:
            return [f"Created with {item_count} item(s)."]
        return ["Created application."]

    if log.action_type == models.ActionTypeChoices.DELETE:
        item_count = before.get("item_count")
        if item_count is not None:
            return [f"Deleted application with {item_count} item(s)."]
        return ["Deleted application."]

    change_lines = []
    for key, label in AUDIT_FIELD_LABELS.items():
        if key in {"article_name", "item_type", "quantity", "unit_cost", "total_amount", "notes"}:
            continue
        before_value = before.get(key)
        after_value = after.get(key)
        if before_value != after_value and (before_value is not None or after_value is not None):
            change_lines.append(f"{label}: {_format_audit_value(before_value)} -> {_format_audit_value(after_value)}")

    before_items = before.get("items") or []
    after_items = after.get("items") or []
    before_map = {_audit_item_key(item): item for item in before_items}
    after_map = {_audit_item_key(item): item for item in after_items}

    shared_keys = [key for key in before_map.keys() if key in after_map]
    added = [item for key, item in after_map.items() if key not in before_map]
    removed = [item for key, item in before_map.items() if key not in after_map]

    for key in shared_keys:
        before_item = before_map[key]
        after_item = after_map[key]
        item_changes = []
        for field in ["quantity", "unit_cost", "total_amount", "notes"]:
            if before_item.get(field) != after_item.get(field):
                item_changes.append(
                    f"{AUDIT_FIELD_LABELS[field]}: {_format_audit_value(before_item.get(field))} -> {_format_audit_value(after_item.get(field))}"
                )
        if item_changes:
            change_lines.append(f'{after_item.get("article_name")}: ' + "; ".join(item_changes))

    for item in added:
        change_lines.append(f'Added item: {item.get("article_name")} ({item.get("quantity")} x {_format_audit_value(item.get("unit_cost"))})')
    for item in removed:
        change_lines.append(f'Removed item: {item.get("article_name")}')

    return change_lines or ["No visible field changes recorded."]


class ApplicationAuditLogListView(LoginRequiredMixin, AdminRequiredMixin, ListView):
    module_key = models.ModuleKeyChoices.AUDIT_LOGS
    permission_action = "view"
    model = models.AuditLog
    template_name = "audit_logs/application_audit_logs.html"
    context_object_name = "audit_logs"
    paginate_by = 50

    def get_queryset(self):
        queryset = models.AuditLog.objects.select_related("user").filter(
            entity_type__in=[
                "district_application",
                "public_application",
                "institution_application",
            ]
        ).order_by("-created_at")
        q = (self.request.GET.get("q") or "").strip()
        application_type = (self.request.GET.get("application_type") or "").strip()
        user_id = (self.request.GET.get("user_id") or "").strip()
        date_from = (self.request.GET.get("date_from") or "").strip()
        date_to = (self.request.GET.get("date_to") or "").strip()
        if q:
            queryset = queryset.filter(
                Q(entity_type__icontains=q)
                | Q(entity_id__icontains=q)
                | Q(action_type__icontains=q)
                | Q(user__email__icontains=q)
                | Q(user__first_name__icontains=q)
                | Q(user__last_name__icontains=q)
            )
        if application_type:
            queryset = queryset.filter(entity_type=application_type)
        if user_id:
            queryset = queryset.filter(user_id=user_id)
        if date_from:
            queryset = queryset.filter(created_at__date__gte=date_from)
        if date_to:
            queryset = queryset.filter(created_at__date__lte=date_to)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["search_query"] = (self.request.GET.get("q") or "").strip()
        context["application_type"] = (self.request.GET.get("application_type") or "").strip()
        context["selected_user_id"] = (self.request.GET.get("user_id") or "").strip()
        context["date_from"] = (self.request.GET.get("date_from") or "").strip()
        context["date_to"] = (self.request.GET.get("date_to") or "").strip()
        context["application_type_choices"] = [
            ("district_application", "District Application"),
            ("public_application", "Public Application"),
            ("institution_application", "Institution Application"),
        ]
        context["audit_users"] = (
            models.AppUser.objects.filter(
                audit_logs__entity_type__in=[
                    "district_application",
                    "public_application",
                    "institution_application",
                ]
            )
            .distinct()
            .order_by("first_name", "email")
        )
        context["audit_rows"] = [
            {
                "log": log,
                "application_label": _application_audit_label(log),
                "change_lines": _application_audit_change_lines(log),
                "user_label": _audit_user_label(log.user),
            }
            for log in context["audit_logs"]
        ]
        return context
