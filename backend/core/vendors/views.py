from __future__ import annotations

"""Views for vendor list, create, update, and export workflows."""

import csv
import json

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.urls import reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from core import models
from core.shared.permissions import AdminRequiredMixin, RoleRequiredMixin, WriteRoleMixin
from core.vendors.forms import VendorForm


class VendorListView(LoginRequiredMixin, RoleRequiredMixin, ListView):
    module_key = models.ModuleKeyChoices.VENDORS
    permission_action = "view"
    model = models.Vendor
    template_name = "vendors/vendor_list.html"
    context_object_name = "vendors"

    def get(self, request, *args, **kwargs):
        if (request.GET.get("export") or "").strip().lower() == "csv":
            return self._export_csv()
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        queryset = models.Vendor.objects.order_by("vendor_name")
        q = (self.request.GET.get("q") or "").strip()
        if q:
            queryset = queryset.filter(
                Q(vendor_name__icontains=q)
                | Q(gst_number__icontains=q)
                | Q(phone_number__icontains=q)
                | Q(city__icontains=q)
                | Q(state__icontains=q)
                | Q(pincode__icontains=q)
                | Q(cheque_in_favour__icontains=q)
            )
        active = (self.request.GET.get("active") or "").strip()
        if active == "active":
            queryset = queryset.filter(is_active=True)
        elif active == "inactive":
            queryset = queryset.filter(is_active=False)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["filters"] = {
            "q": self.request.GET.get("q", ""),
            "active": self.request.GET.get("active", ""),
        }
        params = self.request.GET.copy()
        params.pop("page", None)
        context["query_string_without_page"] = params.urlencode()
        context["can_create_edit"] = self.request.user.has_module_permission(self.module_key, "create_edit")
        context["can_delete"] = self.request.user.has_module_permission(self.module_key, "delete")
        return context

    def _export_csv(self):
        response = HttpResponse(content_type="text/csv")
        timestamp = timezone.localtime().strftime("%Y_%m_%d_%I_%M_%p")
        response["Content-Disposition"] = f'attachment; filename="vendors_{timestamp}.csv"'
        writer = csv.writer(response)
        writer.writerow(
            [
                "Vendor Name",
                "GST Number",
                "Phone Number",
                "Address",
                "City",
                "State",
                "Pincode",
                "Cheque / RTGS in Favour",
                "Status",
                "Created At",
                "Updated At",
            ]
        )
        for vendor in self.get_queryset():
            writer.writerow(
                [
                    vendor.vendor_name,
                    vendor.gst_number or "",
                    vendor.phone_number or "",
                    vendor.address or "",
                    vendor.city or "",
                    vendor.state or "",
                    vendor.pincode or "",
                    vendor.cheque_in_favour or "",
                    "Active" if vendor.is_active else "Inactive",
                    timezone.localtime(vendor.created_at).strftime("%d/%m/%Y %H:%M"),
                    timezone.localtime(vendor.updated_at).strftime("%d/%m/%Y %H:%M"),
                ]
            )
        return response


class VendorCreateView(LoginRequiredMixin, WriteRoleMixin, CreateView):
    module_key = models.ModuleKeyChoices.VENDORS
    permission_action = "create_edit"
    model = models.Vendor
    form_class = VendorForm
    template_name = "vendors/vendor_form.html"
    success_url = reverse_lazy("ui:vendor-list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["popup_mode"] = self.request.GET.get("popup") == "1"
        return context

    def form_valid(self, form):
        self.object = form.save()
        if self.request.GET.get("popup") == "1":
            payload = json.dumps(
                {
                    "id": self.object.id,
                    "vendor_name": self.object.vendor_name,
                    "gst_no": self.object.gst_number or "",
                    "vendor_address": self.object.address or "",
                    "vendor_city": self.object.city or "",
                    "vendor_state": self.object.state or "",
                    "vendor_pincode": self.object.pincode or "",
                    "phone_number": self.object.phone_number or "",
                    "cheque_in_favour": self.object.cheque_in_favour or "",
                }
            ).replace("</", "<\\/")
            return HttpResponse(
                f"""<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>Vendor created</title></head>
<body style="font-family: Poppins, Segoe UI, Arial, sans-serif; padding: 24px;">
  <div>Vendor created. Returning to fund request…</div>
  <script>
    (function() {{
      var vendor = {payload};
      if (window.opener && !window.opener.closed && typeof window.opener.handleVendorCreated === "function") {{
        window.opener.handleVendorCreated(vendor);
        try {{ window.opener.focus(); }} catch (error) {{}}
        window.close();
        return;
      }}
      document.body.innerHTML = "<p>Vendor created. You can close this window now.</p>";
    }})();
  </script>
</body>
</html>"""
            )
        messages.success(self.request, "Vendor created.")
        return HttpResponseRedirect(self.get_success_url())


class VendorUpdateView(LoginRequiredMixin, WriteRoleMixin, UpdateView):
    module_key = models.ModuleKeyChoices.VENDORS
    permission_action = "create_edit"
    model = models.Vendor
    form_class = VendorForm
    template_name = "vendors/vendor_form.html"
    success_url = reverse_lazy("ui:vendor-list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["popup_mode"] = False
        return context

    def form_valid(self, form):
        messages.success(self.request, "Vendor updated.")
        return super().form_valid(form)


class VendorDeleteView(LoginRequiredMixin, AdminRequiredMixin, DeleteView):
    module_key = models.ModuleKeyChoices.VENDORS
    permission_action = "delete"
    model = models.Vendor
    template_name = "vendors/vendor_confirm_delete.html"
    success_url = reverse_lazy("ui:vendor-list")

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        messages.warning(self.request, f"Vendor '{self.object.vendor_name}' deleted.")
        return super().post(request, *args, **kwargs)


class VendorInlineCreateView(LoginRequiredMixin, WriteRoleMixin, View):
    module_key = models.ModuleKeyChoices.VENDORS
    permission_action = "create_edit"

    def post(self, request, *args, **kwargs):
        form = VendorForm(request.POST)
        if not form.is_valid():
            return JsonResponse({"ok": False, "errors": form.errors.get_json_data()}, status=400)
        vendor = form.save()
        return JsonResponse(
            {
                "ok": True,
                "vendor": {
                    "id": vendor.id,
                    "vendor_name": vendor.vendor_name,
                    "gst_no": vendor.gst_number or "",
                    "vendor_address": vendor.address or "",
                    "vendor_city": vendor.city or "",
                    "vendor_state": vendor.state or "",
                    "vendor_pincode": vendor.pincode or "",
                    "phone_number": vendor.phone_number or "",
                    "cheque_in_favour": vendor.cheque_in_favour or "",
                },
            }
        )
