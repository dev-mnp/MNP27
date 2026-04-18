from __future__ import annotations

"""Route map for sequence list workflow."""

from django.urls import path

from .views import SequenceListView

urlpatterns = [
    path("sequence-list/", SequenceListView.as_view(), name="sequence-list"),
]
