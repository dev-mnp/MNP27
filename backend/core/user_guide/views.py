from __future__ import annotations

"""Views for user guide pages."""

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView

from core import models
from core.shared.permissions import RoleRequiredMixin


class UserGuideView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    module_key = models.ModuleKeyChoices.USER_GUIDE
    permission_action = "view"
    template_name = "user_guide/user_guide.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "page_title": "User Guide",
            }
        )
        return context
