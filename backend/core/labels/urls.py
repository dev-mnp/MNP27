from __future__ import annotations

"""Route map for labels workflow."""

from django.urls import path

from .views import LabelGenerationView

urlpatterns = [
    path("labels/", LabelGenerationView.as_view(), name="labels"),
]
