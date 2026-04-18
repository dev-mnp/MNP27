from __future__ import annotations

"""URL routes for the vendor management business module."""

from django.urls import path

from .views import VendorCreateView, VendorDeleteView, VendorInlineCreateView, VendorListView, VendorUpdateView

urlpatterns = [
    path("vendors/", VendorListView.as_view(), name="vendor-list"),
    path("vendors/new/", VendorCreateView.as_view(), name="vendor-create"),
    path("vendors/inline-create/", VendorInlineCreateView.as_view(), name="vendor-inline-create"),
    path("vendors/<int:pk>/edit/", VendorUpdateView.as_view(), name="vendor-edit"),
    path("vendors/<int:pk>/delete/", VendorDeleteView.as_view(), name="vendor-delete"),
]
