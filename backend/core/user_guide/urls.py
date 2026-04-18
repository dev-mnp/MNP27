from __future__ import annotations

"""Route map for user guide pages."""

from django.urls import path

from .views import UserGuideView

urlpatterns = [
    path("user-guide/", UserGuideView.as_view(), name="user-guide"),
]
