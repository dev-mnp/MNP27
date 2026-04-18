from __future__ import annotations

"""Views for user guide pages."""

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView


class UserGuideView(LoginRequiredMixin, TemplateView):
    template_name = "user_guide/user_guide.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "page_title": "User Guide",
            }
        )
        return context
