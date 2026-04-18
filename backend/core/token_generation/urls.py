from __future__ import annotations

"""Route map for token generation workflow."""

from django.urls import path

from .views import TokenGenerationView

urlpatterns = [
    path("token-generation/", TokenGenerationView.as_view(), name="token-generation"),
]
