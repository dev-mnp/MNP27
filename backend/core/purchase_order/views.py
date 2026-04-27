from __future__ import annotations

"""Views and helpers for purchase order workflow."""

import json

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.db.models import CharField, Q
from django.db.models.functions import Cast
from django.forms import inlineformset_factory
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from core import models
from core.purchase_order import services
from core.purchase_order.forms import PurchaseOrderForm, PurchaseOrderItemForm
from core.shared.audit import get_request_audit_meta
from core.shared.audit import log_audit
from core.shared.permissions import AdminRequiredMixin, RoleRequiredMixin, WriteRoleMixin


def _is_editable_purchase_order(user, purchase_order):
    if not user or not user.is_authenticated:
        return False
    if not user.has_module_permission(models.ModuleKeyChoices.PURCHASE_ORDER, "create_edit"):
        return False
    return purchase_order.status == models.FundRequestStatusChoices.DRAFT


PurchaseOrderItemFormSet = inlineformset_factory(
    models.PurchaseOrder,
    models.PurchaseOrderItem,
    form=PurchaseOrderItemForm,
    extra=0,
    can_delete=True,
)


def _purchase_order_sequence(value):
    raw = str(value or "").strip().upper()
    prefix = "MASM/MNP"
    if not raw.startswith(prefix):
        return None
    suffix = raw[len(prefix):]
    if len(suffix) != 5 or not suffix.isdigit():
        return None
    return int(suffix[:3])


def _purchase_order_article_choices():
    return [
        {
            "name": article.article_name,
            "label": article.article_name,
            "article_id": article.id,
            "default_price": str(article.cost_per_unit or 0),
            "pending_qty": 0,
        }
        for article in models.Article.objects.filter(
            item_type=models.ItemTypeChoices.ARTICLE,
            is_active=True,
        ).order_by("article_name")
    ]


class PurchaseOrderListView(LoginRequiredMixin, RoleRequiredMixin, ListView):
    module_key = models.ModuleKeyChoices.PURCHASE_ORDER
    permission_action = "view"
    model = models.PurchaseOrder
    template_name = "purchase_order/purchase_order_list.html"
    context_object_name = "purchase_orders"
    paginate_by = 20

    def get_queryset(self):
        queryset = (
            models.PurchaseOrder.objects
            .select_related("created_by")
            .prefetch_related("items", "items__article")
        )
        self._sort_key = (self.request.GET.get("sort") or "created_at").strip()
        self._sort_dir = (self.request.GET.get("dir") or "desc").strip().lower()
        if q := (self.request.GET.get("q") or "").strip():
            matching_ids = (
                models.PurchaseOrder.objects
                .annotate(
                    total_amount_text=Cast("total_amount", output_field=CharField()),
                    created_at_text=Cast("created_at", output_field=CharField()),
                    item_quantity_text=Cast("items__quantity", output_field=CharField()),
                    item_unit_price_text=Cast("items__unit_price", output_field=CharField()),
                    item_total_text=Cast("items__total_value", output_field=CharField()),
                )
                .filter(
                    Q(purchase_order_number__icontains=q)
                    | Q(vendor_name__icontains=q)
                    | Q(vendor_address__icontains=q)
                    | Q(vendor_city__icontains=q)
                    | Q(vendor_state__icontains=q)
                    | Q(vendor_pincode__icontains=q)
                    | Q(comments__icontains=q)
                    | Q(status__icontains=q)
                    | Q(total_amount_text__icontains=q)
                    | Q(created_at_text__icontains=q)
                    | Q(created_by__email__icontains=q)
                    | Q(created_by__first_name__icontains=q)
                    | Q(created_by__last_name__icontains=q)
                    | Q(items__article_name__icontains=q)
                    | Q(items__supplier_article_name__icontains=q)
                    | Q(items__description__icontains=q)
                    | Q(item_quantity_text__icontains=q)
                    | Q(item_unit_price_text__icontains=q)
                    | Q(item_total_text__icontains=q)
                )
                .values_list("pk", flat=True)
                .distinct()
            )
            queryset = queryset.filter(pk__in=matching_ids)

        if status := (self.request.GET.get("status") or "").strip():
            queryset = queryset.filter(status=status)

        sort_field_map = {
            "purchase_order_number": "purchase_order_number",
            "vendor_name": "vendor_name",
            "vendor_city": "vendor_city",
            "total_amount": "total_amount",
            "status": "status",
            "created_at": "created_at",
        }
        sort_field = sort_field_map.get(self._sort_key, "created_at")
        sort_prefix = "" if self._sort_dir == "asc" else "-"
        if sort_field == "purchase_order_number":
            rows = list(queryset.order_by(f"{sort_prefix}created_at", f"{sort_prefix}id"))
            rows.sort(
                key=lambda po: (
                    _purchase_order_sequence(po.purchase_order_number) is None,
                    _purchase_order_sequence(po.purchase_order_number) or 0,
                    po.created_at,
                    po.id,
                ),
                reverse=(self._sort_dir == "desc"),
            )
            return rows
        return queryset.order_by(f"{sort_prefix}{sort_field}", "-id")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        current_sort = getattr(self, "_sort_key", "created_at")
        current_dir = getattr(self, "_sort_dir", "desc")

        for purchase_order in context["purchase_orders"]:
            purchase_order.item_count = purchase_order.items.count()
            purchase_order.items_total_quantity = sum(int(item.quantity or 0) for item in purchase_order.items.all())
            purchase_order.display_comments = (purchase_order.comments or "").strip() or models.PURCHASE_ORDER_DEFAULT_COMMENTS

        def build_sort_params(column):
            params = self.request.GET.copy()
            params.pop("page", None)
            next_dir = "asc"
            if current_sort == column and current_dir == "asc":
                next_dir = "desc"
            params["sort"] = column
            params["dir"] = next_dir
            return params.urlencode()

        context["status_choices"] = [
            ("", "All"),
            (models.FundRequestStatusChoices.DRAFT, "Draft"),
            (models.FundRequestStatusChoices.SUBMITTED, "Submitted"),
        ]
        context["filters"] = {
            "q": self.request.GET.get("q", ""),
            "status": self.request.GET.get("status", ""),
        }
        context["current_sort"] = current_sort
        context["current_dir"] = current_dir
        context["sort_querystrings"] = {
            "purchase_order_number": build_sort_params("purchase_order_number"),
            "vendor_name": build_sort_params("vendor_name"),
            "total_amount": build_sort_params("total_amount"),
            "status": build_sort_params("status"),
            "created_at": build_sort_params("created_at"),
        }
        context["can_create_edit"] = self.request.user.has_module_permission(models.ModuleKeyChoices.PURCHASE_ORDER, "create_edit")
        context["can_submit"] = self.request.user.has_module_permission(models.ModuleKeyChoices.PURCHASE_ORDER, "submit")
        context["can_reopen"] = self.request.user.has_module_permission(models.ModuleKeyChoices.PURCHASE_ORDER, "reopen")
        context["can_delete"] = self.request.user.has_module_permission(models.ModuleKeyChoices.PURCHASE_ORDER, "delete")
        return context


class PurchaseOrderCreateUpdateMixin(WriteRoleMixin):
    module_key = models.ModuleKeyChoices.PURCHASE_ORDER
    permission_action = "create_edit"
    form_class = PurchaseOrderForm
    template_name = "purchase_order/purchase_order_form.html"
    model = models.PurchaseOrder
    success_url = reverse_lazy("ui:purchase-order-list")

    def _build_formset(self, instance: models.PurchaseOrder | None = None):
        return PurchaseOrderItemFormSet(self.request.POST or None, prefix="items", instance=instance)

    def _can_edit(self, purchase_order: models.PurchaseOrder):
        return _is_editable_purchase_order(self.request.user, purchase_order)

    def dispatch(self, request, *args, **kwargs):
        self.object = getattr(self, "object", None)
        if self.object and not self._can_edit(self.object):
            messages.error(request, "Submitted purchase orders must be reopened before editing.")
            return HttpResponseRedirect(reverse("ui:purchase-order-list"))
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["item_formset"] = kwargs.get("item_formset", None) or self._build_formset(self.object)
        context["article_request_choices_json"] = json.dumps(_purchase_order_article_choices())
        return context

    def _resolve_article_record(self, article_name: str):
        article_name = (article_name or "").strip()
        if not article_name:
            return None
        return models.Article.objects.filter(article_name__iexact=article_name).first()

    def _validate_header_fields(self, form, purchase_order, action):
        if action != "submit":
            return True
        valid = True
        for field_name, label in [
            ("vendor_name", "Vendor Name"),
            ("vendor_address", "Vendor Address"),
            ("vendor_city", "City"),
            ("vendor_state", "State"),
            ("vendor_pincode", "Pincode"),
        ]:
            value = getattr(purchase_order, field_name, None)
            if not str(value or "").strip():
                form.add_error(field_name, f"{label} is required for submit.")
                valid = False
        return valid

    def _validate_item_formset(self, item_formset, action):
        active_forms = [form for form in item_formset.forms if form.cleaned_data and not form.cleaned_data.get("DELETE", False)]
        if action == "submit" and not active_forms:
            item_formset._non_form_errors = item_formset.error_class(["Add at least one item."])
            return False
        valid = True
        if action == "submit":
            for form in active_forms:
                for field_name in ["article_name", "supplier_article_name", "description", "quantity", "unit_price"]:
                    value = form.cleaned_data.get(field_name)
                    if value in (None, "", 0, "0"):
                        form.add_error(field_name, "Required for submit.")
                        valid = False
        return valid

    def form_valid(self, form):
        action = self.request.POST.get("action", "draft")
        if action == "submit" and self.object and self.object.status != models.FundRequestStatusChoices.DRAFT:
            messages.error(self.request, "Only draft purchase orders can be submitted.")
            return HttpResponseRedirect(self.get_success_url())

        purchase_order = form.save(commit=False)
        if self.object and self.object.purchase_order_number:
            purchase_order.purchase_order_number = self.object.purchase_order_number
        if not purchase_order.created_by:
            purchase_order.created_by = self.request.user
        purchase_order.status = (
            models.FundRequestStatusChoices.SUBMITTED
            if action == "submit"
            else models.FundRequestStatusChoices.DRAFT
        )

        header_ok = self._validate_header_fields(form, purchase_order, action)
        item_formset = self._build_formset(purchase_order)
        formsets_ok = item_formset.is_valid()
        items_ok = self._validate_item_formset(item_formset, action)
        if not header_ok or not formsets_ok or not items_ok:
            messages.error(self.request, "Please fix errors in purchase order fields before saving.")
            return self.render_to_response(self.get_context_data(form=form, item_formset=item_formset))

        with transaction.atomic():
            if action == "submit" and not purchase_order.purchase_order_number:
                purchase_order.purchase_order_number = services.next_purchase_order_number()
            purchase_order.save()

            item_formset.instance = purchase_order
            for deleted_form in getattr(item_formset, "deleted_forms", []):
                deleted_instance = getattr(deleted_form, "instance", None)
                if deleted_instance and deleted_instance.pk:
                    deleted_instance.delete()
            item_instances = item_formset.save(commit=False)
            for item in item_instances:
                item.purchase_order = purchase_order
                if not item.article_id:
                    item.article = self._resolve_article_record(item.article_name)
                if item.article and not item.article_name:
                    item.article_name = item.article.article_name
                item.quantity = item.quantity or 0
                item.unit_price = item.unit_price or 0
                item.total_value = (item.unit_price or 0) * (item.quantity or 0)
                item.save()

            services.sync_purchase_order_totals(purchase_order)
            self.object = purchase_order

        messages.success(
            self.request,
            "Purchase order submitted." if action == "submit" else "Purchase order saved as draft.",
        )
        return HttpResponseRedirect(self.get_success_url())


class PurchaseOrderCreateView(LoginRequiredMixin, PurchaseOrderCreateUpdateMixin, CreateView):
    pass


class PurchaseOrderUpdateView(LoginRequiredMixin, PurchaseOrderCreateUpdateMixin, UpdateView):
    def get_queryset(self):
        return models.PurchaseOrder.objects.all()


class PurchaseOrderPDFView(LoginRequiredMixin, RoleRequiredMixin, View):
    module_key = models.ModuleKeyChoices.PURCHASE_ORDER
    permission_action = "view"

    def get(self, request, pk):
        purchase_order = get_object_or_404(
            models.PurchaseOrder.objects.select_related("created_by").prefetch_related("items"),
            pk=pk,
        )
        services.ensure_purchase_order_number(purchase_order)
        pdf_buffer = services.generate_purchase_order_pdf(purchase_order)
        filename_base = purchase_order.purchase_order_number or f"PO-DRAFT-{purchase_order.pk}"
        response = HttpResponse(pdf_buffer.getvalue(), content_type="application/pdf")
        response["Content-Disposition"] = f'inline; filename="{filename_base}.pdf"'
        response["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response["Pragma"] = "no-cache"
        response["Expires"] = "0"
        return response


class PurchaseOrderSubmitView(LoginRequiredMixin, WriteRoleMixin, View):
    module_key = models.ModuleKeyChoices.PURCHASE_ORDER
    permission_action = "submit"
    allowed_roles = {"admin", "editor"}

    def post(self, request, pk):
        purchase_order = get_object_or_404(models.PurchaseOrder, pk=pk)
        if not request.user.has_module_permission(self.module_key, "submit"):
            return HttpResponse("Forbidden", status=403)
        if purchase_order.status != models.FundRequestStatusChoices.DRAFT:
            messages.error(request, "Only draft purchase orders can be submitted.")
            return HttpResponseRedirect(reverse("ui:purchase-order-list"))
        purchase_order.status = models.FundRequestStatusChoices.SUBMITTED
        if not purchase_order.purchase_order_number:
            purchase_order.purchase_order_number = services.next_purchase_order_number()
        purchase_order.save(update_fields=["status", "purchase_order_number"])
        log_audit(
            user=request.user,
            action_type=models.ActionTypeChoices.STATUS_CHANGE,
            entity_type="purchase_order",
            entity_id=str(purchase_order.id),
            details={"status": models.FundRequestStatusChoices.SUBMITTED},
            **get_request_audit_meta(request),
        )
        services.sync_purchase_order_totals(purchase_order)
        messages.success(request, "Purchase order submitted.")
        return HttpResponseRedirect(reverse("ui:purchase-order-list"))


class PurchaseOrderReopenView(LoginRequiredMixin, AdminRequiredMixin, View):
    module_key = models.ModuleKeyChoices.PURCHASE_ORDER
    permission_action = "reopen"

    def post(self, request, pk):
        purchase_order = get_object_or_404(models.PurchaseOrder, pk=pk)
        if purchase_order.status != models.FundRequestStatusChoices.SUBMITTED:
            messages.error(request, "Only submitted purchase orders can be reopened.")
            return HttpResponseRedirect(reverse("ui:purchase-order-list"))
        previous_status = purchase_order.status
        purchase_order.status = models.FundRequestStatusChoices.DRAFT
        purchase_order.save(update_fields=["status"])
        log_audit(
            user=request.user,
            action_type=models.ActionTypeChoices.STATUS_CHANGE,
            entity_type="purchase_order",
            entity_id=str(purchase_order.id),
            details={"from": previous_status, "to": models.FundRequestStatusChoices.DRAFT},
            **get_request_audit_meta(request),
        )
        messages.success(request, "Purchase order reopened as draft.")
        return HttpResponseRedirect(reverse("ui:purchase-order-edit", args=[purchase_order.pk]))


class PurchaseOrderDeleteView(LoginRequiredMixin, AdminRequiredMixin, DeleteView):
    module_key = models.ModuleKeyChoices.PURCHASE_ORDER
    permission_action = "delete"
    model = models.PurchaseOrder
    template_name = "purchase_order/purchase_order_confirm_delete.html"
    success_url = reverse_lazy("ui:purchase-order-list")

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        messages.warning(self.request, "Purchase order deleted.")
        return super().post(request, *args, **kwargs)
