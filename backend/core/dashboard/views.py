from __future__ import annotations

"""Dashboard page views for the dashboard business module."""

from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.views.generic import TemplateView

from core import models
from core.shared.permissions import RoleRequiredMixin
from core.shared.phase2 import _phase2_selected_session

from .services import build_dashboard_metrics, build_seat_allocation_quantity_tree


class DashboardView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    """Render and update dashboard-level metrics and event budget."""

    allowed_roles = {"admin", "editor", "viewer"}
    module_key = models.ModuleKeyChoices.DASHBOARD
    permission_action = "view"
    template_name = "dashboard/dashboard.html"

    def post(self, request, *args, **kwargs):
        if not request.user.has_module_permission(self.module_key, "create_edit"):
            messages.error(request, "You do not have permission to update the event budget.")
            return HttpResponseRedirect(reverse("ui:dashboard"))
        budget_raw = (request.POST.get("event_budget") or "").strip().replace(",", "")
        try:
            event_budget = Decimal(budget_raw or "0")
            if event_budget < 0:
                raise InvalidOperation
        except (InvalidOperation, ValueError):
            messages.error(request, "Enter a valid event budget amount.")
            return HttpResponseRedirect(reverse("ui:dashboard"))
        setting = models.DashboardSetting.objects.order_by("pk").first()
        if setting is None:
            models.DashboardSetting.objects.create(event_budget=event_budget, updated_by=request.user)
        else:
            setting.event_budget = event_budget
            setting.updated_by = request.user
            setting.save(update_fields=["event_budget", "updated_by", "updated_at"])
        messages.success(request, "Event budget updated.")
        return HttpResponseRedirect(reverse("ui:dashboard"))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        metrics = build_dashboard_metrics()
        setting = models.DashboardSetting.objects.order_by("pk").first()
        overall_event_budget = setting.event_budget if setting else metrics["district"]["total_allotted_fund"]
        selected_session = _phase2_selected_session(self.request)
        can_view_dashboard_page_2 = self.request.user.has_module_permission(
            models.ModuleKeyChoices.DASHBOARD, "view_page_2"
        )
        quantity_tree = build_seat_allocation_quantity_tree(selected_session) if can_view_dashboard_page_2 else None
        show_page_2 = bool(can_view_dashboard_page_2 and quantity_tree)
        requested_page = (self.request.GET.get("page") or "1").strip()
        dashboard_page = "2" if show_page_2 and requested_page == "2" else "1"
        context.update(
            {
                "metrics": metrics,
                "overall_event_budget": overall_event_budget,
                "balance_to_allot": overall_event_budget - metrics["overall"]["total_value_accrued"],
                "can_edit_event_budget": self.request.user.has_module_permission(self.module_key, "create_edit"),
                "can_view_dashboard_page_2": can_view_dashboard_page_2,
                "dashboard_page": dashboard_page,
                "show_dashboard_page_2": show_page_2,
                "quantity_tree": quantity_tree,
                "selected_session": selected_session,
            }
        )
        return context
