from __future__ import annotations

"""URL routes for seat allocation module."""

from django.urls import path

from .views import SeatAllocationListView

urlpatterns = [
    path("seat-allocation/", SeatAllocationListView.as_view(), name="seat-allocation-list"),
]

