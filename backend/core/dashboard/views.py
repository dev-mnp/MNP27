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

from .services import build_dashboard_metrics


class DashboardView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    """Render and update dashboard-level metrics and event budget."""

    allowed_roles = {"admin", "editor", "viewer"}
    template_name = "dashboard/dashboard.html"

    def post(self, request, *args, **kwargs):
        if request.user.role not in {"admin", "editor"}:
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
        context.update(
            {
                "metrics": metrics,
                "overall_event_budget": overall_event_budget,
                "balance_to_allot": overall_event_budget - metrics["overall"]["total_value_accrued"],
                "can_edit_event_budget": self.request.user.role in {"admin", "editor"},
            }
        )
        return context
