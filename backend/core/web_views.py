from __future__ import annotations

"""
Server-rendered UI views, helper functions, list filtering, and form workflows.

This is the main file to inspect when changing the behavior of the Django
templates under ``templates/dashboard/``.
"""

import csv
import base64
import json
import uuid
import io
import os
import mimetypes
from decimal import Decimal, InvalidOperation
from openpyxl import Workbook
from openpyxl.utils import get_column_letter
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib import messages
from django.db import IntegrityError, transaction
from django.db.models import CharField, Q
from django.db.models.functions import Cast
from django.http import FileResponse, Http404, HttpResponse, HttpResponseRedirect, JsonResponse
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    FormView,
    ListView,
    TemplateView,
    UpdateView,
)
from django.shortcuts import get_object_or_404
from django.forms import inlineformset_factory

from . import models
from . import services
from .forms import (
    AppUserCreateForm,
    AppUserPasswordResetForm,
    AppUserUpdateForm,
    ArticleForm,
    ApplicationAttachmentUploadForm,
    FundRequestDocumentUploadForm,
    FundRequestForm,
    FundRequestArticleForm,
    FundRequestRecipientForm,
    MasterDataUploadForm,
    PurchaseOrderForm,
    PurchaseOrderItemForm,
)

FEMALE_STATUS_DESCRIPTIONS = {
    "Single": "A woman who is unmarried and not currently in a marital relationship.",
    "Married": "A woman who is currently married.",
    "Widowed": "A woman whose spouse has died.",
    "Divorced": "A woman whose marriage has been legally dissolved.",
    "Separated": "A woman living apart from her spouse without a finalized divorce.",
    "Deserted": "A woman abandoned by her spouse without support.",
    "Single Mother": "A woman raising one or more children without a partner in the household.",
    "Destitute Woman (no income/support)": "A woman without stable income, family support, or financial security.",
    "Female Head of Household": "A woman who is the primary decision-maker and provider for the household.",
    "Victim of Domestic Violence": "A woman currently affected by violence or abuse within the home.",
    "Survivor of Abuse": "A woman who has survived physical, emotional, or sexual abuse.",
    "Elderly Woman (60+)": "A woman aged 60 or above, often needing age-related support.",
    "Homeless": "A woman without secure or permanent housing.",
    "Orphan / No Family Support": "A woman with no dependable family support structure.",
    "Migrant Woman": "A woman who has moved for work, safety, marriage, or survival and may lack local support.",
    "Caregiver (children / elderly / disabled)": "A woman responsible for regular care of children, elderly persons, or persons with disabilities.",
    "Employed": "A woman currently working in a salaried or wage-based role.",
    "Self-employed": "A woman earning independently through business, trade, farming, or service work.",
    "Unemployed": "A woman currently without paid work and seeking or needing livelihood support.",
    "Student": "A woman currently pursuing school, college, or vocational education.",
}


class RoleRequiredMixin(UserPassesTestMixin):
    allowed_roles = {"admin", "editor", "viewer"}
    module_key = None
    permission_action = "view"

    def test_func(self):
        user = self.request.user
        if not (user and user.is_authenticated and user.status == models.StatusChoices.ACTIVE):
            return False
        if self.module_key:
            return user.has_module_permission(self.module_key, self.permission_action)
        return user.role in self.allowed_roles


class WriteRoleMixin(RoleRequiredMixin):
    allowed_roles = {"admin", "editor"}



class DashboardView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    allowed_roles = {"admin", "editor", "viewer"}
    template_name = "dashboard/dashboard.html"

    def post(self, request, *args, **kwargs):
        if request.user.role not in {"admin", "editor"}:
            messages.error(request, "You do not have permission to update the event budget.")
            return HttpResponseRedirect(reverse("ui:dashboard"))
        budget_raw = (request.POST.get("event_budget") or "").strip().replace(",", "")
        try:
            event_budget = Decimal(budget_raw or "0")
            if event_budget < 0:
                raise InvalidOperation
        except (InvalidOperation, ValueError):
            messages.error(request, "Enter a valid event budget amount.")
            return HttpResponseRedirect(reverse("ui:dashboard"))
        setting = models.DashboardSetting.objects.order_by("pk").first()
        if setting is None:
            setting = models.DashboardSetting.objects.create(event_budget=event_budget, updated_by=request.user)
        else:
            setting.event_budget = event_budget
            setting.updated_by = request.user
            setting.save(update_fields=["event_budget", "updated_by", "updated_at"])
        messages.success(request, "Event budget updated.")
        return HttpResponseRedirect(reverse("ui:dashboard"))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        metrics = self._build_metrics()
        setting = models.DashboardSetting.objects.order_by("pk").first()
        overall_event_budget = setting.event_budget if setting else metrics["district"]["total_allotted_fund"]
        context.update(
            {
                "metrics": metrics,
                "overall_event_budget": overall_event_budget,
                "balance_to_allot": overall_event_budget - metrics["overall"]["total_value_accrued"],
                "can_edit_event_budget": self.request.user.role in {"admin", "editor"},
            }
        )
        return context

    def _zero(self):
        return Decimal("0")

    def _signed_currency_text(self, value):
        amount = Decimal(str(value or 0))
        sign = "+" if amount >= 0 else "-"
        return {"sign": sign, "amount": abs(amount)}

    def _build_metrics(self):
        zero = self._zero()
        district_entries = list(
            models.DistrictBeneficiaryEntry.objects.select_related("district", "article").all()
        )
        public_entries = list(
            models.PublicBeneficiaryEntry.objects.select_related("article").all()
        )
        institution_entries = list(
            models.InstitutionsBeneficiaryEntry.objects.select_related("article").all()
        )
        districts = list(models.DistrictMaster.objects.filter(is_active=True).order_by("district_name"))
        fund_requests = list(models.FundRequest.objects.all())

        district_article_ids = set()
        district_ids = set()
        district_articles_qty = 0
        district_value_accrued = zero
        district_spend_map = {}
        for entry in district_entries:
            if entry.article_id:
                district_article_ids.add(entry.article_id)
            if entry.district_id:
                district_ids.add(entry.district_id)
                district_spend_map[entry.district_id] = district_spend_map.get(entry.district_id, zero) + Decimal(str(entry.total_amount or 0))
            district_articles_qty += int(entry.quantity or 0)
            district_value_accrued += Decimal(str(entry.total_amount or 0))

        public_article_ids = set()
        public_articles_qty = 0
        public_value_accrued = zero
        gender_counts = {"Male": 0, "Female": 0, "Transgender": 0}
        female_status_counts = {}
        handicapped = 0
        disability_category_counts = {}
        for entry in public_entries:
            if entry.article_id:
                public_article_ids.add(entry.article_id)
            public_articles_qty += int(entry.quantity or 0)
            public_value_accrued += Decimal(str(entry.total_amount or 0))
            if entry.gender in gender_counts:
                gender_counts[entry.gender] += 1
            if entry.female_status:
                female_status_counts[entry.female_status] = female_status_counts.get(entry.female_status, 0) + 1
            if entry.is_handicapped and entry.is_handicapped != models.HandicappedStatusChoices.NO:
                handicapped += 1
                disability_category_counts[entry.is_handicapped] = disability_category_counts.get(entry.is_handicapped, 0) + 1

        institution_article_ids = set()
        institution_applications = set()
        institution_articles_qty = 0
        institution_value_accrued = zero
        for entry in institution_entries:
            if entry.article_id:
                institution_article_ids.add(entry.article_id)
            if entry.application_number:
                institution_applications.add(entry.application_number)
            institution_articles_qty += int(entry.quantity or 0)
            institution_value_accrued += Decimal(str(entry.total_amount or 0))

        overall_article_ids = district_article_ids | public_article_ids | institution_article_ids
        overall_articles_qty = district_articles_qty + public_articles_qty + institution_articles_qty
        total_allotted_fund = sum((Decimal(str(d.allotted_budget or 0)) for d in districts), zero)
        received_district_allotted_fund = sum(
            (Decimal(str(d.allotted_budget or 0)) for d in districts if d.id in district_ids),
            zero,
        )
        district_variance = district_value_accrued - received_district_allotted_fund
        overall_actual_value_accrued = district_value_accrued + public_value_accrued + institution_value_accrued
        overall_planning_value_accrued = received_district_allotted_fund + public_value_accrued + institution_value_accrued
        overall_beneficiaries = district_articles_qty + public_articles_qty + len(institution_applications)

        fund_request_total_value = sum((Decimal(str(f.total_amount or 0)) for f in fund_requests), zero)

        pending_districts = [
            district.district_name
            for district in districts
            if district.id and district.id not in district_ids and district.district_name
        ]

        under_utilized_district_count = 0
        under_utilized_value = zero
        over_utilized_district_count = 0
        over_utilized_value = zero
        for district in districts:
            if district.id not in district_ids:
                continue
            allotted = Decimal(str(district.allotted_budget or 0))
            used = district_spend_map.get(district.id, zero)
            delta = used - allotted
            if delta > 0:
                over_utilized_district_count += 1
                over_utilized_value += delta
            elif delta < 0:
                under_utilized_district_count += 1
                under_utilized_value += abs(delta)

        preferred_female_order = ["Single", "Married", "Widowed", "Single Mother"]
        female_status_lines = []
        for label in preferred_female_order:
            female_status_lines.append(
                {
                    "label": label,
                    "value": female_status_counts.get(label, 0),
                    "class_name": {
                        "Single": "female-unmarried",
                        "Married": "female-married",
                        "Widowed": "female-widow",
                        "Single Mother": "female-single-mother",
                    }.get(label, ""),
                }
            )
        for label, value in female_status_counts.items():
            if label not in preferred_female_order:
                female_status_lines.append({"label": label, "value": value, "class_name": ""})

        return {
            "district": {
                "districts_received": len(district_ids),
                "districts_pending": max(len(districts) - len(district_ids), 0),
                "total_articles_qty": district_articles_qty,
                "unique_articles": len(district_article_ids),
                "total_beneficiaries": len(district_entries),
                "total_allotted_fund": total_allotted_fund,
                "total_value_accrued": district_value_accrued,
                "under_utilized_district_count": under_utilized_district_count,
                "under_utilized_value": under_utilized_value,
                "over_utilized_district_count": over_utilized_district_count,
                "over_utilized_value": over_utilized_value,
                "net_variance": district_variance,
            },
            "public": {
                "total_beneficiaries": len(public_entries),
                "total_articles_qty": public_articles_qty,
                "unique_articles": len(public_article_ids),
                "total_value_accrued": public_value_accrued,
                "gender_lines": [
                    {"label": "Male", "value": gender_counts["Male"], "class_name": "gender-male"},
                    {"label": "Female", "value": gender_counts["Female"], "class_name": "gender-female"},
                    {"label": "Transgender", "value": gender_counts["Transgender"], "class_name": "gender-transgender"},
                ],
                "female_status_lines": female_status_lines,
                "handicapped": handicapped,
                "handicapped_lines": [
                    {
                        "label": label,
                        "value": disability_category_counts.get(label, 0),
                        "color": color,
                    }
                    for label, color in [
                        ("Blindness / Low Vision", "#2563eb"),
                        ("Deaf / Hard of Hearing", "#9333ea"),
                        ("Locomotor Disability", "#ea580c"),
                        ("Cerebral Palsy", "#0f766e"),
                        ("Leprosy Cured", "#ca8a04"),
                        ("Dwarfism", "#db2777"),
                        ("Acid Attack Victim", "#dc2626"),
                        ("Muscular Dystrophy", "#16a34a"),
                        ("Autism Spectrum Disorder", "#4f46e5"),
                        ("Intellectual Disability", "#0891b2"),
                        ("Specific Learning Disability", "#65a30d"),
                        ("Mental Illness", "#d97706"),
                        ("Multiple Disability", "#7c3aed"),
                        ("Deaf-Blindness", "#334155"),
                        ("Other", "#64748b"),
                    ]
                    if disability_category_counts.get(label, 0)
                ] + [
                    {"label": "No", "value": max(len(public_entries) - handicapped, 0), "color": "#cbd5e1"}
                ],
            },
            "institutions": {
                "total_beneficiaries": len(institution_entries),
                "application_count": len(institution_applications),
                "total_articles_qty": institution_articles_qty,
                "unique_articles": len(institution_article_ids),
                "total_value_accrued": institution_value_accrued,
            },
            "overall": {
                "total_beneficiaries": overall_beneficiaries,
                "total_articles_qty": overall_articles_qty,
                "unique_articles": len(overall_article_ids),
                "total_value_accrued": overall_planning_value_accrued,
                "actual_total_value_accrued": overall_actual_value_accrued,
                "district_variance": district_variance,
                "district_variance_signed": self._signed_currency_text(district_variance),
                "district_contribution_signed": self._signed_currency_text(-district_variance),
            },
            "fund_requests": {
                "count": len(fund_requests),
                "total_value": fund_request_total_value,
            },
            "total_districts": len(districts),
            "pending_districts": pending_districts,
        }


class ArticleListView(LoginRequiredMixin, RoleRequiredMixin, ListView):
    module_key = models.ModuleKeyChoices.ARTICLE_MANAGEMENT
    permission_action = "view"
    model = models.Article
    template_name = "dashboard/article_list.html"
    context_object_name = "articles"

    def get(self, request, *args, **kwargs):
        if (request.GET.get("export") or "").strip().lower() == "csv":
            return self._export_csv()
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        queryset = models.Article.objects.order_by("article_name")
        if q := self.request.GET.get("q"):
            queryset = queryset.filter(
                Q(article_name__icontains=q)
                | Q(article_name_tk__icontains=q)
                | Q(category__icontains=q)
                | Q(master_category__icontains=q)
                | Q(item_type__icontains=q)
            )
        if item_type := (self.request.GET.get("item_type") or "").strip():
            queryset = queryset.filter(item_type=item_type)
        if combo_filter := (self.request.GET.get("combo") or "").strip():
            if combo_filter == "combo":
                queryset = queryset.filter(combo=True)
            elif combo_filter == "separate":
                queryset = queryset.filter(combo=False)
        if category := (self.request.GET.get("category") or "").strip():
            queryset = queryset.filter(category=category)
        if master_category := (self.request.GET.get("master_category") or "").strip():
            queryset = queryset.filter(master_category=master_category)
        sort = (self.request.GET.get("sort") or "article_name").strip()
        direction = (self.request.GET.get("dir") or "asc").strip().lower()
        allowed_sorts = {
            "article_name": "article_name",
            "item_type": "item_type",
            "category": "category",
            "master_category": "master_category",
            "cost_per_unit": "cost_per_unit",
            "combo": "combo",
            "created_at": "created_at",
            "article_name_tk": "article_name_tk",
        }
        sort_field = allowed_sorts.get(sort, "article_name")
        if direction == "desc":
            sort_field = f"-{sort_field}"
        queryset = queryset.order_by(sort_field, "article_name")
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        category_choices = (
            models.Article.objects.exclude(category__isnull=True)
            .exclude(category__exact="")
            .order_by("category")
            .values_list("category", flat=True)
            .distinct()
        )
        master_category_choices = (
            models.Article.objects.exclude(master_category__isnull=True)
            .exclude(master_category__exact="")
            .order_by("master_category")
            .values_list("master_category", flat=True)
            .distinct()
        )
        context.update(
            {
                "item_type_choices": models.ItemTypeChoices.choices,
                "combo_choices": [("combo", "Combo"), ("separate", "Separate")],
                "category_choices": category_choices,
                "master_category_choices": master_category_choices,
                "filters": {
                    "q": self.request.GET.get("q", ""),
                    "item_type": self.request.GET.get("item_type", ""),
                    "combo": self.request.GET.get("combo", ""),
                    "category": self.request.GET.get("category", ""),
                    "master_category": self.request.GET.get("master_category", ""),
                },
                "current_sort": (self.request.GET.get("sort") or "article_name").strip(),
                "current_dir": (self.request.GET.get("dir") or "asc").strip().lower(),
                "query_string_without_page": self._query_string_without_page(),
            }
        )
        return context

    def _query_string_without_page(self):
        params = self.request.GET.copy()
        return params.urlencode()

    def _export_csv(self):
        timestamp = timezone.localtime().strftime("%Y_%m_%d_%I_%M_%p")
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = f'attachment; filename="article-management_{timestamp}.csv"'
        writer = csv.writer(response)
        writer.writerow(
            [
                "Article Name",
                "Token Name",
                "Cost Per Unit",
                "Item Type",
                "Category",
                "Super Category",
                "Combo / Separate",
                "Status",
                "Created At",
                "Updated At",
            ]
        )
        for article in self.get_queryset():
            writer.writerow(
                [
                    article.article_name,
                    article.article_name_tk or "",
                    article.cost_per_unit,
                    article.get_item_type_display(),
                    article.category or "",
                    article.master_category or "",
                    "Combo" if article.combo else "Separate",
                    "Active" if article.is_active else "Inactive",
                    timezone.localtime(article.created_at).strftime("%d/%m/%Y %H:%M"),
                    timezone.localtime(article.updated_at).strftime("%d/%m/%Y %H:%M"),
                ]
            )
        return response


class ArticleCreateView(LoginRequiredMixin, WriteRoleMixin, CreateView):
    module_key = models.ModuleKeyChoices.ARTICLE_MANAGEMENT
    permission_action = "create_edit"
    model = models.Article
    form_class = ArticleForm
    template_name = "dashboard/article_form.html"
    success_url = reverse_lazy("ui:article-list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["popup_mode"] = self.request.GET.get("popup") == "1"
        context["category_suggestions"] = (
            models.Article.objects.exclude(category__isnull=True)
            .exclude(category__exact="")
            .order_by("category")
            .values_list("category", flat=True)
            .distinct()
        )
        context["master_category_suggestions"] = (
            models.Article.objects.exclude(master_category__isnull=True)
            .exclude(master_category__exact="")
            .order_by("master_category")
            .values_list("master_category", flat=True)
            .distinct()
        )
        return context

    def form_valid(self, form):
        self.object = form.save()
        if self.request.GET.get("popup") == "1":
            payload = json.dumps(
                {
                    "id": self.object.id,
                    "article_name": self.object.article_name,
                    "cost_per_unit": str(self.object.cost_per_unit),
                    "item_type": self.object.item_type,
                }
            ).replace("</", "<\\/")
            return HttpResponse(
                f"""<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>Article created</title></head>
<body style="font-family: Poppins, Segoe UI, Arial, sans-serif; padding: 24px;">
  <div>Article created. Returning to the application form…</div>
  <script>
    (function() {{
      var article = {payload};
      if (window.opener && !window.opener.closed && typeof window.opener.handleArticleCreated === "function") {{
        window.opener.handleArticleCreated(article);
        try {{ window.opener.focus(); }} catch (error) {{}}
        window.close();
        return;
      }}
      document.body.innerHTML = "<p>Article created. You can close this window now.</p>";
    }})();
  </script>
</body>
</html>"""
            )
        messages.success(self.request, "Article created.")
        return HttpResponseRedirect(self.get_success_url())


class ArticleUpdateView(LoginRequiredMixin, WriteRoleMixin, UpdateView):
    module_key = models.ModuleKeyChoices.ARTICLE_MANAGEMENT
    permission_action = "create_edit"
    model = models.Article
    form_class = ArticleForm
    template_name = "dashboard/article_form.html"
    success_url = reverse_lazy("ui:article-list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["popup_mode"] = False
        context["category_suggestions"] = (
            models.Article.objects.exclude(category__isnull=True)
            .exclude(category__exact="")
            .order_by("category")
            .values_list("category", flat=True)
            .distinct()
        )
        context["master_category_suggestions"] = (
            models.Article.objects.exclude(master_category__isnull=True)
            .exclude(master_category__exact="")
            .order_by("master_category")
            .values_list("master_category", flat=True)
            .distinct()
        )
        return context

    def form_valid(self, form):
        messages.success(self.request, "Article updated.")
        return super().form_valid(form)


class AdminRequiredMixin(RoleRequiredMixin):
    allowed_roles = {"admin"}


class UserManagementListView(LoginRequiredMixin, AdminRequiredMixin, ListView):
    module_key = models.ModuleKeyChoices.USER_MANAGEMENT
    permission_action = "view"
    model = models.AppUser
    template_name = "dashboard/user_management.html"
    context_object_name = "users"

    def get_queryset(self):
        queryset = models.AppUser.objects.select_related("created_by").order_by("first_name", "email")
        if q := (self.request.GET.get("q") or "").strip():
            queryset = queryset.filter(
                Q(first_name__icontains=q)
                | Q(last_name__icontains=q)
                | Q(email__icontains=q)
                | Q(role__icontains=q)
                | Q(status__icontains=q)
            )
        if role := (self.request.GET.get("role") or "").strip():
            queryset = queryset.filter(role=role)
        if status := (self.request.GET.get("status") or "").strip():
            queryset = queryset.filter(status=status)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["filters"] = {
            "q": (self.request.GET.get("q") or "").strip(),
            "role": (self.request.GET.get("role") or "").strip(),
            "status": (self.request.GET.get("status") or "").strip(),
        }
        context["role_choices"] = models.RoleChoices.choices
        context["status_choices"] = models.StatusChoices.choices
        return context


class UserManagementCreateView(LoginRequiredMixin, AdminRequiredMixin, CreateView):
    module_key = models.ModuleKeyChoices.USER_MANAGEMENT
    permission_action = "create_edit"
    model = models.AppUser
    form_class = AppUserCreateForm
    template_name = "dashboard/user_form.html"

    def get_success_url(self):
        return reverse("ui:user-list")

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        messages.success(self.request, "User created successfully.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Create User"
        context["submit_label"] = "Create"
        return context


class UserManagementUpdateView(LoginRequiredMixin, AdminRequiredMixin, UpdateView):
    module_key = models.ModuleKeyChoices.USER_MANAGEMENT
    permission_action = "create_edit"
    model = models.AppUser
    form_class = AppUserUpdateForm
    template_name = "dashboard/user_form.html"

    def get_success_url(self):
        return reverse("ui:user-list")

    def form_valid(self, form):
        if self.object == self.request.user:
            if form.cleaned_data.get("status") != models.StatusChoices.ACTIVE:
                form.add_error("status", "You cannot deactivate your own account.")
                return self.form_invalid(form)
            if form.cleaned_data.get("role") != models.RoleChoices.ADMIN:
                form.add_error("role", "You cannot remove your own admin access.")
                return self.form_invalid(form)
        messages.success(self.request, "User updated successfully.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Edit User"
        context["submit_label"] = "Save"
        return context


class UserManagementPasswordResetView(LoginRequiredMixin, AdminRequiredMixin, FormView):
    module_key = models.ModuleKeyChoices.USER_MANAGEMENT
    permission_action = "reset_password"
    form_class = AppUserPasswordResetForm
    template_name = "dashboard/user_password_reset.html"

    def dispatch(self, request, *args, **kwargs):
        self.target_user = get_object_or_404(models.AppUser, pk=kwargs["pk"])
        return super().dispatch(request, *args, **kwargs)

    def get_success_url(self):
        return reverse("ui:user-list")

    def form_valid(self, form):
        self.target_user.set_password(form.cleaned_data["password1"])
        self.target_user.save(update_fields=["password", "updated_at"])
        messages.success(self.request, f"Password reset for {self.target_user.display_name}.")
        return HttpResponseRedirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Reset Password"
        context["target_user"] = self.target_user
        context["submit_label"] = "Reset Password"
        return context


class UserManagementDeleteView(LoginRequiredMixin, AdminRequiredMixin, View):
    module_key = models.ModuleKeyChoices.USER_MANAGEMENT
    permission_action = "delete"
    def post(self, request, *args, **kwargs):
        user = get_object_or_404(models.AppUser, pk=kwargs["pk"])
        if user == request.user:
            messages.error(request, "You cannot delete your own account.")
            return HttpResponseRedirect(reverse("ui:user-list"))
        user.delete()
        messages.success(request, "User deleted successfully.")
        return HttpResponseRedirect(reverse("ui:user-list"))


class ArticleDeleteView(LoginRequiredMixin, AdminRequiredMixin, DeleteView):
    module_key = models.ModuleKeyChoices.ARTICLE_MANAGEMENT
    permission_action = "delete"
    model = models.Article
    template_name = "dashboard/article_confirm_delete.html"
    success_url = reverse_lazy("ui:article-list")

    def post(self, request, *args, **kwargs):
        messages.warning(self.request, "Article deleted.")
        return super().post(request, *args, **kwargs)


class MasterEntryView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    module_key = models.ModuleKeyChoices.APPLICATION_ENTRY
    permission_action = "view"
    template_name = "dashboard/module_master_entry.html"

    def get(self, request, *args, **kwargs):
        export_scope = (request.GET.get("export_scope") or "").strip().lower()
        if export_scope:
            return _export_master_entry_csv(request, export_scope=export_scope)
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        beneficiary_type = self.request.GET.get("type", "district")
        search_query = (self.request.GET.get("q") or "").strip()
        date_from = (self.request.GET.get("date_from") or "").strip()
        date_to = (self.request.GET.get("date_to") or "").strip()
        status_filter = (self.request.GET.get("status") or "").strip().lower()
        sort_by = (self.request.GET.get("sort") or "").strip()
        sort_dir = "asc" if (self.request.GET.get("dir") or "desc").lower() == "asc" else "desc"

        district_groups = _filter_sort_district_summaries(
            _build_district_entry_summaries(),
            search_query=search_query,
            date_from=date_from,
            date_to=date_to,
            status_filter=status_filter,
            sort_by=sort_by,
            sort_dir=sort_dir,
        )
        public_entries = _filter_sort_public_entries(
            models.PublicBeneficiaryEntry.objects.select_related("article").all(),
            search_query=search_query,
            date_from=date_from,
            date_to=date_to,
            status_filter=status_filter,
            sort_by=sort_by,
            sort_dir=sort_dir,
        )
        public_entries = list(public_entries)
        public_attachment_map = _public_attachment_preview_map([entry.id for entry in public_entries])
        public_attachment_lists = _public_attachment_preview_lists([entry.id for entry in public_entries])
        for entry in public_entries:
            entry_history_matches = _public_history_matches(entry.aadhar_number)
            entry.public_history_summary = _public_history_summary(entry_history_matches)
            attachment = public_attachment_map.get(entry.id)
            attachment_items = [_attachment_preview_payload(item) for item in public_attachment_lists.get(entry.id, [])]
            attachment_items = [item for item in attachment_items if item]
            entry.attachment_id = attachment.id if attachment else None
            entry.attachment_preview_url = reverse("ui:application-attachment-download", kwargs={"attachment_id": attachment.id}) if attachment else ""
            entry.attachment_source = (attachment.file.name or "").lower() if attachment and attachment.file else ""
            entry.attachment_title = _attachment_preview_title(attachment)
            entry.attachment_count = len(attachment_items)
            entry.attachment_items_json = json.dumps(attachment_items)
            entry.attachment_items_b64 = _attachment_items_b64(attachment_items)
        institution_groups = _filter_sort_institution_summaries(
            _build_institution_entry_summaries(),
            search_query=search_query,
            date_from=date_from,
            date_to=date_to,
            status_filter=status_filter,
            sort_by=sort_by,
            sort_dir=sort_dir,
        )

        context["beneficiary_type"] = beneficiary_type
        context["search_query"] = search_query
        context["date_from"] = date_from
        context["date_to"] = date_to
        context["status_filter"] = status_filter
        context["status_choices"] = [
            ("", "All Statuses"),
            (models.BeneficiaryStatusChoices.DRAFT, "Draft"),
            (models.BeneficiaryStatusChoices.SUBMITTED, "Submitted"),
        ]
        context["sort_by"] = sort_by
        context["sort_dir"] = sort_dir
        context["district_groups"] = district_groups
        context["district_count"] = models.DistrictBeneficiaryEntry.objects.values("district_id").distinct().count()
        context["public_count"] = models.PublicBeneficiaryEntry.objects.count()
        context["institution_count"] = models.InstitutionsBeneficiaryEntry.objects.values("application_number").distinct().count()
        context["public_entries"] = public_entries
        context["institution_groups"] = institution_groups
        context["district_total_accrued"] = sum((row["total_accrued"] or 0) for row in district_groups)
        context["public_total_accrued"] = sum((entry.total_amount or 0) for entry in public_entries)
        context["institution_total_accrued"] = sum((row["total_value"] or 0) for row in institution_groups)
        context["public_submit_popup"] = self.request.session.pop("public_submit_popup", None)
        context["institution_submit_popup"] = self.request.session.pop("institution_submit_popup", None)
        return context


class ApplicationAuditLogListView(LoginRequiredMixin, AdminRequiredMixin, ListView):
    module_key = models.ModuleKeyChoices.AUDIT_LOGS
    permission_action = "view"
    model = models.AuditLog
    template_name = "dashboard/application_audit_logs.html"
    context_object_name = "audit_logs"
    paginate_by = 50

    def get_queryset(self):
        queryset = models.AuditLog.objects.select_related("user").filter(
            entity_type__in=[
                "district_application",
                "public_application",
                "institution_application",
            ]
        ).order_by("-created_at")
        q = (self.request.GET.get("q") or "").strip()
        application_type = (self.request.GET.get("application_type") or "").strip()
        user_id = (self.request.GET.get("user_id") or "").strip()
        date_from = (self.request.GET.get("date_from") or "").strip()
        date_to = (self.request.GET.get("date_to") or "").strip()
        if q:
            queryset = queryset.filter(
                Q(entity_type__icontains=q)
                | Q(entity_id__icontains=q)
                | Q(action_type__icontains=q)
                | Q(user__email__icontains=q)
                | Q(user__first_name__icontains=q)
                | Q(user__last_name__icontains=q)
            )
        if application_type:
            queryset = queryset.filter(entity_type=application_type)
        if user_id:
            queryset = queryset.filter(user_id=user_id)
        if date_from:
            queryset = queryset.filter(created_at__date__gte=date_from)
        if date_to:
            queryset = queryset.filter(created_at__date__lte=date_to)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["search_query"] = (self.request.GET.get("q") or "").strip()
        context["application_type"] = (self.request.GET.get("application_type") or "").strip()
        context["selected_user_id"] = (self.request.GET.get("user_id") or "").strip()
        context["date_from"] = (self.request.GET.get("date_from") or "").strip()
        context["date_to"] = (self.request.GET.get("date_to") or "").strip()
        context["application_type_choices"] = [
            ("district_application", "District Application"),
            ("public_application", "Public Application"),
            ("institution_application", "Institution Application"),
        ]
        context["audit_users"] = (
            models.AppUser.objects.filter(
                audit_logs__entity_type__in=[
                    "district_application",
                    "public_application",
                    "institution_application",
                ]
            )
            .distinct()
            .order_by("first_name", "email")
        )
        context["audit_rows"] = [
            {
                "log": log,
                "application_label": _application_audit_label(log),
                "change_lines": _application_audit_change_lines(log),
                "user_label": _audit_user_label(log.user),
            }
            for log in context["audit_logs"]
        ]
        return context



EXPORT_COLUMNS = [
    "Application Number",
    "Beneficiary Name",
    "Requested Item",
    "Quantity",
    "Cost Per Unit",
    "Total Value",
    "Address",
    "Mobile",
    "Aadhar Number",
    "Handicapped Status",
    "Gender",
    "Gender Category",
    "Beneficiary Type",
    "Item Type",
    "Article Category",
    "Super Category Article",
    "Token Name",
    "Internal Notes",
    "Comments",
]


def _request_audit_meta(request):
    return {
        "ip_address": request.META.get("REMOTE_ADDR"),
        "user_agent": request.META.get("HTTP_USER_AGENT", ""),
    }


def _attachment_upload_context(*, attachments=None, enabled=False, upload_url="", helper_text="Attachments can be added after the application is first saved."):
    return {
        "application_attachments": attachments or [],
        "attachment_upload_form": ApplicationAttachmentUploadForm(),
        "attachments_enabled": enabled,
        "attachment_upload_url": upload_url,
        "attachment_helper_text": helper_text,
        "attachment_constraints_text": (
            "Allowed files: PDF, JPG, JPEG, PNG, WEBP, DOC, DOCX, XLS, XLSX, CSV. "
            "Maximum file size: 10 MB. Maximum 2 files per application."
        ),
    }


def _prefixed_attachment_name(application_reference, uploaded_name, custom_name=""):
    prefix = (application_reference or "").strip()
    original_name = (uploaded_name or "").strip()
    chosen_name = (custom_name or "").strip() or original_name or "attachment"
    chosen_root, chosen_ext = os.path.splitext(chosen_name)
    _, original_ext = os.path.splitext(original_name)
    final_name = chosen_name if chosen_ext else f"{chosen_name}{original_ext}"
    if prefix:
        normalized_prefix = f"{prefix}_"
        if final_name.startswith(normalized_prefix):
            return final_name
        return f"{prefix}_{final_name}"
    return final_name


def _attachment_name_exists(queryset, final_name):
    normalized = (final_name or "").strip().lower()
    if not normalized:
        return False
    for existing_name in queryset.values_list("file_name", flat=True):
        if (existing_name or "").strip().lower() == normalized:
            return True
    return False


def _district_attachment_context(district):
    has_saved_application = bool(district and models.DistrictBeneficiaryEntry.objects.filter(district=district).exists())
    attachments = []
    upload_url = ""
    if has_saved_application:
        attachments = list(models.ApplicationAttachment.objects.filter(district=district).select_related("uploaded_by").order_by("-created_at"))
        upload_url = reverse("ui:district-attachment-upload", kwargs={"district_id": district.id})
    return _attachment_upload_context(
        attachments=attachments,
        enabled=has_saved_application,
        upload_url=upload_url,
        helper_text="Save the district application first to upload attachments." if not has_saved_application else "Upload files related to this district application. You can rename the file before upload.",
    )


def _public_attachment_context(entry):
    has_saved_application = bool(entry and entry.pk)
    attachments = []
    upload_url = ""
    if has_saved_application:
        attachments = list(models.ApplicationAttachment.objects.filter(public_entry=entry).select_related("uploaded_by").order_by("-created_at"))
        upload_url = reverse("ui:public-attachment-upload", kwargs={"pk": entry.pk})
    context = _attachment_upload_context(
        attachments=attachments,
        enabled=has_saved_application,
        upload_url=upload_url,
        helper_text="Save the public application first to upload attachments." if not has_saved_application else "Upload files related to this public application. You can rename the file before upload.",
    )
    context["entry_id"] = entry.pk if has_saved_application else None
    return context


def _institution_attachment_context(application_number):
    has_saved_application = bool(application_number)
    attachments = []
    upload_url = ""
    if has_saved_application:
        attachments = list(
            models.ApplicationAttachment.objects.filter(
                application_type=models.ApplicationAttachmentTypeChoices.INSTITUTION,
                institution_application_number=application_number,
            ).select_related("uploaded_by").order_by("-created_at")
        )
        upload_url = reverse("ui:institution-attachment-upload", kwargs={"application_number": application_number})
    return _attachment_upload_context(
        attachments=attachments,
        enabled=has_saved_application,
        upload_url=upload_url,
        helper_text="Save the institution application first to upload attachments." if not has_saved_application else "Upload files related to this institution application. You can rename the file before upload.",
    )


def _district_attachment_preview_map(district_ids):
    if not district_ids:
        return {}
    attachments = (
        models.ApplicationAttachment.objects.filter(
            application_type=models.ApplicationAttachmentTypeChoices.DISTRICT,
            district_id__in=district_ids,
        )
        .order_by("district_id", "-created_at", "-id")
    )
    preview_map = {}
    for attachment in attachments:
        if attachment.district_id not in preview_map:
            preview_map[attachment.district_id] = attachment
    return preview_map


def _district_attachment_preview_lists(district_ids):
    if not district_ids:
        return {}
    attachments = (
        models.ApplicationAttachment.objects.filter(
            application_type=models.ApplicationAttachmentTypeChoices.DISTRICT,
            district_id__in=district_ids,
        )
        .order_by("district_id", "-created_at", "-id")
    )
    preview_map = {}
    for attachment in attachments:
        preview_map.setdefault(attachment.district_id, []).append(attachment)
    return preview_map


def _public_attachment_preview_map(entry_ids):
    if not entry_ids:
        return {}
    attachments = (
        models.ApplicationAttachment.objects.filter(
            application_type=models.ApplicationAttachmentTypeChoices.PUBLIC,
            public_entry_id__in=entry_ids,
        )
        .order_by("public_entry_id", "-created_at", "-id")
    )
    preview_map = {}
    for attachment in attachments:
        if attachment.public_entry_id not in preview_map:
            preview_map[attachment.public_entry_id] = attachment
    return preview_map


def _public_attachment_preview_lists(entry_ids):
    if not entry_ids:
        return {}
    attachments = (
        models.ApplicationAttachment.objects.filter(
            application_type=models.ApplicationAttachmentTypeChoices.PUBLIC,
            public_entry_id__in=entry_ids,
        )
        .order_by("public_entry_id", "-created_at", "-id")
    )
    preview_map = {}
    for attachment in attachments:
        preview_map.setdefault(attachment.public_entry_id, []).append(attachment)
    return preview_map


def _institution_attachment_preview_map(application_numbers):
    if not application_numbers:
        return {}
    attachments = (
        models.ApplicationAttachment.objects.filter(
            application_type=models.ApplicationAttachmentTypeChoices.INSTITUTION,
            institution_application_number__in=application_numbers,
        )
        .order_by("institution_application_number", "-created_at", "-id")
    )
    preview_map = {}
    for attachment in attachments:
        key = attachment.institution_application_number
        if key and key not in preview_map:
            preview_map[key] = attachment
    return preview_map


def _institution_attachment_preview_lists(application_numbers):
    if not application_numbers:
        return {}
    attachments = (
        models.ApplicationAttachment.objects.filter(
            application_type=models.ApplicationAttachmentTypeChoices.INSTITUTION,
            institution_application_number__in=application_numbers,
        )
        .order_by("institution_application_number", "-created_at", "-id")
    )
    preview_map = {}
    for attachment in attachments:
        key = attachment.institution_application_number
        if key:
            preview_map.setdefault(key, []).append(attachment)
    return preview_map


def _attachment_preview_title(attachment):
    if not attachment:
        return ""
    if attachment.file_name:
        return attachment.file_name
    if attachment.file:
        return os.path.basename(attachment.file.name)
    return ""


def _attachment_preview_payload(attachment):
    if not attachment:
        return None
    preview_url = reverse("ui:application-attachment-download", kwargs={"attachment_id": attachment.id})
    return {
        "id": attachment.id,
        "title": _attachment_preview_title(attachment),
        "preview_url": preview_url,
        "download_url": f"{preview_url}?download=1",
        "source": (attachment.file.name or "").lower() if attachment.file else "",
    }


def _attachment_items_b64(items):
    payload = json.dumps(items, ensure_ascii=False)
    return base64.b64encode(payload.encode("utf-8")).decode("ascii")


def _district_audit_snapshot(district):
    entries = list(
        models.DistrictBeneficiaryEntry.objects.filter(district=district).select_related("article").order_by("id")
    )
    total_accrued = sum((entry.total_amount or 0) for entry in entries)
    return {
        "district_id": str(district.id),
        "application_number": district.application_number or "",
        "district_name": district.district_name or "",
        "president_name": district.president_name or "",
        "mobile_number": district.mobile_number or "",
        "allotted_budget": str(district.allotted_budget or 0),
        "status": entries[0].status if entries else "",
        "internal_notes": (entries[0].internal_notes or "") if entries else "",
        "total_accrued": str(total_accrued or 0),
        "item_count": len(entries),
        "items": [
            {
                "id": str(entry.id),
                "article_id": str(entry.article_id),
                "article_name": entry.article.article_name,
                "item_type": entry.article.item_type,
                "quantity": entry.quantity,
                "unit_cost": str(entry.article_cost_per_unit or 0),
                "total_amount": str(entry.total_amount or 0),
                "name_of_beneficiary": entry.name_of_beneficiary or "",
                "name_of_institution": entry.name_of_institution or "",
                "aadhar_number": entry.aadhar_number or "",
                "cheque_rtgs_in_favour": entry.cheque_rtgs_in_favour or "",
                "notes": entry.notes or "",
            }
            for entry in entries
        ],
    }


def _public_audit_snapshot(entry):
    return {
        "id": str(entry.id),
        "application_number": entry.application_number or "",
        "name": entry.name or "",
        "aadhar_number": entry.aadhar_number or "",
        "is_handicapped": entry.get_is_handicapped_display() if entry.is_handicapped else models.HandicappedStatusChoices.NO,
        "gender": entry.gender or "",
        "female_status": entry.female_status or "",
        "address": entry.address or "",
        "mobile": entry.mobile or "",
        "article_id": str(entry.article_id),
        "article_name": entry.article.article_name,
        "item_type": entry.article.item_type,
        "quantity": entry.quantity,
        "unit_cost": str(entry.article_cost_per_unit or 0),
        "total_amount": str(entry.total_amount or 0),
        "name_of_institution": entry.name_of_institution or "",
        "cheque_rtgs_in_favour": entry.cheque_rtgs_in_favour or "",
        "notes": entry.notes or "",
        "status": entry.status or "",
    }


def _institution_audit_snapshot(application_number):
    entries = list(
        models.InstitutionsBeneficiaryEntry.objects.filter(application_number=application_number).select_related("article").order_by("id")
    )
    if not entries:
        return {"application_number": application_number, "item_count": 0, "items": []}
    first = entries[0]
    total_value = sum((entry.total_amount or 0) for entry in entries)
    return {
        "application_number": application_number,
        "institution_name": first.institution_name or "",
        "institution_type": first.institution_type or "",
        "status": first.status or "",
        "address": first.address or "",
        "mobile": first.mobile or "",
        "internal_notes": first.internal_notes or "",
        "total_value": str(total_value or 0),
        "item_count": len(entries),
        "items": [
            {
                "id": str(entry.id),
                "article_id": str(entry.article_id),
                "article_name": entry.article.article_name,
                "item_type": entry.article.item_type,
                "quantity": entry.quantity,
                "unit_cost": str(entry.article_cost_per_unit or 0),
                "total_amount": str(entry.total_amount or 0),
                "name_of_beneficiary": entry.name_of_beneficiary or "",
                "name_of_institution": entry.name_of_institution or "",
                "aadhar_number": entry.aadhar_number or "",
                "cheque_rtgs_in_favour": entry.cheque_rtgs_in_favour or "",
                "notes": entry.notes or "",
            }
            for entry in entries
        ],
    }


AUDIT_FIELD_LABELS = {
    "district_name": "District",
    "president_name": "President",
    "mobile_number": "Mobile Number",
    "allotted_budget": "Allotted Budget",
    "name": "Name",
    "aadhar_number": "Aadhaar Number",
    "is_handicapped": "Disability Category",
    "gender": "Gender",
    "female_status": "Gender Category",
    "address": "Address",
    "mobile": "Mobile Number",
    "article_name": "Requested Item",
    "item_type": "Item Type",
    "quantity": "Quantity",
    "unit_cost": "Unit Price",
    "total_amount": "Total Value",
    "cheque_rtgs_in_favour": "Cheque / RTGS in Favour",
    "notes": "Comments",
    "internal_notes": "Internal Notes",
    "institution_name": "Institution Name",
    "institution_type": "Institution Type",
    "total_value": "Total Value",
}


def _application_audit_label(log):
    details = log.details or {}
    after = details.get("after") or {}
    before = details.get("before") or {}
    snapshot = after or before
    if log.entity_type == "district_application":
        return snapshot.get("application_number") or snapshot.get("district_name") or log.entity_id or "-"
    if log.entity_type == "public_application":
        application_number = snapshot.get("application_number") or log.entity_id or "-"
        name = snapshot.get("name") or ""
        return f"{application_number} - {name}".strip(" -")
    if log.entity_type == "institution_application":
        application_number = snapshot.get("application_number") or log.entity_id or "-"
        name = snapshot.get("institution_name") or ""
        return f"{application_number} - {name}".strip(" -")
    return log.entity_id or "-"


def _format_audit_value(value):
    if value is None or value == "":
        return "-"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    return str(value)


def _audit_user_label(user):
    if not user:
        return "System"
    if user.first_name:
        return user.first_name
    return user.email


def _audit_item_key(item):
    if item.get("id"):
        return ("id", str(item.get("id")))
    return ("article", item.get("article_id") or "", item.get("article_name") or "")


def _application_audit_change_lines(log):
    details = log.details or {}
    before = details.get("before") or {}
    after = details.get("after") or {}

    if log.action_type == models.ActionTypeChoices.CREATE:
        item_count = after.get("item_count")
        if item_count is not None:
            return [f"Created with {item_count} item(s)."]
        return ["Created application."]

    if log.action_type == models.ActionTypeChoices.DELETE:
        item_count = before.get("item_count")
        if item_count is not None:
            return [f"Deleted application with {item_count} item(s)."]
        return ["Deleted application."]

    change_lines = []
    for key, label in AUDIT_FIELD_LABELS.items():
        if key in {"article_name", "item_type", "quantity", "unit_cost", "total_amount", "notes"}:
            continue
        before_value = before.get(key)
        after_value = after.get(key)
        if before_value != after_value and (before_value is not None or after_value is not None):
            change_lines.append(f"{label}: {_format_audit_value(before_value)} -> {_format_audit_value(after_value)}")

    before_items = before.get("items") or []
    after_items = after.get("items") or []
    before_map = {_audit_item_key(item): item for item in before_items}
    after_map = {_audit_item_key(item): item for item in after_items}

    shared_keys = [key for key in before_map.keys() if key in after_map]
    added = [item for key, item in after_map.items() if key not in before_map]
    removed = [item for key, item in before_map.items() if key not in after_map]

    for key in shared_keys:
        before_item = before_map[key]
        after_item = after_map[key]
        item_changes = []
        for field in ["quantity", "unit_cost", "total_amount", "notes"]:
            if before_item.get(field) != after_item.get(field):
                item_changes.append(
                    f"{AUDIT_FIELD_LABELS[field]}: {_format_audit_value(before_item.get(field))} -> {_format_audit_value(after_item.get(field))}"
                )
        if item_changes:
            change_lines.append(f'{after_item.get("article_name")}: ' + "; ".join(item_changes))

    for item in added:
        change_lines.append(f'Added item: {item.get("article_name")} ({item.get("quantity")} x {_format_audit_value(item.get("unit_cost"))})')
    for item in removed:
        change_lines.append(f'Removed item: {item.get("article_name")}')

    return change_lines or ["No visible field changes recorded."]


def _master_entry_filters_from_request(request):
    return {
        "search_query": (request.GET.get("q") or "").strip(),
        "date_from": (request.GET.get("date_from") or "").strip(),
        "date_to": (request.GET.get("date_to") or "").strip(),
        "status_filter": (request.GET.get("status") or "").strip().lower(),
        "sort_by": (request.GET.get("sort") or "").strip(),
        "sort_dir": "asc" if (request.GET.get("dir") or "desc").lower() == "asc" else "desc",
        "beneficiary_type": (request.GET.get("type") or "district").strip(),
    }


def _decimal_to_csv(value):
    if value is None:
        return ""
    if isinstance(value, Decimal):
        normalized = value.quantize(Decimal("0.01"))
        if normalized == normalized.to_integral():
            return str(int(normalized))
        return format(normalized.normalize(), "f")
    return str(value)


def _district_export_rows(filtered_summaries):
    district_ids = [row["district_id"] for row in filtered_summaries]
    if not district_ids:
        return []
    entries = models.DistrictBeneficiaryEntry.objects.select_related("district", "article").filter(district_id__in=district_ids).order_by("district__application_number", "created_at", "id")
    rows = []
    for entry in entries:
        rows.append({
            "Application Number": entry.district.application_number or entry.application_number or "",
            "Beneficiary Name": entry.district.district_name or "",
            "Requested Item": entry.article.article_name or "",
            "Quantity": str(entry.quantity or 0),
            "Cost Per Unit": _decimal_to_csv(entry.article_cost_per_unit),
            "Total Value": _decimal_to_csv(entry.total_amount),
            "Address": entry.district.district_name or "",
            "Mobile": entry.district.mobile_number or "",
            "Aadhar Number": "",
            "Handicapped Status": "",
            "Gender": "",
            "Gender Category": "",
            "Beneficiary Type": "District",
            "Item Type": entry.article.item_type or "",
            "Article Category": entry.article.category or "",
            "Super Category Article": entry.article.master_category or "",
            "Token Name": entry.article.article_name_tk or "",
            "Internal Notes": "",
            "Comments": entry.notes or "",
        })
    return rows


def _public_export_rows(filtered_entries):
    rows = []
    for entry in filtered_entries:
        rows.append({
            "Application Number": entry.application_number or "",
            "Beneficiary Name": entry.name or "",
            "Requested Item": entry.article.article_name or "",
            "Quantity": str(entry.quantity or 0),
            "Cost Per Unit": _decimal_to_csv(entry.article_cost_per_unit),
            "Total Value": _decimal_to_csv(entry.total_amount),
            "Address": entry.address or "",
            "Mobile": entry.mobile or "",
            "Aadhar Number": entry.aadhar_number or "",
            "Handicapped Status": entry.get_is_handicapped_display() if entry.is_handicapped else models.HandicappedStatusChoices.NO,
            "Gender": entry.gender or "",
            "Gender Category": entry.female_status or entry.gender or "",
            "Beneficiary Type": "Public",
            "Item Type": entry.article.item_type or "",
            "Article Category": entry.article.category or "",
            "Super Category Article": entry.article.master_category or "",
            "Token Name": entry.article.article_name_tk or "",
            "Internal Notes": "",
            "Comments": entry.notes or "",
        })
    return rows


def _institution_export_rows(filtered_summaries):
    application_numbers = [row["application_number"] for row in filtered_summaries]
    if not application_numbers:
        return []
    entries = models.InstitutionsBeneficiaryEntry.objects.select_related("article").filter(application_number__in=application_numbers).order_by("application_number", "created_at", "id")
    rows = []
    for entry in entries:
        rows.append({
            "Application Number": entry.application_number or "",
            "Beneficiary Name": entry.institution_name or "",
            "Requested Item": entry.article.article_name or "",
            "Quantity": str(entry.quantity or 0),
            "Cost Per Unit": _decimal_to_csv(entry.article_cost_per_unit),
            "Total Value": _decimal_to_csv(entry.total_amount),
            "Address": entry.address or "",
            "Mobile": entry.mobile or "",
            "Aadhar Number": "",
            "Handicapped Status": "",
            "Gender": "",
            "Gender Category": "",
            "Beneficiary Type": "Institutions",
            "Item Type": entry.article.item_type or "",
            "Article Category": entry.article.category or "",
            "Super Category Article": entry.article.master_category or "",
            "Token Name": entry.article.article_name_tk or "",
            "Internal Notes": entry.internal_notes or "",
            "Comments": entry.notes or "",
        })
    return rows


def _export_master_entry_csv(request, *, export_scope):
    filters = _master_entry_filters_from_request(request)
    district_rows = []
    public_rows = []
    institution_rows = []

    if export_scope in {"all", "district"}:
        filtered_district_summaries = _filter_sort_district_summaries(
            _build_district_entry_summaries(),
            search_query=filters["search_query"],
            date_from=filters["date_from"],
            date_to=filters["date_to"],
            status_filter=filters["status_filter"],
            sort_by=filters["sort_by"],
            sort_dir=filters["sort_dir"],
        )
        district_rows = _district_export_rows(filtered_district_summaries)

    if export_scope in {"all", "public"}:
        filtered_public_entries = _filter_sort_public_entries(
            models.PublicBeneficiaryEntry.objects.select_related("article").all(),
            search_query=filters["search_query"],
            date_from=filters["date_from"],
            date_to=filters["date_to"],
            status_filter=filters["status_filter"],
            sort_by=filters["sort_by"],
            sort_dir=filters["sort_dir"],
        )
        public_rows = _public_export_rows(filtered_public_entries)

    if export_scope in {"all", "institutions"}:
        filtered_institution_summaries = _filter_sort_institution_summaries(
            _build_institution_entry_summaries(),
            search_query=filters["search_query"],
            date_from=filters["date_from"],
            date_to=filters["date_to"],
            status_filter=filters["status_filter"],
            sort_by=filters["sort_by"],
            sort_dir=filters["sort_dir"],
        )
        institution_rows = _institution_export_rows(filtered_institution_summaries)

    rows = district_rows + public_rows + institution_rows
    response = HttpResponse(content_type="text/csv")
    timestamp = timezone.localtime().strftime("%Y_%m_%d_%I_%M_%p")
    response["Content-Disposition"] = f'attachment; filename="master-entry-{export_scope}_{timestamp}.csv"'
    writer = csv.DictWriter(response, fieldnames=EXPORT_COLUMNS)
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return response


def _build_district_entry_summaries():
    entries = list(
        models.DistrictBeneficiaryEntry.objects.select_related("district", "article").order_by("-created_at")
    )
    grouped = {}
    for entry in entries:
        key = entry.district_id
        grouped.setdefault(key, []).append(entry)

    attachment_map = _district_attachment_preview_map(list(grouped.keys()))
    attachment_lists = _district_attachment_preview_lists(list(grouped.keys()))
    summaries = []
    for district_id, district_entries in grouped.items():
        first = district_entries[0]
        total_accrued = sum((entry.total_amount or 0) for entry in district_entries)
        total_quantity = sum((entry.quantity or 0) for entry in district_entries)
        remaining = (first.district.allotted_budget or 0) - total_accrued
        attachment = attachment_map.get(district_id)
        attachment_items = [_attachment_preview_payload(item) for item in attachment_lists.get(district_id, [])]
        attachment_items = [item for item in attachment_items if item]
        summaries.append(
            {
                "district_id": district_id,
                "application_number": first.district.application_number or first.application_number or "-",
                "district_name": first.district.district_name,
                "article_names": ", ".join(sorted({entry.article.article_name for entry in district_entries})),
                "article_count": len({entry.article_id for entry in district_entries if entry.article_id}),
                "total_quantity": total_quantity,
                "allotted_budget": first.district.allotted_budget or 0,
                "total_accrued": total_accrued,
                "remaining_fund": remaining,
                "status": first.status,
                "internal_notes": first.internal_notes or "",
                "created_at": max(entry.created_at for entry in district_entries),
                "attachment_id": attachment.id if attachment else None,
                "attachment_preview_url": reverse("ui:application-attachment-download", kwargs={"attachment_id": attachment.id}) if attachment else "",
                "attachment_source": (attachment.file.name or "").lower() if attachment and attachment.file else "",
                "attachment_title": _attachment_preview_title(attachment),
                "attachment_count": len(attachment_items),
                "attachment_items_json": json.dumps(attachment_items),
                "attachment_items_b64": _attachment_items_b64(attachment_items),
                "detail_items": [
                    {
                        "article_name": entry.article.article_name,
                        "quantity": entry.quantity,
                        "unit_cost": entry.article_cost_per_unit,
                        "total_amount": entry.total_amount,
                        "name_of_beneficiary": entry.name_of_beneficiary,
                        "name_of_institution": entry.name_of_institution,
                        "aadhar_number": entry.aadhar_number,
                        "notes": entry.notes,
                        "cheque_rtgs_in_favour": entry.cheque_rtgs_in_favour,
                        "changed_at": entry.updated_at,
                    }
                    for entry in district_entries
                ],
            }
        )
    summaries.sort(key=lambda row: row["application_number"])
    return summaries


def _filter_sort_district_summaries(summaries, *, search_query="", date_from="", date_to="", status_filter="", sort_by="", sort_dir="desc"):
    if search_query:
        query = search_query.lower()
        summaries = [
            row for row in summaries
            if query in (row["application_number"] or "").lower()
            or query in (row["district_name"] or "").lower()
            or query in (row.get("article_names") or "").lower()
            or query in (row.get("internal_notes") or "").lower()
            or query in (row.get("status") or "").lower()
            or any(
                query in str(item.get("article_name") or "").lower()
                or query in str(item.get("name_of_beneficiary") or "").lower()
                or query in str(item.get("name_of_institution") or "").lower()
                or query in str(item.get("aadhar_number") or "").lower()
                or query in str(item.get("notes") or "").lower()
                or query in str(item.get("cheque_rtgs_in_favour") or "").lower()
                for item in row.get("detail_items", [])
            )
        ]

    if date_from:
        summaries = [row for row in summaries if row["created_at"].date().isoformat() >= date_from]
    if date_to:
        summaries = [row for row in summaries if row["created_at"].date().isoformat() <= date_to]
    if status_filter:
        summaries = [row for row in summaries if (row.get("status") or "") == status_filter]

    reverse = sort_dir == "desc"
    sort_map = {
        "application_number": lambda row: row["application_number"] or "",
        "district_name": lambda row: row["district_name"] or "",
        "total_accrued": lambda row: row["total_accrued"] or 0,
        "remaining_fund": lambda row: row["remaining_fund"] or 0,
        "status": lambda row: row.get("status") or "",
        "created_at": lambda row: row["created_at"],
    }
    if sort_by in sort_map:
        summaries = sorted(summaries, key=sort_map[sort_by], reverse=reverse)
    return summaries


def _district_form_context(district=None, entries=None, errors=None):
    articles = list(models.Article.objects.filter(is_active=True).order_by("article_name"))
    districts_queryset = models.DistrictMaster.objects.filter(is_active=True)
    if district is None:
        used_district_ids = models.DistrictBeneficiaryEntry.objects.values_list("district_id", flat=True).distinct()
        districts_queryset = districts_queryset.exclude(id__in=used_district_ids)
    districts = list(districts_queryset.order_by("district_name"))
    return {
        "district_master_list": districts,
        "articles_master_list": articles,
        "selected_district": district,
        "entry_rows": entries or [],
        "form_errors": errors or [],
        "form_successes": [],
        "application_status": (entries[0]["status"] if entries and isinstance(entries[0], dict) and entries[0].get("status") else ""),
        "internal_notes": (entries[0].get("internal_notes", "") if entries and isinstance(entries[0], dict) else ""),
    }


def _parse_district_rows(post_data):
    article_ids = post_data.getlist("article_id")
    quantities = post_data.getlist("quantity")
    unit_costs = post_data.getlist("unit_cost")
    notes_list = post_data.getlist("notes")
    name_of_beneficiary_list = post_data.getlist("name_of_beneficiary")
    name_of_institution_list = post_data.getlist("name_of_institution")
    aadhar_number_list = post_data.getlist("aadhar_number")
    cheque_rtgs_list = post_data.getlist("cheque_rtgs_in_favour")
    rows = []
    max_len = max(
        len(article_ids),
        len(quantities),
        len(unit_costs),
        len(notes_list),
        len(name_of_beneficiary_list),
        len(name_of_institution_list),
        len(aadhar_number_list),
        len(cheque_rtgs_list),
        0,
    )
    for idx in range(max_len):
        rows.append(
            {
                "article_id": (article_ids[idx] if idx < len(article_ids) else "").strip(),
                "quantity": (quantities[idx] if idx < len(quantities) else "").strip(),
                "unit_cost": (unit_costs[idx] if idx < len(unit_costs) else "").strip(),
                "notes": (notes_list[idx] if idx < len(notes_list) else "").strip(),
                "name_of_beneficiary": (name_of_beneficiary_list[idx] if idx < len(name_of_beneficiary_list) else "").strip(),
                "name_of_institution": (name_of_institution_list[idx] if idx < len(name_of_institution_list) else "").strip(),
                "aadhar_number": (aadhar_number_list[idx] if idx < len(aadhar_number_list) else "").strip(),
                "cheque_rtgs_in_favour": (cheque_rtgs_list[idx] if idx < len(cheque_rtgs_list) else "").strip(),
            }
        )
    return [row for row in rows if any(row.values())]


def _validate_and_build_district_entries(district, raw_rows, *, internal_notes=""):
    errors = []
    built_rows = []
    seen_articles = set()

    if not raw_rows:
        errors.append("Add at least one article or aid item.")
        return built_rows, errors

    article_map = {
        str(article.id): article
        for article in models.Article.objects.filter(id__in=[row["article_id"] for row in raw_rows if row["article_id"]])
    }

    for index, row in enumerate(raw_rows, start=1):
        article = article_map.get(row["article_id"])
        if not article:
            errors.append(f"Row {index}: select a valid article.")
            continue

        try:
            quantity = int(row["quantity"])
            if quantity <= 0:
                raise ValueError
        except (TypeError, ValueError):
            errors.append(f"Row {index}: quantity must be greater than 0.")
            continue

        if article.item_type != models.ItemTypeChoices.AID and article.id in seen_articles:
            errors.append(f"Row {index}: {article.article_name} can be added only once.")
            continue

        if article.cost_per_unit and article.cost_per_unit > 0:
            unit_cost = article.cost_per_unit
        else:
            try:
                unit_cost = Decimal(row["unit_cost"])
                if unit_cost < 0:
                    raise ValueError
            except (InvalidOperation, TypeError, ValueError):
                errors.append(f"Row {index}: enter a valid price for {article.article_name}.")
                continue

        total_amount = unit_cost * quantity
        built_rows.append(
            {
                "district": district,
                "application_number": district.application_number,
                "article": article,
                "article_cost_per_unit": unit_cost,
                "quantity": quantity,
                "total_amount": total_amount,
                "name_of_beneficiary": row.get("name_of_beneficiary") or None,
                "name_of_institution": row["name_of_institution"] or None,
                "aadhar_number": row["aadhar_number"] or None,
                "cheque_rtgs_in_favour": row["cheque_rtgs_in_favour"] or None,
                "notes": row["notes"] or None,
                "internal_notes": internal_notes or None,
                "status": models.BeneficiaryStatusChoices.PENDING,
            }
        )
        if article.item_type != models.ItemTypeChoices.AID:
            seen_articles.add(article.id)

    return built_rows, errors


def _timestamp_conflict_token(value):
    if not value:
        return ""
    return timezone.localtime(value).isoformat()


def _district_conflict_token(district):
    if not district:
        return ""
    latest = (
        models.DistrictBeneficiaryEntry.objects.filter(district=district)
        .order_by("-updated_at")
        .values_list("updated_at", flat=True)
        .first()
    )
    return _timestamp_conflict_token(latest)


def _public_conflict_token(entry):
    if not entry:
        return ""
    return _timestamp_conflict_token(entry.updated_at)


def _institution_conflict_token(application_number):
    if not application_number:
        return ""
    latest = (
        models.InstitutionsBeneficiaryEntry.objects.filter(application_number=application_number)
        .order_by("-updated_at")
        .values_list("updated_at", flat=True)
        .first()
    )
    return _timestamp_conflict_token(latest)


def _conflict_message(label):
    return (
        f"This {label} was updated after you opened this page. "
        f"We stopped the save so newer changes are not overwritten. "
        f"Please review the latest version and then try again."
    )


class DistrictMasterEntryBaseView(LoginRequiredMixin, WriteRoleMixin, TemplateView):
    module_key = models.ModuleKeyChoices.APPLICATION_ENTRY
    permission_action = "create_edit"
    template_name = "dashboard/master_entry_district_form.html"

    def get_district(self):
        district_id = self.kwargs.get("district_id")
        if district_id:
            return models.DistrictMaster.objects.get(pk=district_id, is_active=True)
        return None

    def _render_form(self, district=None, entries=None, errors=None):
        context = self.get_context_data(**_district_form_context(district=district, entries=entries, errors=errors))
        context.update(_district_attachment_context(district))
        context["conflict_token"] = _district_conflict_token(district)
        return self.render_to_response(context)

    def _save_entries(self, district, rows, *, replace=False):
        action = (self.request.POST.get("action") or "draft").strip().lower()
        internal_notes = (self.request.POST.get("internal_notes") or "").strip()
        target_status = models.BeneficiaryStatusChoices.SUBMITTED if action == "submit" else models.BeneficiaryStatusChoices.DRAFT
        built_rows, errors = _validate_and_build_district_entries(district, rows, internal_notes=internal_notes)
        for built in built_rows:
            built["status"] = target_status
        if errors:
            hydrated_rows = []
            article_lookup = {str(article.id): article for article in models.Article.objects.filter(is_active=True)}
            for row in rows:
                article = article_lookup.get(row["article_id"])
                hydrated_rows.append(
                    {
                        "article_id": row["article_id"],
                        "quantity": row["quantity"],
                        "unit_cost": row["unit_cost"],
                        "notes": row["notes"],
                        "name_of_beneficiary": row.get("name_of_beneficiary", ""),
                        "name_of_institution": row.get("name_of_institution", ""),
                        "aadhar_number": row.get("aadhar_number", ""),
                        "cheque_rtgs_in_favour": row.get("cheque_rtgs_in_favour", ""),
                        "article_name": article.article_name if article else "",
                        "item_type": article.item_type if article else "",
                        "internal_notes": internal_notes,
                    }
                )
            return self._render_form(district=district, entries=hydrated_rows, errors=errors)

        with transaction.atomic():
            if replace:
                existing_entries = list(
                    models.DistrictBeneficiaryEntry.objects.filter(district=district).select_related("article").order_by("id")
                )
                previous_status = existing_entries[0].status if existing_entries else None
                before_snapshot = _district_audit_snapshot(district)
                _sync_district_entries(existing_entries, built_rows, self.request.user)
                after_snapshot = _district_audit_snapshot(district)
                services.log_audit(
                    user=self.request.user,
                    action_type=models.ActionTypeChoices.UPDATE,
                    entity_type="district_application",
                    entity_id=str(district.id),
                    details={"before": before_snapshot, "after": after_snapshot},
                    **_request_audit_meta(self.request),
                )
                if previous_status != target_status:
                    services.log_audit(
                        user=self.request.user,
                        action_type=models.ActionTypeChoices.STATUS_CHANGE,
                        entity_type="district_application",
                        entity_id=str(district.id),
                        details={"from": previous_status, "to": target_status},
                        **_request_audit_meta(self.request),
                    )
            else:
                for built in built_rows:
                    models.DistrictBeneficiaryEntry.objects.create(created_by=self.request.user, **built)
                services.log_audit(
                    user=self.request.user,
                    action_type=models.ActionTypeChoices.CREATE,
                    entity_type="district_application",
                    entity_id=str(district.id),
                    details={"after": _district_audit_snapshot(district)},
                    **_request_audit_meta(self.request),
                )
                services.log_audit(
                    user=self.request.user,
                    action_type=models.ActionTypeChoices.STATUS_CHANGE,
                    entity_type="district_application",
                    entity_id=str(district.id),
                    details={"from": None, "to": target_status},
                    **_request_audit_meta(self.request),
                )
        return None


class DistrictMasterEntryCreateView(DistrictMasterEntryBaseView):
    def get(self, request, *args, **kwargs):
        return self._render_form()

    def post(self, request, *args, **kwargs):
        district_id = request.POST.get("district_id")
        if not district_id:
            return self._render_form(errors=["Select a district."])
        try:
            district = models.DistrictMaster.objects.get(pk=district_id, is_active=True)
        except models.DistrictMaster.DoesNotExist:
            return self._render_form(errors=["Select a valid district."])

        if models.DistrictBeneficiaryEntry.objects.filter(district=district).exists():
            return self._render_form(district=district, errors=["This district already has an entry. Use modify instead."])

        rows = _parse_district_rows(request.POST)
        response = self._save_entries(district, rows, replace=False)
        if response is not None:
            return response
        action = (request.POST.get("action") or "draft").strip().lower()
        if action == "submit":
            messages.success(request, "District application submitted.")
            return HttpResponseRedirect(reverse("ui:master-entry"))
        else:
            messages.success(request, "District application saved as draft.")
            return HttpResponseRedirect(reverse("ui:master-entry-district-edit", kwargs={"district_id": district.id}))


class DistrictMasterEntryUpdateView(DistrictMasterEntryBaseView):
    def get(self, request, *args, **kwargs):
        district = self.get_district()
        entries = list(models.DistrictBeneficiaryEntry.objects.filter(district=district).select_related("article").order_by("id"))
        if entries and entries[0].status == models.BeneficiaryStatusChoices.SUBMITTED:
            messages.error(request, "This district application is submitted and locked. Reopen it first.")
            return HttpResponseRedirect(reverse("ui:master-entry"))
        hydrated = [
            {
                "article_id": str(entry.article_id),
                "quantity": entry.quantity,
                "unit_cost": entry.article_cost_per_unit,
                "notes": entry.notes or "",
                "name_of_beneficiary": entry.name_of_beneficiary or "",
                "name_of_institution": entry.name_of_institution or "",
                "aadhar_number": entry.aadhar_number or "",
                "cheque_rtgs_in_favour": entry.cheque_rtgs_in_favour or "",
                "article_name": entry.article.article_name,
                "item_type": entry.article.item_type,
                "status": entry.status,
                "internal_notes": entry.internal_notes or "",
            }
            for entry in entries
        ]
        return self._render_form(district=district, entries=hydrated)

    def post(self, request, *args, **kwargs):
        district = self.get_district()
        locked_entries = list(models.DistrictBeneficiaryEntry.objects.filter(district=district).order_by("id"))
        if locked_entries and locked_entries[0].status == models.BeneficiaryStatusChoices.SUBMITTED:
            messages.error(request, "This district application is submitted and locked. Reopen it first.")
            return HttpResponseRedirect(reverse("ui:master-entry"))
        submitted_conflict_token = request.POST.get("_conflict_token", "")
        current_conflict_token = _district_conflict_token(district)
        if submitted_conflict_token and current_conflict_token and submitted_conflict_token != current_conflict_token:
            messages.error(request, _conflict_message("district application"), extra_tags="persistent")
            return HttpResponseRedirect(reverse("ui:master-entry-district-edit", kwargs={"district_id": district.id}))
        rows = _parse_district_rows(request.POST)
        response = self._save_entries(district, rows, replace=True)
        if response is not None:
            return response
        action = (request.POST.get("action") or "draft").strip().lower()
        if action == "submit":
            messages.success(request, "District application submitted.")
            return HttpResponseRedirect(reverse("ui:master-entry"))
        else:
            messages.success(request, "District application saved as draft.")
            return HttpResponseRedirect(reverse("ui:master-entry-district-edit", kwargs={"district_id": district.id}))


class DistrictMasterEntryDetailView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    module_key = models.ModuleKeyChoices.APPLICATION_ENTRY
    permission_action = "view"
    template_name = "dashboard/master_entry_district_detail.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        district = models.DistrictMaster.objects.get(pk=self.kwargs["district_id"], is_active=True)
        entries = list(models.DistrictBeneficiaryEntry.objects.filter(district=district).select_related("article").order_by("id"))
        total_accrued = sum((entry.total_amount or 0) for entry in entries)
        total_quantity = sum((entry.quantity or 0) for entry in entries)
        status = entries[0].status if entries else ""
        context.update(
            {
                "district": district,
                "entries": entries,
                "total_accrued": total_accrued,
                "total_quantity": total_quantity,
                "remaining_fund": (district.allotted_budget or 0) - total_accrued,
                "application_status": status,
            }
        )
        context.update(_district_attachment_context(district))
        return context


class DistrictMasterEntryDeleteView(LoginRequiredMixin, AdminRequiredMixin, View):
    module_key = models.ModuleKeyChoices.APPLICATION_ENTRY
    permission_action = "delete"
    def post(self, request, *args, **kwargs):
        district = models.DistrictMaster.objects.get(pk=kwargs["district_id"], is_active=True)
        snapshot = _district_audit_snapshot(district)
        models.DistrictBeneficiaryEntry.objects.filter(district=district).delete()
        services.log_audit(
            user=request.user,
            action_type=models.ActionTypeChoices.DELETE,
            entity_type="district_application",
            entity_id=str(district.id),
            details={"before": snapshot},
            **_request_audit_meta(request),
        )
        messages.warning(request, "District entry deleted.")
        return HttpResponseRedirect(reverse("ui:master-entry"))


class DistrictMasterEntryReopenView(LoginRequiredMixin, AdminRequiredMixin, View):
    module_key = models.ModuleKeyChoices.APPLICATION_ENTRY
    permission_action = "reopen"
    def post(self, request, *args, **kwargs):
        district = models.DistrictMaster.objects.get(pk=kwargs["district_id"], is_active=True)
        models.DistrictBeneficiaryEntry.objects.filter(district=district).update(status=models.BeneficiaryStatusChoices.DRAFT)
        services.log_audit(
            user=request.user,
            action_type=models.ActionTypeChoices.STATUS_CHANGE,
            entity_type="district_application",
            entity_id=str(district.id),
            details={"from": models.BeneficiaryStatusChoices.SUBMITTED, "to": models.BeneficiaryStatusChoices.DRAFT},
            **_request_audit_meta(request),
        )
        messages.success(request, "District application reopened as draft.")
        return HttpResponseRedirect(reverse("ui:master-entry"))


def _public_history_matches(aadhar_number):
    if not aadhar_number:
        return []
    return list(
        models.PublicBeneficiaryHistory.objects.filter(
            Q(aadhar_number=aadhar_number) | Q(aadhar_number_sp=aadhar_number)
        ).order_by("-year", "name")[:10]
    )


def _public_history_summary(history_matches):
    items = []
    for row in history_matches or []:
        year = getattr(row, "year", "") or "-"
        article = getattr(row, "article_name", "") or "-"
        items.append(f"{year}: {article}")
    return "; ".join(items)


def _public_current_match(aadhar_number, *, exclude_pk=None):
    if not aadhar_number:
        return None
    queryset = models.PublicBeneficiaryEntry.objects.select_related("article").filter(aadhar_number=aadhar_number)
    if exclude_pk:
        queryset = queryset.exclude(pk=exclude_pk)
    return queryset.order_by("-created_at").first()


def _public_form_context(entry=None, form_data=None, history_matches=None, current_match=None, warnings=None, errors=None, successes=None, allow_duplicate_save=False):
    entry = entry or {}
    return {
        "public_entry": entry,
        "public_form_data": form_data or {},
        "history_matches": history_matches or [],
        "history_summary": _public_history_summary(history_matches or []),
        "current_match": current_match,
        "form_warnings": warnings or [],
        "form_errors": errors or [],
        "form_successes": [],
        "allow_duplicate_save": allow_duplicate_save,
        "articles_master_list": list(models.Article.objects.filter(is_active=True).order_by("article_name")),
        "gender_choices": models.GenderChoices.choices,
        "female_status_choices": models.FemaleStatusChoices.choices,
        "disability_category_choices": models.DisabilityCategoryChoices.choices,
        "female_status_descriptions": FEMALE_STATUS_DESCRIPTIONS,
        "application_status": getattr(entry, "status", ""),
    }


def _build_public_form_data(post_data):
    disability_category = (post_data.get("disability_category") or "").strip()
    is_handicapped = post_data.get("is_handicapped", "")
    if disability_category:
        is_handicapped = "true"
    return {
        "aadhar_number": (post_data.get("aadhar_number") or "").strip(),
        "name": (post_data.get("name") or "").strip(),
        "is_handicapped": is_handicapped,
        "disability_category": disability_category,
        "gender": (post_data.get("gender") or "").strip(),
        "female_status": (post_data.get("female_status") or "").strip(),
        "address": (post_data.get("address") or "").strip(),
        "mobile": (post_data.get("mobile") or "").strip(),
        "article_id": (post_data.get("article_id") or "").strip(),
        "article_cost_per_unit": (post_data.get("article_cost_per_unit") or "").strip(),
        "quantity": (post_data.get("quantity") or "").strip(),
        "name_of_institution": (post_data.get("name_of_institution") or "").strip(),
        "cheque_rtgs_in_favour": (post_data.get("cheque_rtgs_in_favour") or "").strip(),
        "notes": (post_data.get("notes") or "").strip(),
    }


def _validate_public_form(form_data, *, require_complete=True):
    errors = []
    article = None

    aadhar_number = form_data["aadhar_number"]
    if require_complete:
        if not (aadhar_number.isdigit() and len(aadhar_number) == 12):
            errors.append("Aadhaar number must be a valid 12-digit number.")
    elif aadhar_number and not (aadhar_number.isdigit() and len(aadhar_number) == 12):
        errors.append("Aadhaar number must be a valid 12-digit number.")

    if require_complete and not form_data["name"]:
        errors.append("Name is required.")

    if require_complete and form_data["is_handicapped"] not in {"true", "false"}:
        errors.append("Handicapped status is required.")

    if form_data["is_handicapped"] == "true":
        valid_disability_values = {value for value, _label in models.DisabilityCategoryChoices.choices}
        if require_complete and not form_data["disability_category"]:
            errors.append("Disability category is required when handicapped is Yes.")
        elif form_data["disability_category"] and form_data["disability_category"] not in valid_disability_values:
            errors.append("Select a valid disability category.")

    if require_complete and not form_data["gender"]:
        errors.append("Gender is required.")
    elif form_data["gender"] == models.GenderChoices.FEMALE and require_complete and not form_data["female_status"]:
        errors.append("Gender Category is required when gender is Female.")

    if require_complete and not form_data["address"]:
        errors.append("Address is required.")

    if require_complete and not form_data["mobile"]:
        errors.append("Mobile number is required.")
    elif form_data["mobile"]:
        mobile_numbers = [value.strip() for value in form_data["mobile"].split("&") if value.strip()]
        if not mobile_numbers and require_complete:
            errors.append("Mobile number is required.")
        elif mobile_numbers and any((not number.isdigit()) or len(number) != 10 for number in mobile_numbers):
            errors.append("Each mobile number must be exactly 10 digits.")

    if require_complete and not form_data["article_id"]:
        errors.append("Select an article or aid.")
    elif form_data["article_id"]:
        try:
            article = models.Article.objects.get(pk=form_data["article_id"], is_active=True)
        except models.Article.DoesNotExist:
            errors.append("Select a valid article or aid.")

    quantity = 1
    quantity_raw = form_data["quantity"]
    if require_complete or form_data["article_id"] or quantity_raw:
        try:
            quantity = int(quantity_raw or 0)
            if quantity <= 0:
                raise ValueError
        except (TypeError, ValueError):
            errors.append("Quantity must be greater than 0.")
            quantity = 0

    unit_cost = None
    if article:
        if article.cost_per_unit and article.cost_per_unit > 0:
            unit_cost = article.cost_per_unit
        else:
            try:
                unit_cost = Decimal(form_data["article_cost_per_unit"])
                if unit_cost < 0:
                    raise ValueError
            except (InvalidOperation, TypeError, ValueError):
                errors.append("Enter a valid cost per unit.")

    return article, quantity, unit_cost, errors


def _build_institution_entry_summaries():
    entries = list(
        models.InstitutionsBeneficiaryEntry.objects.select_related("article").order_by("-created_at")
    )
    grouped = {}
    for entry in entries:
        key = entry.application_number or str(entry.pk)
        grouped.setdefault(key, []).append(entry)

    attachment_map = _institution_attachment_preview_map(list(grouped.keys()))
    attachment_lists = _institution_attachment_preview_lists(list(grouped.keys()))
    summaries = []
    for application_number, group_entries in grouped.items():
        first = group_entries[0]
        attachment = attachment_map.get(application_number)
        attachment_items = [_attachment_preview_payload(item) for item in attachment_lists.get(application_number, [])]
        attachment_items = [item for item in attachment_items if item]
        summaries.append(
            {
                "application_number": application_number,
                "institution_name": first.institution_name,
                "institution_type": first.get_institution_type_display(),
                "article_names": ", ".join(sorted({entry.article.article_name for entry in group_entries})),
                "article_count": len({entry.article_id for entry in group_entries if entry.article_id}),
                "total_quantity": sum((row.quantity or 0) for row in group_entries),
                "total_value": sum((row.total_amount or 0) for row in group_entries),
                "status": first.status,
                "internal_notes": first.internal_notes or "",
                "created_at": max(row.created_at for row in group_entries),
                "address": first.address,
                "mobile": first.mobile,
                "attachment_id": attachment.id if attachment else None,
                "attachment_preview_url": reverse("ui:application-attachment-download", kwargs={"attachment_id": attachment.id}) if attachment else "",
                "attachment_source": (attachment.file.name or "").lower() if attachment and attachment.file else "",
                "attachment_title": _attachment_preview_title(attachment),
                "attachment_count": len(attachment_items),
                "attachment_items_json": json.dumps(attachment_items),
                "attachment_items_b64": _attachment_items_b64(attachment_items),
                "detail_items": [
                    {
                        "article_name": entry.article.article_name,
                        "quantity": entry.quantity,
                        "unit_cost": entry.article_cost_per_unit,
                        "total_amount": entry.total_amount,
                        "name_of_beneficiary": entry.name_of_beneficiary,
                        "name_of_institution": entry.name_of_institution,
                        "aadhar_number": entry.aadhar_number,
                        "notes": entry.notes,
                        "cheque_rtgs_in_favour": entry.cheque_rtgs_in_favour,
                        "changed_at": entry.updated_at,
                    }
                    for entry in group_entries
                ],
            }
        )
    summaries.sort(key=lambda row: row["application_number"])
    return summaries


def _filter_sort_public_entries(queryset, *, search_query="", date_from="", date_to="", status_filter="", sort_by="", sort_dir="desc"):
    if search_query:
        query_filter = (
            Q(application_number__icontains=search_query)
            | Q(name__icontains=search_query)
            | Q(aadhar_number__icontains=search_query)
            | Q(address__icontains=search_query)
            | Q(mobile__icontains=search_query)
            | Q(article__article_name__icontains=search_query)
            | Q(name_of_institution__icontains=search_query)
            | Q(notes__icontains=search_query)
            | Q(cheque_rtgs_in_favour__icontains=search_query)
        )
        queryset = queryset.filter(query_filter)
    if date_from:
        queryset = queryset.filter(created_at__date__gte=date_from)
    if date_to:
        queryset = queryset.filter(created_at__date__lte=date_to)
    if status_filter:
        queryset = queryset.filter(status=status_filter)

    ordering_map = {
        "application_number": "application_number",
        "name": "name",
        "aadhar_number": "aadhar_number",
        "total_amount": "total_amount",
        "status": "status",
        "created_at": "created_at",
    }
    ordering = ordering_map.get(sort_by, "created_at")
    if sort_dir == "desc":
        ordering = f"-{ordering}"
    return queryset.order_by(ordering)


def _filter_sort_institution_summaries(summaries, *, search_query="", date_from="", date_to="", status_filter="", sort_by="", sort_dir="desc"):
    if search_query:
        query = search_query.lower()
        summaries = [
            row for row in summaries
            if query in (row["application_number"] or "").lower()
            or query in (row["institution_name"] or "").lower()
            or query in (row.get("institution_type") or "").lower()
            or query in (row.get("article_names") or "").lower()
            or query in (row.get("internal_notes") or "").lower()
            or query in (row.get("address") or "").lower()
            or query in (row.get("mobile") or "").lower()
            or query in (row.get("status") or "").lower()
            or any(
                query in str(item.get("article_name") or "").lower()
                or query in str(item.get("name_of_beneficiary") or "").lower()
                or query in str(item.get("name_of_institution") or "").lower()
                or query in str(item.get("aadhar_number") or "").lower()
                or query in str(item.get("notes") or "").lower()
                or query in str(item.get("cheque_rtgs_in_favour") or "").lower()
                for item in row.get("detail_items", [])
            )
        ]

    if date_from:
        summaries = [row for row in summaries if row["created_at"].date().isoformat() >= date_from]
    if date_to:
        summaries = [row for row in summaries if row["created_at"].date().isoformat() <= date_to]
    if status_filter:
        summaries = [row for row in summaries if (row.get("status") or "") == status_filter]

    reverse = sort_dir == "desc"
    sort_map = {
        "application_number": lambda row: row["application_number"] or "",
        "institution_name": lambda row: row["institution_name"] or "",
        "total_value": lambda row: row["total_value"] or 0,
        "status": lambda row: row.get("status") or "",
        "created_at": lambda row: row["created_at"],
    }
    if sort_by in sort_map:
        summaries = sorted(summaries, key=sort_map[sort_by], reverse=reverse)
    return summaries


def _institution_form_context(form_data=None, rows=None, errors=None, application_number=None):
    return {
        "institution_form_data": form_data or {},
        "institution_rows": rows or [],
        "form_errors": errors or [],
        "articles_master_list": list(models.Article.objects.filter(is_active=True).order_by("article_name")),
        "institution_type_choices": models.InstitutionTypeChoices.choices,
        "institution_application_number": application_number,
        "application_status": (rows[0]["status"] if rows and isinstance(rows[0], dict) and rows[0].get("status") else ""),
        "internal_notes": (form_data or {}).get("internal_notes", ""),
    }


def _build_institution_form_data(post_data):
    return {
        "institution_name": (post_data.get("institution_name") or "").strip(),
        "institution_type": (post_data.get("institution_type") or "").strip(),
        "address": (post_data.get("address") or "").strip(),
        "mobile": (post_data.get("mobile") or "").strip(),
        "internal_notes": (post_data.get("internal_notes") or "").strip(),
    }


def _validate_institution_rows(raw_rows, *, require_complete=True, internal_notes=""):
    errors = []
    built_rows = []
    seen_articles = set()
    if not raw_rows:
        errors.append("Add at least one article or aid item.")
        return built_rows, errors

    article_map = {
        str(article.id): article
        for article in models.Article.objects.filter(id__in=[row["article_id"] for row in raw_rows if row["article_id"]])
    }

    for index, row in enumerate(raw_rows, start=1):
        article = article_map.get(row["article_id"])
        if not article:
            errors.append(f"Row {index}: select a valid article.")
            continue

        try:
            quantity = int(row["quantity"])
            if quantity <= 0:
                raise ValueError
        except (TypeError, ValueError):
            errors.append(f"Row {index}: quantity must be greater than 0.")
            continue

        if article.item_type != models.ItemTypeChoices.AID and article.id in seen_articles:
            errors.append(f"Row {index}: {article.article_name} can be added only once.")
            continue

        if article.cost_per_unit and article.cost_per_unit > 0:
            unit_cost = article.cost_per_unit
        else:
            try:
                unit_cost = Decimal(row["unit_cost"])
                if unit_cost < 0:
                    raise ValueError
            except (InvalidOperation, TypeError, ValueError):
                errors.append(f"Row {index}: enter a valid price for {article.article_name}.")
                continue

        built_rows.append(
            {
                "article": article,
                "article_cost_per_unit": unit_cost,
                "quantity": quantity,
                "total_amount": unit_cost * quantity,
                "name_of_beneficiary": row.get("name_of_beneficiary") or None,
                "name_of_institution": row.get("name_of_institution") or None,
                "aadhar_number": row.get("aadhar_number") or None,
                "cheque_rtgs_in_favour": row.get("cheque_rtgs_in_favour") or None,
                "notes": row["notes"] or None,
                "internal_notes": internal_notes or None,
            }
        )
        if article.item_type != models.ItemTypeChoices.AID:
            seen_articles.add(article.id)
    return built_rows, errors


def _sync_district_entries(existing_entries, built_rows, user):
    by_article = {}
    for entry in existing_entries:
        by_article.setdefault(entry.article_id, []).append(entry)

    used_ids = set()
    for built in built_rows:
        candidates = by_article.get(built["article"].id, [])
        match = next((entry for entry in candidates if entry.id not in used_ids), None)
        if match is None:
            models.DistrictBeneficiaryEntry.objects.create(created_by=user, **built)
            continue

        changed = False
        if match.application_number != built["application_number"]:
            match.application_number = built["application_number"]
            changed = True
        if match.article_id != built["article"].id:
            match.article = built["article"]
            changed = True
        if match.article_cost_per_unit != built["article_cost_per_unit"]:
            match.article_cost_per_unit = built["article_cost_per_unit"]
            changed = True
        if match.quantity != built["quantity"]:
            match.quantity = built["quantity"]
            changed = True
        if match.total_amount != built["total_amount"]:
            match.total_amount = built["total_amount"]
            changed = True
        if match.name_of_beneficiary != built.get("name_of_beneficiary"):
            match.name_of_beneficiary = built.get("name_of_beneficiary")
            changed = True
        if match.name_of_institution != built.get("name_of_institution"):
            match.name_of_institution = built.get("name_of_institution")
            changed = True
        if match.aadhar_number != built.get("aadhar_number"):
            match.aadhar_number = built.get("aadhar_number")
            changed = True
        if match.cheque_rtgs_in_favour != built.get("cheque_rtgs_in_favour"):
            match.cheque_rtgs_in_favour = built.get("cheque_rtgs_in_favour")
            changed = True
        if match.notes != built["notes"]:
            match.notes = built["notes"]
            changed = True
        if match.internal_notes != built.get("internal_notes"):
            match.internal_notes = built.get("internal_notes")
            changed = True
        if match.status != built["status"]:
            match.status = built["status"]
            changed = True
        if not match.created_by_id:
            match.created_by = user
            changed = True
        if changed:
            match.save()
        used_ids.add(match.id)

    for entry in existing_entries:
        if entry.id not in used_ids:
            entry.delete()


def _sync_institution_entries(existing_entries, built_rows, user, *, application_number, form_data):
    by_article = {}
    for entry in existing_entries:
        by_article.setdefault(entry.article_id, []).append(entry)

    used_ids = set()
    for built in built_rows:
        candidates = by_article.get(built["article"].id, [])
        match = next((entry for entry in candidates if entry.id not in used_ids), None)
        if match is None:
            models.InstitutionsBeneficiaryEntry.objects.create(
                created_by=user,
                application_number=application_number,
                institution_name=form_data["institution_name"],
                institution_type=form_data["institution_type"],
                address=form_data["address"] or None,
                mobile=form_data["mobile"] or None,
                **built,
            )
            continue

        changed = False
        if match.application_number != application_number:
            match.application_number = application_number
            changed = True
        if match.institution_name != form_data["institution_name"]:
            match.institution_name = form_data["institution_name"]
            changed = True
        if match.institution_type != form_data["institution_type"]:
            match.institution_type = form_data["institution_type"]
            changed = True
        address = form_data["address"] or None
        if match.address != address:
            match.address = address
            changed = True
        mobile = form_data["mobile"] or None
        if match.mobile != mobile:
            match.mobile = mobile
            changed = True
        if match.article_id != built["article"].id:
            match.article = built["article"]
            changed = True
        if match.article_cost_per_unit != built["article_cost_per_unit"]:
            match.article_cost_per_unit = built["article_cost_per_unit"]
            changed = True
        if match.quantity != built["quantity"]:
            match.quantity = built["quantity"]
            changed = True
        if match.total_amount != built["total_amount"]:
            match.total_amount = built["total_amount"]
            changed = True
        if match.name_of_beneficiary != built.get("name_of_beneficiary"):
            match.name_of_beneficiary = built.get("name_of_beneficiary")
            changed = True
        if match.name_of_institution != built.get("name_of_institution"):
            match.name_of_institution = built.get("name_of_institution")
            changed = True
        if match.aadhar_number != built.get("aadhar_number"):
            match.aadhar_number = built.get("aadhar_number")
            changed = True
        if match.cheque_rtgs_in_favour != built.get("cheque_rtgs_in_favour"):
            match.cheque_rtgs_in_favour = built.get("cheque_rtgs_in_favour")
            changed = True
        if match.notes != built["notes"]:
            match.notes = built["notes"]
            changed = True
        if match.internal_notes != built.get("internal_notes"):
            match.internal_notes = built.get("internal_notes")
            changed = True
        if match.status != built["status"]:
            match.status = built["status"]
            changed = True
        if not match.created_by_id:
            match.created_by = user
            changed = True
        if changed:
            match.save()
        used_ids.add(match.id)

    for entry in existing_entries:
        if entry.id not in used_ids:
            entry.delete()


class PublicMasterEntryBaseView(LoginRequiredMixin, WriteRoleMixin, TemplateView):
    module_key = models.ModuleKeyChoices.APPLICATION_ENTRY
    permission_action = "create_edit"
    template_name = "dashboard/master_entry_public_form.html"

    def get_entry(self):
        pk = self.kwargs.get("pk")
        if pk:
            return models.PublicBeneficiaryEntry.objects.select_related("article").get(pk=pk)
        return None

    def _render_form(self, *, entry=None, form_data=None, history_matches=None, current_match=None, warnings=None, errors=None, successes=None, allow_duplicate_save=False):
        context = self.get_context_data(
            **_public_form_context(
                entry=entry,
                form_data=form_data,
                history_matches=history_matches,
                current_match=current_match,
                warnings=warnings,
                errors=errors,
                successes=successes,
                allow_duplicate_save=allow_duplicate_save,
            )
        )
        context.update(_public_attachment_context(entry))
        context["conflict_token"] = _public_conflict_token(entry)
        return self.render_to_response(context)

    def _save_entry(self, *, entry=None, form_data=None):
        action = (self.request.POST.get("action") or "draft").strip().lower()
        target_status = models.BeneficiaryStatusChoices.SUBMITTED if action == "submit" else models.BeneficiaryStatusChoices.DRAFT
        require_complete = target_status == models.BeneficiaryStatusChoices.SUBMITTED
        article, quantity, unit_cost, errors = _validate_public_form(form_data, require_complete=require_complete)
        if not require_complete and article is None:
            errors.append("Select an article or aid before saving draft.")
        history_matches = _public_history_matches(form_data["aadhar_number"])
        current_match = _public_current_match(form_data["aadhar_number"], exclude_pk=getattr(entry, "pk", None))
        warnings = ["This Aadhaar number exists in past beneficiary history."] if history_matches else []
        if current_match:
            warnings.append("Duplicate found in current applications.")
        if errors:
            return self._render_form(
                entry=entry,
                form_data=form_data,
                history_matches=history_matches,
                current_match=current_match,
                warnings=warnings,
                errors=errors,
            ), None

        if current_match:
            return self._render_form(
                entry=entry,
                form_data=form_data,
                history_matches=history_matches,
                current_match=current_match,
                warnings=warnings + ["Duplicate found in current applications. Review the existing record below and use Modify if you want to update it."],
            ), None

        if entry is None:
            entry = models.PublicBeneficiaryEntry(application_number=f"DRAFT-PUB-{uuid.uuid4().hex[:12].upper()}")
            action_type = models.ActionTypeChoices.CREATE
            before_snapshot = None
            previous_status = None
        else:
            action_type = models.ActionTypeChoices.UPDATE
            before_snapshot = _public_audit_snapshot(entry)
            previous_status = entry.status

        entry.name = form_data["name"]
        entry.aadhar_number = form_data["aadhar_number"]
        entry.is_handicapped = form_data["disability_category"] or models.HandicappedStatusChoices.NO
        entry.gender = form_data["gender"]
        entry.female_status = form_data["female_status"] or None
        entry.address = form_data["address"] or None
        entry.mobile = form_data["mobile"]
        entry.article = article
        entry.article_cost_per_unit = unit_cost
        entry.quantity = quantity
        entry.total_amount = unit_cost * quantity
        entry.name_of_institution = form_data["name_of_institution"] or None
        entry.cheque_rtgs_in_favour = form_data["cheque_rtgs_in_favour"] or None
        entry.notes = form_data["notes"] or None
        if target_status == models.BeneficiaryStatusChoices.SUBMITTED and (not entry.application_number or str(entry.application_number).startswith("DRAFT-PUB-")):
            entry.application_number = services.next_public_application_number()
        entry.status = target_status
        if not entry.created_by_id:
            entry.created_by = self.request.user
        entry.save()
        services.log_audit(
            user=self.request.user,
            action_type=action_type,
            entity_type="public_application",
            entity_id=str(entry.id),
            details={"before": before_snapshot, "after": _public_audit_snapshot(entry)},
            **_request_audit_meta(self.request),
        )
        if previous_status != target_status:
            services.log_audit(
                user=self.request.user,
                action_type=models.ActionTypeChoices.STATUS_CHANGE,
                entity_type="public_application",
                entity_id=str(entry.id),
                details={"from": previous_status, "to": target_status},
                **_request_audit_meta(self.request),
            )
        return None, entry


class PublicMasterEntryCreateView(PublicMasterEntryBaseView):
    def get(self, request, *args, **kwargs):
        return self._render_form(form_data={"quantity": "1"})

    def post(self, request, *args, **kwargs):
        form_data = _build_public_form_data(request.POST)
        if request.POST.get("action") == "verify":
            if not (form_data["aadhar_number"].isdigit() and len(form_data["aadhar_number"]) == 12):
                return self._render_form(
                    form_data=form_data,
                    errors=["Aadhaar number must be a valid 12-digit number."],
                )
            history_matches = _public_history_matches(form_data["aadhar_number"])
            current_match = _public_current_match(form_data["aadhar_number"])
            warnings = ["This Aadhaar number exists in past beneficiary history."] if history_matches else []
            successes = ["Verification passed."] if not history_matches and not current_match else []
            if current_match:
                warnings.append("Duplicate found in current applications.")
            return self._render_form(
                form_data=form_data,
                history_matches=history_matches,
                current_match=current_match,
                warnings=warnings,
                successes=successes,
                allow_duplicate_save=bool(current_match),
            )

        response, saved_entry = self._save_entry(form_data=form_data)
        if response is not None:
            return response
        action = (request.POST.get("action") or "draft").strip().lower()
        if action == "submit":
            request.session["public_submit_popup"] = {"application_number": saved_entry.application_number, "name": saved_entry.name}
            messages.success(request, "Public application submitted.")
            return HttpResponseRedirect(reverse("ui:master-entry") + "?type=public")
        else:
            messages.success(request, "Public application saved as draft.")
            return HttpResponseRedirect(reverse("ui:master-entry-public-edit", kwargs={"pk": saved_entry.pk}))


class PublicMasterEntryUpdateView(PublicMasterEntryBaseView):
    def get(self, request, *args, **kwargs):
        entry = self.get_entry()
        if entry.status == models.BeneficiaryStatusChoices.SUBMITTED:
            messages.error(request, "This public application is submitted and locked. Reopen it first.")
            return HttpResponseRedirect(reverse("ui:master-entry") + "?type=public")
        return self._render_form(
            entry=entry,
            form_data={
                "aadhar_number": entry.aadhar_number,
                "name": entry.name,
                "is_handicapped": "true" if entry.is_handicapped and entry.is_handicapped != models.HandicappedStatusChoices.NO else "false",
                "disability_category": entry.is_handicapped if entry.is_handicapped and entry.is_handicapped != models.HandicappedStatusChoices.NO else "",
                "gender": entry.gender or "",
                "female_status": entry.female_status or "",
                "address": entry.address or "",
                "mobile": entry.mobile or "",
                "article_id": str(entry.article_id),
                "article_cost_per_unit": str(entry.article_cost_per_unit),
                "quantity": str(entry.quantity),
                "name_of_institution": entry.name_of_institution or "",
                "cheque_rtgs_in_favour": entry.cheque_rtgs_in_favour or "",
                "notes": entry.notes or "",
            },
            history_matches=_public_history_matches(entry.aadhar_number),
        )

    def post(self, request, *args, **kwargs):
        entry = self.get_entry()
        if entry.status == models.BeneficiaryStatusChoices.SUBMITTED:
            messages.error(request, "This public application is submitted and locked. Reopen it first.")
            return HttpResponseRedirect(reverse("ui:master-entry") + "?type=public")
        submitted_conflict_token = request.POST.get("_conflict_token", "")
        current_conflict_token = _public_conflict_token(entry)
        if submitted_conflict_token and current_conflict_token and submitted_conflict_token != current_conflict_token:
            messages.error(request, _conflict_message("public application"), extra_tags="persistent")
            return HttpResponseRedirect(reverse("ui:master-entry-public-edit", kwargs={"pk": entry.pk}))
        form_data = _build_public_form_data(request.POST)
        if request.POST.get("action") == "verify":
            if not (form_data["aadhar_number"].isdigit() and len(form_data["aadhar_number"]) == 12):
                return self._render_form(
                    entry=entry,
                    form_data=form_data,
                    errors=["Aadhaar number must be a valid 12-digit number."],
                )
            history_matches = _public_history_matches(form_data["aadhar_number"])
            current_match = _public_current_match(form_data["aadhar_number"], exclude_pk=entry.pk)
            warnings = ["This Aadhaar number exists in past beneficiary history."] if history_matches else []
            successes = ["Verification passed."] if not history_matches and not current_match else []
            if current_match:
                warnings.append("Duplicate found in current applications.")
            return self._render_form(
                entry=entry,
                form_data=form_data,
                history_matches=history_matches,
                current_match=current_match,
                warnings=warnings,
                successes=successes,
                allow_duplicate_save=bool(current_match),
            )

        response, saved_entry = self._save_entry(entry=entry, form_data=form_data)
        if response is not None:
            return response
        action = (request.POST.get("action") or "draft").strip().lower()
        if action == "submit":
            request.session["public_submit_popup"] = {"application_number": saved_entry.application_number, "name": saved_entry.name}
            messages.success(request, "Public application submitted.")
            return HttpResponseRedirect(reverse("ui:master-entry") + "?type=public")
        else:
            messages.success(request, "Public application saved as draft.")
            return HttpResponseRedirect(reverse("ui:master-entry-public-edit", kwargs={"pk": saved_entry.pk}))


class PublicMasterEntryDetailView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    module_key = models.ModuleKeyChoices.APPLICATION_ENTRY
    permission_action = "view"
    template_name = "dashboard/master_entry_public_detail.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        entry = models.PublicBeneficiaryEntry.objects.select_related("article").get(pk=self.kwargs["pk"])
        context["entry"] = entry
        context["history_matches"] = _public_history_matches(entry.aadhar_number)
        context.update(_public_attachment_context(entry))
        return context


class PublicMasterEntryDeleteView(LoginRequiredMixin, AdminRequiredMixin, View):
    module_key = models.ModuleKeyChoices.APPLICATION_ENTRY
    permission_action = "delete"
    def post(self, request, *args, **kwargs):
        entry = models.PublicBeneficiaryEntry.objects.get(pk=kwargs["pk"])
        snapshot = _public_audit_snapshot(entry)
        entry.delete()
        services.log_audit(
            user=request.user,
            action_type=models.ActionTypeChoices.DELETE,
            entity_type="public_application",
            entity_id=str(kwargs["pk"]),
            details={"before": snapshot},
            **_request_audit_meta(request),
        )
        messages.warning(request, "Public entry deleted.")
        return HttpResponseRedirect(reverse("ui:master-entry") + "?type=public")


class PublicMasterEntryReopenView(LoginRequiredMixin, AdminRequiredMixin, View):
    module_key = models.ModuleKeyChoices.APPLICATION_ENTRY
    permission_action = "reopen"
    def post(self, request, *args, **kwargs):
        entry = models.PublicBeneficiaryEntry.objects.get(pk=kwargs["pk"])
        previous_status = entry.status
        entry.status = models.BeneficiaryStatusChoices.DRAFT
        entry.save(update_fields=["status"])
        services.log_audit(
            user=request.user,
            action_type=models.ActionTypeChoices.STATUS_CHANGE,
            entity_type="public_application",
            entity_id=str(entry.id),
            details={"from": previous_status, "to": models.BeneficiaryStatusChoices.DRAFT},
            **_request_audit_meta(request),
        )
        messages.success(request, "Public application reopened as draft.")
        return HttpResponseRedirect(reverse("ui:master-entry") + "?type=public")


class InstitutionsMasterEntryBaseView(LoginRequiredMixin, WriteRoleMixin, TemplateView):
    module_key = models.ModuleKeyChoices.APPLICATION_ENTRY
    permission_action = "create_edit"
    template_name = "dashboard/master_entry_institution_form.html"

    def _render_form(self, *, form_data=None, rows=None, errors=None, application_number=None):
        context = self.get_context_data(
            **_institution_form_context(
                form_data=form_data,
                rows=rows,
                errors=errors,
                application_number=application_number,
            )
        )
        context.update(_institution_attachment_context(application_number))
        context["conflict_token"] = _institution_conflict_token(application_number)
        return self.render_to_response(context)

    def _save_group(self, *, application_number=None, form_data=None, raw_rows=None, replace=False):
        action = (self.request.POST.get("action") or "draft").strip().lower()
        require_complete = action == "submit"
        errors = []
        if require_complete and not form_data["institution_name"]:
            errors.append("Institution name is required.")
        if require_complete and not form_data["institution_type"]:
            errors.append("Institution type is required.")
        if require_complete and not form_data["address"]:
            errors.append("Address is required.")
        if require_complete and not form_data["mobile"]:
            errors.append("Mobile number is required.")
        elif form_data["mobile"]:
            mobile_numbers = [value.strip() for value in form_data["mobile"].split("&") if value.strip()]
            if mobile_numbers and any((not number.isdigit()) or len(number) != 10 for number in mobile_numbers):
                errors.append("Each mobile number must be exactly 10 digits.")

        built_rows, row_errors = _validate_institution_rows(
            raw_rows,
            require_complete=require_complete,
            internal_notes=form_data["internal_notes"],
        )
        errors.extend(row_errors)

        if errors:
            article_lookup = {str(article.id): article for article in models.Article.objects.filter(is_active=True)}
            hydrated_rows = []
            for row in raw_rows:
                article = article_lookup.get(row["article_id"])
                hydrated_rows.append(
                    {
                        "article_id": row["article_id"],
                        "quantity": row["quantity"],
                        "unit_cost": row["unit_cost"],
                        "notes": row["notes"],
                        "name_of_beneficiary": row.get("name_of_beneficiary", ""),
                        "name_of_institution": row.get("name_of_institution", ""),
                        "aadhar_number": row.get("aadhar_number", ""),
                        "cheque_rtgs_in_favour": row.get("cheque_rtgs_in_favour", ""),
                        "article_name": article.article_name if article else "",
                        "item_type": article.item_type if article else "",
                        "internal_notes": form_data["internal_notes"],
                    }
                )
            return self._render_form(
                form_data=form_data,
                rows=hydrated_rows,
                errors=errors,
                application_number=application_number,
            )

        source_application_number = application_number
        is_draft_placeholder = bool(application_number and application_number.startswith("DRAFT-INS-"))
        if action == "submit":
            if not application_number or is_draft_placeholder:
                application_number = services.next_institution_application_number()
        elif not application_number:
            application_number = f"DRAFT-INS-{uuid.uuid4().hex[:12].upper()}"
        target_status = models.BeneficiaryStatusChoices.SUBMITTED if action == "submit" else models.BeneficiaryStatusChoices.DRAFT
        for built in built_rows:
            built["status"] = target_status

        with transaction.atomic():
            if replace:
                lookup_application_number = source_application_number or application_number
                before_snapshot = _institution_audit_snapshot(lookup_application_number)
                existing_entries = list(
                    models.InstitutionsBeneficiaryEntry.objects.filter(application_number=lookup_application_number).select_related("article").order_by("id")
                )
                previous_status = existing_entries[0].status if existing_entries else None
                _sync_institution_entries(
                    existing_entries,
                    built_rows,
                    self.request.user,
                    application_number=application_number,
                    form_data=form_data,
                )
                if lookup_application_number != application_number:
                    models.ApplicationAttachment.objects.filter(
                        application_type=models.ApplicationAttachmentTypeChoices.INSTITUTION,
                        institution_application_number=lookup_application_number,
                    ).update(institution_application_number=application_number)
                services.log_audit(
                    user=self.request.user,
                    action_type=models.ActionTypeChoices.UPDATE,
                    entity_type="institution_application",
                    entity_id=application_number,
                    details={"before": before_snapshot, "after": _institution_audit_snapshot(application_number)},
                    **_request_audit_meta(self.request),
                )
                if previous_status != target_status:
                    services.log_audit(
                        user=self.request.user,
                        action_type=models.ActionTypeChoices.STATUS_CHANGE,
                        entity_type="institution_application",
                        entity_id=application_number,
                        details={"from": previous_status, "to": target_status},
                        **_request_audit_meta(self.request),
                    )
            else:
                for built in built_rows:
                    models.InstitutionsBeneficiaryEntry.objects.create(
                        created_by=self.request.user,
                        application_number=application_number,
                        institution_name=form_data["institution_name"],
                        institution_type=form_data["institution_type"],
                        address=form_data["address"] or None,
                        mobile=form_data["mobile"] or None,
                        **built,
                    )
                services.log_audit(
                    user=self.request.user,
                    action_type=models.ActionTypeChoices.CREATE,
                    entity_type="institution_application",
                    entity_id=application_number,
                    details={"after": _institution_audit_snapshot(application_number)},
                    **_request_audit_meta(self.request),
                )
                services.log_audit(
                    user=self.request.user,
                    action_type=models.ActionTypeChoices.STATUS_CHANGE,
                    entity_type="institution_application",
                    entity_id=application_number,
                    details={"from": None, "to": target_status},
                    **_request_audit_meta(self.request),
                )
        self._saved_institution_application_number = application_number
        return None


class InstitutionsMasterEntryCreateView(InstitutionsMasterEntryBaseView):
    def get(self, request, *args, **kwargs):
        return self._render_form()

    def post(self, request, *args, **kwargs):
        form_data = _build_institution_form_data(request.POST)
        rows = _parse_district_rows(request.POST)
        action = (request.POST.get("action") or "draft").strip().lower()
        response = self._save_group(form_data=form_data, raw_rows=rows)
        if response is not None:
            return response
        saved_application_number = getattr(self, "_saved_institution_application_number", None)
        if action == "submit":
            popup_entry = models.InstitutionsBeneficiaryEntry.objects.filter(application_number=saved_application_number).order_by("-updated_at").first()
            if popup_entry:
                request.session["institution_submit_popup"] = {
                    "application_number": popup_entry.application_number,
                    "name": popup_entry.institution_name,
                }
            messages.success(request, "Institution application submitted.")
            return HttpResponseRedirect(reverse("ui:master-entry") + "?type=institutions")
        else:
            messages.success(request, "Institution application saved as draft.")
            return HttpResponseRedirect(reverse("ui:master-entry-institution-edit", kwargs={"application_number": saved_application_number}))


class InstitutionsMasterEntryUpdateView(InstitutionsMasterEntryBaseView):
    def get(self, request, *args, **kwargs):
        application_number = kwargs["application_number"]
        entries = list(
            models.InstitutionsBeneficiaryEntry.objects.filter(application_number=application_number).select_related("article").order_by("id")
        )
        if entries and entries[0].status == models.BeneficiaryStatusChoices.SUBMITTED:
            messages.error(request, "This institution application is submitted and locked. Reopen it first.")
            return HttpResponseRedirect(reverse("ui:master-entry") + "?type=institutions")
        first = entries[0]
        rows = [
            {
                "article_id": str(entry.article_id),
                "quantity": entry.quantity,
                "unit_cost": entry.article_cost_per_unit,
                "notes": entry.notes or "",
                "name_of_beneficiary": entry.name_of_beneficiary or "",
                "name_of_institution": entry.name_of_institution or "",
                "aadhar_number": entry.aadhar_number or "",
                "cheque_rtgs_in_favour": entry.cheque_rtgs_in_favour or "",
                "article_name": entry.article.article_name,
                "item_type": entry.article.item_type,
                "status": entry.status,
                "internal_notes": entry.internal_notes or "",
            }
            for entry in entries
        ]
        form_data = {
            "institution_name": first.institution_name,
            "institution_type": first.institution_type,
            "address": first.address or "",
            "mobile": first.mobile or "",
            "internal_notes": first.internal_notes or "",
        }
        return self._render_form(form_data=form_data, rows=rows, application_number=application_number)

    def post(self, request, *args, **kwargs):
        application_number = kwargs["application_number"]
        existing_entries = list(models.InstitutionsBeneficiaryEntry.objects.filter(application_number=application_number).order_by("id"))
        if existing_entries and existing_entries[0].status == models.BeneficiaryStatusChoices.SUBMITTED:
            messages.error(request, "This institution application is submitted and locked. Reopen it first.")
            return HttpResponseRedirect(reverse("ui:master-entry") + "?type=institutions")
        submitted_conflict_token = request.POST.get("_conflict_token", "")
        current_conflict_token = _institution_conflict_token(application_number)
        if submitted_conflict_token and current_conflict_token and submitted_conflict_token != current_conflict_token:
            messages.error(request, _conflict_message("institution application"), extra_tags="persistent")
            return HttpResponseRedirect(reverse("ui:master-entry-institution-edit", kwargs={"application_number": application_number}))
        form_data = _build_institution_form_data(request.POST)
        rows = _parse_district_rows(request.POST)
        action = (request.POST.get("action") or "draft").strip().lower()
        response = self._save_group(application_number=application_number, form_data=form_data, raw_rows=rows, replace=True)
        if response is not None:
            return response
        saved_application_number = getattr(self, "_saved_institution_application_number", application_number)
        if action == "submit":
            popup_entry = models.InstitutionsBeneficiaryEntry.objects.filter(application_number=saved_application_number).order_by("-updated_at").first()
            if popup_entry:
                request.session["institution_submit_popup"] = {
                    "application_number": popup_entry.application_number,
                    "name": popup_entry.institution_name,
                }
            messages.success(request, "Institution application submitted.")
            return HttpResponseRedirect(reverse("ui:master-entry") + "?type=institutions")
        else:
            messages.success(request, "Institution application saved as draft.")
            return HttpResponseRedirect(reverse("ui:master-entry-institution-edit", kwargs={"application_number": saved_application_number}))


class InstitutionsMasterEntryDetailView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    module_key = models.ModuleKeyChoices.APPLICATION_ENTRY
    permission_action = "view"
    template_name = "dashboard/master_entry_institution_detail.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        application_number = self.kwargs["application_number"]
        entries = list(
            models.InstitutionsBeneficiaryEntry.objects.filter(application_number=application_number).select_related("article").order_by("id")
        )
        first = entries[0]
        context.update(
            {
                "application_number": application_number,
                "entry_header": first,
                "entries": entries,
                "total_quantity": sum((row.quantity or 0) for row in entries),
                "total_value": sum((row.total_amount or 0) for row in entries),
                "application_status": first.status,
            }
        )
        context.update(_institution_attachment_context(application_number))
        return context


class InstitutionsMasterEntryDeleteView(LoginRequiredMixin, AdminRequiredMixin, View):
    module_key = models.ModuleKeyChoices.APPLICATION_ENTRY
    permission_action = "delete"
    def post(self, request, *args, **kwargs):
        application_number = kwargs["application_number"]
        snapshot = _institution_audit_snapshot(application_number)
        models.InstitutionsBeneficiaryEntry.objects.filter(application_number=application_number).delete()
        services.log_audit(
            user=request.user,
            action_type=models.ActionTypeChoices.DELETE,
            entity_type="institution_application",
            entity_id=application_number,
            details={"before": snapshot},
            **_request_audit_meta(request),
        )
        messages.warning(request, "Institution entry deleted.")
        return HttpResponseRedirect(reverse("ui:master-entry") + "?type=institutions")


class InstitutionsMasterEntryReopenView(LoginRequiredMixin, AdminRequiredMixin, View):
    module_key = models.ModuleKeyChoices.APPLICATION_ENTRY
    permission_action = "reopen"
    def post(self, request, *args, **kwargs):
        application_number = kwargs["application_number"]
        models.InstitutionsBeneficiaryEntry.objects.filter(application_number=application_number).update(
            status=models.BeneficiaryStatusChoices.DRAFT
        )
        services.log_audit(
            user=request.user,
            action_type=models.ActionTypeChoices.STATUS_CHANGE,
            entity_type="institution_application",
            entity_id=application_number,
            details={"from": models.BeneficiaryStatusChoices.SUBMITTED, "to": models.BeneficiaryStatusChoices.DRAFT},
            **_request_audit_meta(request),
        )
        messages.success(request, "Institution application reopened as draft.")
        return HttpResponseRedirect(reverse("ui:master-entry") + "?type=institutions")


class ApplicationAttachmentDownloadView(LoginRequiredMixin, RoleRequiredMixin, View):
    module_key = models.ModuleKeyChoices.APPLICATION_ENTRY
    permission_action = "view"
    def get(self, request, *args, **kwargs):
        attachment = get_object_or_404(models.ApplicationAttachment.objects.select_related("uploaded_by"), pk=kwargs["attachment_id"])
        if not attachment.file:
            raise Http404("File not found.")
        stored_name = os.path.basename(attachment.file.name)
        if attachment.application_type == models.ApplicationAttachmentTypeChoices.DISTRICT and attachment.district_id:
            application_reference = attachment.district.application_number
        elif attachment.application_type == models.ApplicationAttachmentTypeChoices.PUBLIC and attachment.public_entry_id:
            application_reference = attachment.public_entry.application_number or f"PUBLIC-{attachment.public_entry_id}"
        elif attachment.application_type == models.ApplicationAttachmentTypeChoices.INSTITUTION:
            application_reference = attachment.institution_application_number
        else:
            application_reference = ""
        display_name = _prefixed_attachment_name(application_reference, stored_name, attachment.file_name or stored_name)
        as_attachment = (request.GET.get("download") or "").strip() == "1"
        content_type, _ = mimetypes.guess_type(stored_name)
        if as_attachment:
            display_root, display_ext = os.path.splitext(display_name)
            _, stored_ext = os.path.splitext(stored_name)
            download_name = display_name if display_ext else f"{display_name}{stored_ext}"
            return FileResponse(
                attachment.file.open("rb"),
                as_attachment=True,
                filename=download_name,
                content_type=content_type or "application/octet-stream",
            )
        response = FileResponse(
            attachment.file.open("rb"),
            as_attachment=False,
            content_type=content_type or "application/octet-stream",
        )
        response["Content-Disposition"] = "inline"
        return response


class DistrictApplicationAttachmentUploadView(LoginRequiredMixin, WriteRoleMixin, View):
    module_key = models.ModuleKeyChoices.APPLICATION_ENTRY
    permission_action = "create_edit"
    def post(self, request, *args, **kwargs):
        district = get_object_or_404(models.DistrictMaster, pk=kwargs["district_id"], is_active=True)
        form = ApplicationAttachmentUploadForm(request.POST, request.FILES)
        if not form.is_valid():
            messages.error(request, "; ".join(form.errors.get("file", []) + form.errors.get("file_name", [])) or "Choose a valid file before uploading.")
            return HttpResponseRedirect(reverse("ui:master-entry-district-edit", kwargs={"district_id": district.id}))

        attachments_qs = models.ApplicationAttachment.objects.filter(
            application_type=models.ApplicationAttachmentTypeChoices.DISTRICT,
            district=district,
        )
        existing_count = attachments_qs.count()
        if existing_count >= ApplicationAttachmentUploadForm.MAX_FILES_PER_APPLICATION:
            messages.error(request, f"Maximum {ApplicationAttachmentUploadForm.MAX_FILES_PER_APPLICATION} files are allowed for one application.")
            return HttpResponseRedirect(reverse("ui:master-entry-district-edit", kwargs={"district_id": district.id}))

        uploaded = form.cleaned_data["file"]
        display_name = _prefixed_attachment_name(district.application_number, uploaded.name, form.cleaned_data.get("file_name") or "")
        if _attachment_name_exists(attachments_qs, display_name):
            messages.error(request, "A file with this name already exists for this application. Please rename it before uploading.")
            return HttpResponseRedirect(reverse("ui:master-entry-district-edit", kwargs={"district_id": district.id}))
        models.ApplicationAttachment.objects.create(
            application_type=models.ApplicationAttachmentTypeChoices.DISTRICT,
            district=district,
            file=uploaded,
            file_name=display_name,
            uploaded_by=request.user,
        )
        messages.success(request, "Attachment uploaded.")
        return HttpResponseRedirect(reverse("ui:master-entry-district-edit", kwargs={"district_id": district.id}))


class DistrictApplicationAttachmentDeleteView(LoginRequiredMixin, WriteRoleMixin, View):
    module_key = models.ModuleKeyChoices.APPLICATION_ENTRY
    permission_action = "create_edit"
    def post(self, request, *args, **kwargs):
        district = get_object_or_404(models.DistrictMaster, pk=kwargs["district_id"], is_active=True)
        attachment = get_object_or_404(
            models.ApplicationAttachment,
            pk=kwargs["attachment_id"],
            application_type=models.ApplicationAttachmentTypeChoices.DISTRICT,
            district=district,
        )
        if attachment.file:
            attachment.file.delete(save=False)
        attachment.delete()
        messages.success(request, "Attachment removed.")
        return HttpResponseRedirect(reverse("ui:master-entry-district-edit", kwargs={"district_id": district.id}))


class PublicApplicationAttachmentUploadView(LoginRequiredMixin, WriteRoleMixin, View):
    module_key = models.ModuleKeyChoices.APPLICATION_ENTRY
    permission_action = "create_edit"
    def post(self, request, *args, **kwargs):
        entry = get_object_or_404(models.PublicBeneficiaryEntry, pk=kwargs["pk"])
        form = ApplicationAttachmentUploadForm(request.POST, request.FILES)
        if not form.is_valid():
            messages.error(request, "; ".join(form.errors.get("file", []) + form.errors.get("file_name", [])) or "Choose a valid file before uploading.")
            return HttpResponseRedirect(reverse("ui:master-entry-public-edit", kwargs={"pk": entry.pk}))

        attachments_qs = models.ApplicationAttachment.objects.filter(
            application_type=models.ApplicationAttachmentTypeChoices.PUBLIC,
            public_entry=entry,
        )
        existing_count = attachments_qs.count()
        if existing_count >= ApplicationAttachmentUploadForm.MAX_FILES_PER_APPLICATION:
            messages.error(request, f"Maximum {ApplicationAttachmentUploadForm.MAX_FILES_PER_APPLICATION} files are allowed for one application.")
            return HttpResponseRedirect(reverse("ui:master-entry-public-edit", kwargs={"pk": entry.pk}))

        uploaded = form.cleaned_data["file"]
        application_reference = entry.application_number or f"PUBLIC-{entry.pk}"
        display_name = _prefixed_attachment_name(application_reference, uploaded.name, form.cleaned_data.get("file_name") or "")
        if _attachment_name_exists(attachments_qs, display_name):
            messages.error(request, "A file with this name already exists for this application. Please rename it before uploading.")
            return HttpResponseRedirect(reverse("ui:master-entry-public-edit", kwargs={"pk": entry.pk}))
        models.ApplicationAttachment.objects.create(
            application_type=models.ApplicationAttachmentTypeChoices.PUBLIC,
            public_entry=entry,
            file=uploaded,
            file_name=display_name,
            uploaded_by=request.user,
        )
        messages.success(request, "Attachment uploaded.")
        return HttpResponseRedirect(reverse("ui:master-entry-public-edit", kwargs={"pk": entry.pk}))


class PublicApplicationAttachmentDeleteView(LoginRequiredMixin, WriteRoleMixin, View):
    module_key = models.ModuleKeyChoices.APPLICATION_ENTRY
    permission_action = "create_edit"
    def post(self, request, *args, **kwargs):
        entry = get_object_or_404(models.PublicBeneficiaryEntry, pk=kwargs["pk"])
        attachment = get_object_or_404(
            models.ApplicationAttachment,
            pk=kwargs["attachment_id"],
            application_type=models.ApplicationAttachmentTypeChoices.PUBLIC,
            public_entry=entry,
        )
        if attachment.file:
            attachment.file.delete(save=False)
        attachment.delete()
        messages.success(request, "Attachment removed.")
        return HttpResponseRedirect(reverse("ui:master-entry-public-edit", kwargs={"pk": entry.pk}))


class InstitutionApplicationAttachmentUploadView(LoginRequiredMixin, WriteRoleMixin, View):
    module_key = models.ModuleKeyChoices.APPLICATION_ENTRY
    permission_action = "create_edit"
    def post(self, request, *args, **kwargs):
        application_number = kwargs["application_number"]
        if not models.InstitutionsBeneficiaryEntry.objects.filter(application_number=application_number).exists():
            raise Http404("Institution application not found.")
        form = ApplicationAttachmentUploadForm(request.POST, request.FILES)
        if not form.is_valid():
            messages.error(request, "; ".join(form.errors.get("file", []) + form.errors.get("file_name", [])) or "Choose a valid file before uploading.")
            return HttpResponseRedirect(reverse("ui:master-entry-institution-edit", kwargs={"application_number": application_number}))

        attachments_qs = models.ApplicationAttachment.objects.filter(
            application_type=models.ApplicationAttachmentTypeChoices.INSTITUTION,
            institution_application_number=application_number,
        )
        existing_count = attachments_qs.count()
        if existing_count >= ApplicationAttachmentUploadForm.MAX_FILES_PER_APPLICATION:
            messages.error(request, f"Maximum {ApplicationAttachmentUploadForm.MAX_FILES_PER_APPLICATION} files are allowed for one application.")
            return HttpResponseRedirect(reverse("ui:master-entry-institution-edit", kwargs={"application_number": application_number}))

        uploaded = form.cleaned_data["file"]
        display_name = _prefixed_attachment_name(application_number, uploaded.name, form.cleaned_data.get("file_name") or "")
        if _attachment_name_exists(attachments_qs, display_name):
            messages.error(request, "A file with this name already exists for this application. Please rename it before uploading.")
            return HttpResponseRedirect(reverse("ui:master-entry-institution-edit", kwargs={"application_number": application_number}))
        models.ApplicationAttachment.objects.create(
            application_type=models.ApplicationAttachmentTypeChoices.INSTITUTION,
            institution_application_number=application_number,
            file=uploaded,
            file_name=display_name,
            uploaded_by=request.user,
        )
        messages.success(request, "Attachment uploaded.")
        return HttpResponseRedirect(reverse("ui:master-entry-institution-edit", kwargs={"application_number": application_number}))


class InstitutionApplicationAttachmentDeleteView(LoginRequiredMixin, WriteRoleMixin, View):
    module_key = models.ModuleKeyChoices.APPLICATION_ENTRY
    permission_action = "create_edit"
    def post(self, request, *args, **kwargs):
        application_number = kwargs["application_number"]
        attachment = get_object_or_404(
            models.ApplicationAttachment,
            pk=kwargs["attachment_id"],
            application_type=models.ApplicationAttachmentTypeChoices.INSTITUTION,
            institution_application_number=application_number,
        )
        if attachment.file:
            attachment.file.delete(save=False)
        attachment.delete()
        messages.success(request, "Attachment removed.")
        return HttpResponseRedirect(reverse("ui:master-entry-institution-edit", kwargs={"application_number": application_number}))


def _split_order_article_names(article: models.Article | None) -> tuple[list[str], bool]:
    if not article or not article.article_name:
        return [], False
    raw_name = article.article_name.strip()
    if not raw_name:
        return [], False
    has_plus = "+" in raw_name
    if has_plus:
        parts = [part.strip() for part in raw_name.split("+") if part.strip()]
    else:
        parts = [raw_name]
    return parts, bool(article.combo or has_plus)


def _ensure_order_summary_row(rows_map, order_name: str, article: models.Article | None, combo_related: bool):
    key = order_name.casefold()
    if key not in rows_map:
        rows_map[key] = {
            "row_key": key,
            "article_name": order_name,
            "item_type": article.item_type if article else "",
            "category": article.category if article else "",
            "master_category": article.master_category if article else "",
            "combo_related": combo_related,
            "total_quantity": 0,
            "quantity_ordered": 0,
            "quantity_received": 0,
            "quantity_pending": 0,
            "total_value": Decimal("0"),
            "breakdown": {"district": 0, "public": 0, "institutions": 0},
            "source_items": set(),
            "beneficiaries": [],
            "statuses": set(),
        }
    row = rows_map[key]
    if article:
        row["item_type"] = row["item_type"] or article.item_type
        row["category"] = row["category"] or (article.category or "")
        row["master_category"] = row["master_category"] or (article.master_category or "")
    row["combo_related"] = row["combo_related"] or combo_related
    return row


def _build_order_management_rows():
    rows_map = {}

    district_entries = (
        models.DistrictBeneficiaryEntry.objects.select_related("district", "article")
        .order_by("application_number", "district__district_name", "created_at")
    )
    for entry in district_entries:
        parts, combo_related = _split_order_article_names(entry.article)
        if not parts:
            continue
        split_count = Decimal(len(parts))
        value_share = (entry.total_amount or Decimal("0")) / split_count if split_count else Decimal("0")
        for part in parts:
            row = _ensure_order_summary_row(rows_map, part, entry.article, combo_related)
            row["total_quantity"] += entry.quantity
            row["total_value"] += value_share
            row["breakdown"]["district"] += entry.quantity
            row["source_items"].add(entry.article.article_name)
            row["statuses"].add(entry.status)
            row["beneficiaries"].append(
                {
                    "beneficiary_type": "District",
                    "application_number": entry.application_number or "",
                    "beneficiary_name": entry.district.district_name,
                    "quantity": entry.quantity,
                    "source_item": entry.article.article_name,
                    "notes": entry.notes or "",
                    "status": entry.status,
                    "item_type": entry.article.item_type,
                    "linked_fund_request_status": getattr(entry.fund_request, "status", "") if entry.fund_request_id else "",
                    "created_at": entry.created_at,
                }
            )

    public_entries = (
        models.PublicBeneficiaryEntry.objects.select_related("article")
        .order_by("application_number", "name", "created_at")
    )
    for entry in public_entries:
        parts, combo_related = _split_order_article_names(entry.article)
        if not parts:
            continue
        split_count = Decimal(len(parts))
        value_share = (entry.total_amount or Decimal("0")) / split_count if split_count else Decimal("0")
        for part in parts:
            row = _ensure_order_summary_row(rows_map, part, entry.article, combo_related)
            row["total_quantity"] += entry.quantity
            row["total_value"] += value_share
            row["breakdown"]["public"] += entry.quantity
            row["source_items"].add(entry.article.article_name)
            row["statuses"].add(entry.status)
            row["beneficiaries"].append(
                {
                    "beneficiary_type": "Public",
                    "application_number": entry.application_number or "",
                    "beneficiary_name": entry.name,
                    "quantity": entry.quantity,
                    "source_item": entry.article.article_name,
                    "notes": entry.notes or "",
                    "status": entry.status,
                    "item_type": entry.article.item_type,
                    "linked_fund_request_status": getattr(entry.fund_request, "status", "") if entry.fund_request_id else "",
                    "created_at": entry.created_at,
                }
            )

    institution_entries = (
        models.InstitutionsBeneficiaryEntry.objects.select_related("article")
        .order_by("application_number", "institution_name", "created_at")
    )
    for entry in institution_entries:
        parts, combo_related = _split_order_article_names(entry.article)
        if not parts:
            continue
        split_count = Decimal(len(parts))
        value_share = (entry.total_amount or Decimal("0")) / split_count if split_count else Decimal("0")
        for part in parts:
            row = _ensure_order_summary_row(rows_map, part, entry.article, combo_related)
            row["total_quantity"] += entry.quantity
            row["total_value"] += value_share
            row["breakdown"]["institutions"] += entry.quantity
            row["source_items"].add(entry.article.article_name)
            row["statuses"].add(entry.status)
            row["beneficiaries"].append(
                {
                    "beneficiary_type": "Institutions",
                    "application_number": entry.application_number or "",
                    "beneficiary_name": entry.institution_name,
                    "quantity": entry.quantity,
                    "source_item": entry.article.article_name,
                    "notes": entry.notes or "",
                    "status": entry.status,
                    "item_type": entry.article.item_type,
                    "linked_fund_request_status": getattr(entry.fund_request, "status", "") if entry.fund_request_id else "",
                    "created_at": entry.created_at,
                }
            )

    order_entries = (
        models.OrderEntry.objects.select_related("article")
        .exclude(status=models.OrderStatusChoices.CANCELLED)
        .order_by("article__article_name", "order_date", "created_at")
    )
    for entry in order_entries:
        parts, combo_related = _split_order_article_names(entry.article)
        if not parts:
            continue
        for part in parts:
            row = _ensure_order_summary_row(rows_map, part, entry.article, combo_related)
            if entry.status in {models.OrderStatusChoices.ORDERED, models.OrderStatusChoices.RECEIVED}:
                row["quantity_ordered"] += entry.quantity_ordered
            if entry.status == models.OrderStatusChoices.RECEIVED:
                row["quantity_received"] += entry.quantity_ordered

    rows = []
    for index, row in enumerate(sorted(rows_map.values(), key=lambda item: item["article_name"].casefold()), start=1):
        if models.BeneficiaryStatusChoices.SUBMITTED in row["statuses"]:
            row["source_status"] = models.BeneficiaryStatusChoices.SUBMITTED
        elif models.BeneficiaryStatusChoices.DRAFT in row["statuses"]:
            row["source_status"] = models.BeneficiaryStatusChoices.DRAFT
        else:
            row["source_status"] = ""
        quantity_gap = row["total_quantity"] - row["quantity_ordered"]
        row["quantity_pending"] = quantity_gap if quantity_gap > 0 else 0
        row["quantity_excess"] = abs(quantity_gap) if quantity_gap < 0 else 0
        row["source_items_display"] = ", ".join(sorted(row["source_items"]))
        row["beneficiaries"] = sorted(
            row["beneficiaries"],
            key=lambda item: (
                item["beneficiary_type"],
                item.get("created_at") or timezone.now(),
                item["application_number"],
                item["beneficiary_name"].casefold(),
                item["source_item"].casefold(),
            ),
        )
        allocation_status_priority = {
            models.BeneficiaryStatusChoices.SUBMITTED: 0,
            models.BeneficiaryStatusChoices.DRAFT: 1,
        }
        beneficiaries_for_allocation = sorted(
            row["beneficiaries"],
            key=lambda item: (
                allocation_status_priority.get(item.get("application_status") or item.get("status") or "", 99),
                item["beneficiary_type"],
                item.get("created_at") or timezone.now(),
                item["application_number"],
                item["beneficiary_name"].casefold(),
                item["source_item"].casefold(),
            ),
        )
        remaining_ordered = int(row["quantity_ordered"] or 0)
        for item in beneficiaries_for_allocation:
            quantity = int(item.get("quantity") or 0)
            source_status = item.get("status") or ""
            item["application_status"] = source_status or ""
            if item.get("item_type") == models.ItemTypeChoices.AID:
                linked_status = item.get("linked_fund_request_status") or ""
                item["ordered_quantity"] = quantity if linked_status == models.FundRequestStatusChoices.SUBMITTED else 0
                item["order_status"] = "Fund Raised" if item["ordered_quantity"] >= quantity and quantity > 0 else "No"
                continue
            if remaining_ordered <= 0:
                item["ordered_quantity"] = 0
                item["order_status"] = "No"
                continue
            if remaining_ordered >= quantity:
                item["ordered_quantity"] = quantity
                item["order_status"] = "Fund Raised"
                remaining_ordered -= quantity
            else:
                item["ordered_quantity"] = remaining_ordered
                item["order_status"] = "Partial"
                remaining_ordered = 0
        row["order_statuses"] = {item.get("order_status") or "" for item in row["beneficiaries"]}
        row["beneficiary_names_display"] = ", ".join(
            f'{item["beneficiary_type"]}: {item["beneficiary_name"]}' for item in row["beneficiaries"]
        )
        row["row_id"] = f"order-row-{index}"
        rows.append(row)
    return rows


def _order_management_metrics(rows):
    metrics = []
    for item_type in models.ItemTypeChoices:
        typed_rows = [row for row in rows if row["item_type"] == item_type.value]
        metrics.append(
            {
                "label": item_type.label,
                "count": len(typed_rows),
                "needed": sum(row["total_quantity"] for row in typed_rows),
                "ordered": sum(row["quantity_ordered"] for row in typed_rows),
                "pending": sum(row["quantity_pending"] for row in typed_rows),
                "excess": sum(row["quantity_excess"] for row in typed_rows),
            }
        )
    return metrics


def _partition_order_management_rows_by_application_status(rows, application_status_filter):
    if not application_status_filter:
        return rows

    status_priority = [
        models.BeneficiaryStatusChoices.SUBMITTED,
        models.BeneficiaryStatusChoices.DRAFT,
    ]

    partitioned_rows = []
    for row in rows:
        all_beneficiaries = row["beneficiaries"]
        beneficiaries = [
            item for item in all_beneficiaries
            if (item.get("application_status") or item.get("status") or "") == application_status_filter
        ]
        if not beneficiaries:
            continue

        filtered_row = dict(row)
        filtered_row["beneficiaries"] = beneficiaries
        filtered_row["breakdown"] = {"district": 0, "public": 0, "institutions": 0}
        filtered_row["total_quantity"] = 0
        filtered_row["quantity_ordered"] = 0
        filtered_row["quantity_pending"] = 0
        filtered_row["quantity_excess"] = 0
        filtered_row["statuses"] = {application_status_filter}
        filtered_row["source_status"] = application_status_filter
        filtered_row["order_statuses"] = {item.get("order_status") or "" for item in beneficiaries}

        quantities_by_status = {status: 0 for status in status_priority}
        for item in all_beneficiaries:
            item_status = (item.get("application_status") or item.get("status") or "").strip()
            if item_status in quantities_by_status:
                quantities_by_status[item_status] += int(item.get("quantity") or 0)

        filtered_total_quantity = sum(int(item.get("quantity") or 0) for item in beneficiaries)
        ordered_pool = int(row.get("quantity_ordered") or 0)

        if application_status_filter == models.BeneficiaryStatusChoices.SUBMITTED:
            ordered_for_filtered = min(ordered_pool, filtered_total_quantity)
        elif application_status_filter == models.BeneficiaryStatusChoices.DRAFT:
            ordered_after_submitted = max(
                ordered_pool - quantities_by_status.get(models.BeneficiaryStatusChoices.SUBMITTED, 0),
                0,
            )
            ordered_for_filtered = min(ordered_after_submitted, filtered_total_quantity)
        else:
            ordered_reserved_for_prior = 0
            for status in status_priority:
                if status == application_status_filter:
                    break
                ordered_reserved_for_prior += quantities_by_status.get(status, 0)
            ordered_for_filtered = min(max(ordered_pool - ordered_reserved_for_prior, 0), filtered_total_quantity)

        filtered_row["quantity_ordered"] = ordered_for_filtered
        filtered_row["quantity_pending"] = max(filtered_total_quantity - ordered_for_filtered, 0)

        for item in beneficiaries:
            quantity = int(item.get("quantity") or 0)
            filtered_row["total_quantity"] += quantity
            if item.get("beneficiary_type") == "District":
                filtered_row["breakdown"]["district"] += quantity
            elif item.get("beneficiary_type") == "Public":
                filtered_row["breakdown"]["public"] += quantity
            else:
                filtered_row["breakdown"]["institutions"] += quantity
        filtered_row["beneficiary_names_display"] = ", ".join(
            f'{item["beneficiary_type"]}: {item["beneficiary_name"]}' for item in beneficiaries
        )
        partitioned_rows.append(filtered_row)

    return partitioned_rows


def _partition_order_management_rows_by_order_status(rows, order_status_filter):
    if not order_status_filter:
        return rows

    partitioned_rows = []
    for row in rows:
        beneficiaries = [
            item for item in row["beneficiaries"]
            if (item.get("order_status") or "") == order_status_filter
        ]
        if not beneficiaries:
            continue

        filtered_row = dict(row)
        filtered_row["beneficiaries"] = beneficiaries
        filtered_row["breakdown"] = {"district": 0, "public": 0, "institutions": 0}
        filtered_row["total_quantity"] = 0
        filtered_row["quantity_ordered"] = 0
        filtered_row["quantity_pending"] = 0
        filtered_row["quantity_excess"] = 0
        filtered_row["order_statuses"] = {order_status_filter}

        statuses = {item.get("status") or "" for item in beneficiaries if item.get("status")}
        filtered_row["statuses"] = statuses
        if models.BeneficiaryStatusChoices.SUBMITTED in statuses:
            filtered_row["source_status"] = models.BeneficiaryStatusChoices.SUBMITTED
        elif models.BeneficiaryStatusChoices.DRAFT in statuses:
            filtered_row["source_status"] = models.BeneficiaryStatusChoices.DRAFT
        else:
            filtered_row["source_status"] = ""

        for item in beneficiaries:
            quantity = int(item.get("quantity") or 0)
            filtered_row["total_quantity"] += quantity
            if item.get("beneficiary_type") == "District":
                filtered_row["breakdown"]["district"] += quantity
            elif item.get("beneficiary_type") == "Public":
                filtered_row["breakdown"]["public"] += quantity
            else:
                filtered_row["breakdown"]["institutions"] += quantity

            ordered_quantity = int(item.get("ordered_quantity") or 0)
            if order_status_filter == "Fund Raised":
                filtered_row["quantity_ordered"] += ordered_quantity
            elif order_status_filter == "Partial":
                filtered_row["quantity_ordered"] += ordered_quantity
                filtered_row["quantity_pending"] += max(quantity - ordered_quantity, 0)
            else:
                filtered_row["quantity_pending"] += quantity

        filtered_row["beneficiary_names_display"] = ", ".join(
            f'{item["beneficiary_type"]}: {item["beneficiary_name"]}' for item in beneficiaries
        )
        partitioned_rows.append(filtered_row)

    return partitioned_rows


class OrderManagementView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    module_key = models.ModuleKeyChoices.INVENTORY_PLANNING
    permission_action = "view"
    template_name = "dashboard/order_management.html"

    def get(self, request, *args, **kwargs):
        if (request.GET.get("export") or "").strip().lower() == "csv":
            return self._export_csv()
        return super().get(request, *args, **kwargs)

    def _get_filtered_rows(self):
        rows = _build_order_management_rows()
        status_filter = self.request.GET.get("status")
        if status_filter is None:
            status_filter = ""
        status_filter = status_filter.strip()
        order_status_filter = (self.request.GET.get("order_status") or "").strip()
        combo_filter = (self.request.GET.get("combo") or "").strip()
        balance_filter = (self.request.GET.get("balance") or "").strip()
        q = (self.request.GET.get("q") or "").strip().casefold()
        item_type = (self.request.GET.get("item_type") or "").strip()
        rows = _partition_order_management_rows_by_application_status(rows, status_filter)
        rows = _partition_order_management_rows_by_order_status(rows, order_status_filter)
        if combo_filter == "combo":
            rows = [row for row in rows if row["combo_related"]]
        elif combo_filter == "separate":
            rows = [row for row in rows if not row["combo_related"]]
        if q:
            rows = [
                row for row in rows
                if q in row["article_name"].casefold()
                or q in row["source_items_display"].casefold()
                or q in row["beneficiary_names_display"].casefold()
                or any(
                    q in item["application_number"].casefold()
                    or q in item["beneficiary_name"].casefold()
                    for item in row["beneficiaries"]
                )
            ]
        if item_type:
            rows = [row for row in rows if row["item_type"] == item_type]
        if balance_filter == "pending":
            rows = [row for row in rows if row["quantity_pending"] > 0]
        elif balance_filter == "excess":
            rows = [row for row in rows if row["quantity_excess"] > 0]

        sort = (self.request.GET.get("sort") or "article_name").strip()
        direction = (self.request.GET.get("dir") or "asc").strip().lower()
        allowed_sorts = {
            "article_name": lambda row: row["article_name"].casefold(),
            "total_quantity": lambda row: row["total_quantity"],
            "quantity_ordered": lambda row: row["quantity_ordered"],
            "quantity_pending": lambda row: row["quantity_pending"],
            "district": lambda row: row["breakdown"]["district"],
            "public": lambda row: row["breakdown"]["public"],
            "institutions": lambda row: row["breakdown"]["institutions"],
        }
        sort_key = allowed_sorts.get(sort, allowed_sorts["article_name"])
        rows = sorted(rows, key=sort_key, reverse=(direction == "desc"))
        previous_combo_related = None
        for index, row in enumerate(rows):
            row["group_break_before"] = index > 0 and previous_combo_related != row["combo_related"]
            previous_combo_related = row["combo_related"]
        return rows

    def _query_string_without_page(self):
        params = self.request.GET.copy()
        return params.urlencode()

    def _query_string_without(self, *keys):
        params = self.request.GET.copy()
        for key in keys:
            if key in params:
                del params[key]
        return params.urlencode()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        all_rows = _build_order_management_rows()
        rows = self._get_filtered_rows()
        article_rows = [row for row in all_rows if row["item_type"] == models.ItemTypeChoices.ARTICLE]
        aid_rows = [row for row in all_rows if row["item_type"] == models.ItemTypeChoices.AID]
        project_rows = [row for row in all_rows if row["item_type"] == models.ItemTypeChoices.PROJECT]
        context.update(
            {
                "rows": rows,
                "metrics": _order_management_metrics(all_rows),
                "item_type_choices": models.ItemTypeChoices.choices,
                "status_choices": [
                    ("", "All"),
                    (models.BeneficiaryStatusChoices.DRAFT, "Draft"),
                    (models.BeneficiaryStatusChoices.SUBMITTED, "Submitted"),
                ],
                "combo_choices": [
                    ("", "All"),
                    ("separate", "Separate"),
                    ("combo", "Combo / Split"),
                ],
                "order_status_choices": [
                    ("", "All"),
                    ("Fund Raised", "Fund Raised"),
                    ("Partial", "Partial"),
                    ("No", "No"),
                ],
                "balance_choices": [
                    ("", "All"),
                    ("pending", "Pending"),
                    ("excess", "Excess"),
                ],
                "filters": {
                    "q": self.request.GET.get("q", ""),
                    "item_type": self.request.GET.get("item_type", ""),
                    "status": (self.request.GET.get("status") if self.request.GET.get("status") is not None else ""),
                    "order_status": self.request.GET.get("order_status", ""),
                    "combo": self.request.GET.get("combo", ""),
                    "balance": self.request.GET.get("balance", ""),
                },
                "current_sort": (self.request.GET.get("sort") or "article_name").strip(),
                "current_dir": (self.request.GET.get("dir") or "asc").strip().lower(),
                "query_string_without_page": self._query_string_without_page(),
                "query_string_without_sort": self._query_string_without("sort", "dir", "export"),
                "article_count": len(article_rows),
                "aid_count": len(aid_rows),
                "project_count": len(project_rows),
                "all_item_count": len(all_rows),
                "filtered_item_count": len(rows),
            }
        )
        return context

    def _export_csv(self):
        rows = self._get_filtered_rows()
        export_mode = (self.request.GET.get("export_mode") or "overview").strip().lower()
        if export_mode not in {"overview", "complete"}:
            export_mode = "overview"
        timestamp = timezone.localtime().strftime("%Y_%m_%d_%I_%M_%p")
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = f'attachment; filename="inventory-planning-{export_mode}_{timestamp}.csv"'
        writer = csv.writer(response)
        if export_mode == "complete":
            writer.writerow(
                [
                    "Order Item",
                    "Item Type",
                    "Combo / Separate",
                    "Application Status Filtered",
                    "Source Items",
                    "Total Quantity Needed",
                    "Quantity Ordered",
                    "Quantity Pending",
                    "Quantity Excess",
                    "District",
                    "Public",
                    "Institutions & Others",
                    "Beneficiary Type",
                    "Application Number",
                    "Beneficiary",
                    "Beneficiary Quantity",
                    "Application Status",
                    "Order Status",
                    "Source Item",
                    "Notes",
                ]
            )
            for row in rows:
                beneficiaries = row["beneficiaries"] or [None]
                for item in beneficiaries:
                    writer.writerow(
                        [
                            row["article_name"],
                            row["item_type"],
                            "Combo / Split" if row["combo_related"] else "Separate",
                            row.get("source_status", ""),
                            row["source_items_display"],
                            row["total_quantity"],
                            row["quantity_ordered"],
                            row["quantity_pending"],
                            row["quantity_excess"],
                            row["breakdown"]["district"],
                            row["breakdown"]["public"],
                            row["breakdown"]["institutions"],
                            item["beneficiary_type"] if item else "",
                            item["application_number"] if item else "",
                            item["beneficiary_name"] if item else "",
                            item["quantity"] if item else "",
                            (item["application_status"].title() if item and item.get("application_status") else ""),
                            item["order_status"] if item else "",
                            item["source_item"] if item else "",
                            item["notes"] if item else "",
                        ]
                    )
        else:
            writer.writerow(
                [
                    "Order Item",
                    "Item Type",
                    "Combo / Separate",
                    "Application Status Filtered",
                    "Source Items",
                    "Total Quantity Needed",
                    "Quantity Ordered",
                    "Quantity Pending",
                    "Quantity Excess",
                    "District",
                    "Public",
                    "Institutions & Others",
                ]
            )
            for row in rows:
                writer.writerow(
                    [
                        row["article_name"],
                        row["item_type"],
                        "Combo / Split" if row["combo_related"] else "Separate",
                        row.get("source_status", ""),
                        row["source_items_display"],
                        row["total_quantity"],
                        row["quantity_ordered"],
                        row["quantity_pending"],
                        row["quantity_excess"],
                        row["breakdown"]["district"],
                        row["breakdown"]["public"],
                        row["breakdown"]["institutions"],
                    ]
                )
        return response


def _is_editable_by_user(user, fr):
    if not user or not user.is_authenticated:
        return False
    if user.role not in {"admin", "editor"}:
        return False
    return fr.status == models.FundRequestStatusChoices.DRAFT


def _is_editable_purchase_order(user, purchase_order):
    if not user or not user.is_authenticated:
        return False
    if user.role not in {"admin", "editor"}:
        return False
    return purchase_order.status == models.FundRequestStatusChoices.DRAFT


FundRequestRecipientFormSet = inlineformset_factory(
    models.FundRequest,
    models.FundRequestRecipient,
    form=FundRequestRecipientForm,
    extra=0,
    can_delete=True,
)

FundRequestArticleFormSet = inlineformset_factory(
    models.FundRequest,
    models.FundRequestArticle,
    form=FundRequestArticleForm,
    extra=0,
    can_delete=True,
)

PurchaseOrderItemFormSet = inlineformset_factory(
    models.PurchaseOrder,
    models.PurchaseOrderItem,
    form=PurchaseOrderItemForm,
    extra=0,
    can_delete=True,
)


class FundRequestListView(LoginRequiredMixin, RoleRequiredMixin, ListView):
    module_key = models.ModuleKeyChoices.ORDER_FUND_REQUEST
    permission_action = "view"
    model = models.FundRequest
    template_name = "dashboard/fund_request_list.html"
    context_object_name = "fund_requests"
    paginate_by = 20

    def get(self, request, *args, **kwargs):
        if (request.GET.get("export") or "").strip().lower() in {"xlsx", "export"}:
            return self._export_xlsx()
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        queryset = (
            models.FundRequest.objects.select_related("created_by")
            .prefetch_related("recipients", "articles", "documents")
        )
        self._sort_key = (self.request.GET.get("sort") or "created_at").strip()
        self._sort_dir = (self.request.GET.get("dir") or "desc").strip().lower()
        if q := (self.request.GET.get("q") or "").strip():
            fund_request_number_q = Q(fund_request_number__icontains=q)
            parsed_request_number = models.parse_fund_request_sequence(q)
            if parsed_request_number is not None:
                alternate_terms = {
                    models.format_fund_request_number(f"FR-{parsed_request_number}"),
                    f"FR-{parsed_request_number}",
                    f"FR{parsed_request_number}",
                }
                for term in alternate_terms:
                    fund_request_number_q |= Q(fund_request_number__icontains=term)
            matching_ids = (
                models.FundRequest.objects.select_related("created_by")
                .annotate(
                    total_amount_text=Cast("total_amount", output_field=CharField()),
                    created_at_text=Cast("created_at", output_field=CharField()),
                    recipient_source_entry_id_text=Cast("recipients__source_entry_id", output_field=CharField()),
                    recipient_fund_requested_text=Cast("recipients__fund_requested", output_field=CharField()),
                    article_sl_no_text=Cast("articles__sl_no", output_field=CharField()),
                    article_quantity_text=Cast("articles__quantity", output_field=CharField()),
                    article_unit_price_text=Cast("articles__unit_price", output_field=CharField()),
                    article_price_including_gst_text=Cast("articles__price_including_gst", output_field=CharField()),
                    article_value_text=Cast("articles__value", output_field=CharField()),
                    article_cumulative_text=Cast("articles__cumulative", output_field=CharField()),
                    document_generated_at_text=Cast("documents__generated_at", output_field=CharField()),
                )
                .filter(
                    fund_request_number_q
                    | Q(fund_request_type__icontains=q)
                    | Q(status__icontains=q)
                    | Q(aid_type__icontains=q)
                    | Q(notes__icontains=q)
                    | Q(total_amount_text__icontains=q)
                    | Q(created_at_text__icontains=q)
                    | Q(gst_number__icontains=q)
                    | Q(supplier_name__icontains=q)
                    | Q(supplier_address__icontains=q)
                    | Q(supplier_city__icontains=q)
                    | Q(supplier_state__icontains=q)
                    | Q(supplier_pincode__icontains=q)
                    | Q(purchase_order_number__icontains=q)
                    | Q(created_by__email__icontains=q)
                    | Q(created_by__first_name__icontains=q)
                    | Q(created_by__last_name__icontains=q)
                    | Q(recipients__recipient_name__icontains=q)
                    | Q(recipients__name_of_beneficiary__icontains=q)
                    | Q(recipients__name_of_institution__icontains=q)
                    | Q(recipients__beneficiary_type__icontains=q)
                    | Q(recipients__beneficiary__icontains=q)
                    | Q(recipients__details__icontains=q)
                    | Q(recipients__address__icontains=q)
                    | Q(recipients__cheque_in_favour__icontains=q)
                    | Q(recipients__cheque_no__icontains=q)
                    | Q(recipients__notes__icontains=q)
                    | Q(recipients__district_name__icontains=q)
                    | Q(recipient_source_entry_id_text__icontains=q)
                    | Q(recipient_fund_requested_text__icontains=q)
                    | Q(recipients__aadhar_number__icontains=q)
                    | Q(articles__article_name__icontains=q)
                    | Q(articles__beneficiary__icontains=q)
                    | Q(articles__vendor_name__icontains=q)
                    | Q(articles__gst_no__icontains=q)
                    | Q(articles__vendor_address__icontains=q)
                    | Q(articles__vendor_city__icontains=q)
                    | Q(articles__vendor_state__icontains=q)
                    | Q(articles__vendor_pincode__icontains=q)
                    | Q(articles__cheque_in_favour__icontains=q)
                    | Q(articles__cheque_no__icontains=q)
                    | Q(articles__supplier_article_name__icontains=q)
                    | Q(articles__description__icontains=q)
                    | Q(article_sl_no_text__icontains=q)
                    | Q(article_quantity_text__icontains=q)
                    | Q(article_unit_price_text__icontains=q)
                    | Q(article_price_including_gst_text__icontains=q)
                    | Q(article_value_text__icontains=q)
                    | Q(article_cumulative_text__icontains=q)
                    | Q(documents__file_name__icontains=q)
                    | Q(documents__file_path__icontains=q)
                    | Q(documents__document_type__icontains=q)
                    | Q(document_generated_at_text__icontains=q)
                    | Q(documents__generated_by__email__icontains=q)
                    | Q(documents__generated_by__first_name__icontains=q)
                    | Q(documents__generated_by__last_name__icontains=q)
                )
                .values_list("pk", flat=True)
                .distinct()
            )
            queryset = queryset.filter(pk__in=matching_ids)
        if request_type := (self.request.GET.get("request_type") or "").strip():
            queryset = queryset.filter(fund_request_type=request_type)
        if status := (self.request.GET.get("status") or "").strip():
            queryset = queryset.filter(status=status)
        if supplier := (self.request.GET.get("supplier") or "").strip():
            queryset = queryset.filter(supplier_name__icontains=supplier)
        sort_fields = {
            "fund_request_number": "fund_request_number",
            "fund_request_type": "fund_request_type",
            "item_type": "aid_type",
            "total_amount": "total_amount",
            "status": "status",
            "created_at": "created_at",
            "supplier_name": "supplier_name",
        }
        sort_field = sort_fields.get(self._sort_key, "created_at")
        sort_prefix = "" if self._sort_dir == "asc" else "-"
        if sort_field == "fund_request_number":
            queryset = queryset.order_by(f"{sort_prefix}created_at", f"{sort_prefix}id")
            queryset = sorted(
                queryset,
                key=lambda fr: (
                    models.parse_fund_request_sequence(fr.fund_request_number) is None,
                    models.parse_fund_request_sequence(fr.fund_request_number) or 0,
                    fr.created_at,
                    fr.id,
                ),
                reverse=(self._sort_dir == "desc"),
            )
            return queryset
        queryset = queryset.order_by(f"{sort_prefix}{sort_field}", "-id")
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        def clean_option_name(raw_value: str) -> str:
            text = str(raw_value or "").strip()
            if not text:
                return "-"
            parts = [part.strip() for part in text.split(" - ") if part.strip()]
            if len(parts) >= 2:
                return parts[1]
            return parts[0] if parts else text

        def beneficiary_option_display(recipient) -> str:
            raw_value = str(recipient.beneficiary or "").strip()
            if raw_value and " - " in raw_value:
                return raw_value
            source_entry_id = getattr(recipient, "source_entry_id", None)
            beneficiary_type = getattr(recipient, "beneficiary_type", None)
            if source_entry_id and beneficiary_type:
                source_entry = None
                if beneficiary_type == models.RecipientTypeChoices.DISTRICT:
                    source_entry = models.DistrictBeneficiaryEntry.objects.select_related("district").filter(pk=source_entry_id).first()
                elif beneficiary_type == models.RecipientTypeChoices.PUBLIC:
                    source_entry = models.PublicBeneficiaryEntry.objects.filter(pk=source_entry_id).first()
                elif beneficiary_type in {
                    models.RecipientTypeChoices.INSTITUTIONS,
                    models.RecipientTypeChoices.OTHERS,
                }:
                    source_entry = models.InstitutionsBeneficiaryEntry.objects.filter(pk=source_entry_id).first()
                if source_entry:
                    payload = _build_aid_option_payload(source_entry, beneficiary_type)
                    display_text = str(payload.get("display_text") or "").strip()
                    if display_text:
                        return display_text
            if raw_value and not raw_value.isdigit():
                return raw_value
            return (
                getattr(recipient, "display_name", "")
                or getattr(recipient, "recipient_name", "")
                or "-"
            )

        for fr in context["fund_requests"]:
            recipients = list(fr.recipients.all())
            articles = list(fr.articles.all())
            for recipient in recipients:
                recipient.display_name = (
                    recipient.name_of_beneficiary
                    or recipient.name_of_institution
                    or recipient.district_name
                    or clean_option_name(recipient.beneficiary)
                    or clean_option_name(recipient.recipient_name)
                )
                recipient.beneficiary_display = beneficiary_option_display(recipient)
            fr.district_recipient_count = sum(
                1 for recipient in recipients if recipient.beneficiary_type == models.RecipientTypeChoices.DISTRICT
            )
            fr.public_recipient_count = sum(
                1 for recipient in recipients if recipient.beneficiary_type == models.RecipientTypeChoices.PUBLIC
            )
            fr.institutions_recipient_count = sum(
                1 for recipient in recipients if recipient.beneficiary_type == models.RecipientTypeChoices.INSTITUTIONS
            )
            fr.others_recipient_count = sum(
                1 for recipient in recipients if recipient.beneficiary_type == models.RecipientTypeChoices.OTHERS
            )
            fr.article_total_quantity = sum(int(article.quantity or 0) for article in articles)
        current_sort = getattr(self, "_sort_key", "created_at")
        current_dir = getattr(self, "_sort_dir", "desc")
        def build_sort_params(column):
            params = self.request.GET.copy()
            params.pop("page", None)
            next_dir = "asc"
            if current_sort == column and current_dir == "asc":
                next_dir = "desc"
            params["sort"] = column
            params["dir"] = next_dir
            return params.urlencode()
        context["request_type_choices"] = models.FundRequestTypeChoices.choices
        context["status_choices"] = models.FundRequestStatusChoices.choices
        context["filters"] = {
            "q": self.request.GET.get("q", ""),
            "request_type": self.request.GET.get("request_type", ""),
            "status": self.request.GET.get("status", ""),
            "supplier": self.request.GET.get("supplier", ""),
        }
        context["current_sort"] = current_sort
        context["current_dir"] = current_dir
        context["sort_querystrings"] = {
            "fund_request_number": build_sort_params("fund_request_number"),
            "fund_request_type": build_sort_params("fund_request_type"),
            "item_type": build_sort_params("item_type"),
            "total_amount": build_sort_params("total_amount"),
            "status": build_sort_params("status"),
            "created_at": build_sort_params("created_at"),
        }
        return context

    def _event_birthday_number(self, event_year: int) -> int:
        return max(event_year - 1940, 1)

    def _beneficiary_display_for_export(self, recipient, fund_request_type):
        if fund_request_type == models.FundRequestTypeChoices.ARTICLE:
            return "All Districts & Public"
        if not recipient:
            return ""
        if recipient.beneficiary_type == models.RecipientTypeChoices.DISTRICT:
            if recipient.district_name:
                return recipient.district_name
            text = str(recipient.beneficiary or "").strip()
            parts = [part.strip() for part in text.split(" - ") if part.strip()]
            return parts[1] if len(parts) >= 2 else text
        if recipient.beneficiary_type in {
            models.RecipientTypeChoices.PUBLIC,
            models.RecipientTypeChoices.INSTITUTIONS,
            models.RecipientTypeChoices.OTHERS,
        }:
            text = str(recipient.beneficiary or "").strip()
            parts = [part.strip() for part in text.split(" - ") if part.strip()]
            return parts[0] if parts else text
        return str(recipient.beneficiary or "").strip()

    def _export_xlsx(self):
        export_status = (self.request.GET.get("export_status") or "").strip().lower()
        queryset = list(
            models.FundRequest.objects.select_related("created_by")
            .prefetch_related("recipients", "articles")
            .order_by("fund_request_number", "created_at", "id")
        )
        if q := (self.request.GET.get("q") or "").strip():
            queryset = [
                fr for fr in queryset
                if q.lower() in str(fr.fund_request_number or "").lower()
                or q.lower() in str(fr.formatted_fund_request_number or "").lower()
                or q.lower() in str(fr.aid_type or "").lower()
                or q.lower() in str(fr.supplier_name or "").lower()
            ]
        if request_type := (self.request.GET.get("request_type") or "").strip():
            queryset = [fr for fr in queryset if fr.fund_request_type == request_type]
        if export_status in {
            models.FundRequestStatusChoices.DRAFT,
            models.FundRequestStatusChoices.SUBMITTED,
        }:
            queryset = [fr for fr in queryset if fr.status == export_status]

        def _fr_sort_key(fr):
            sequence = models.parse_fund_request_sequence(fr.fund_request_number)
            if sequence is not None:
                return (0, sequence)
            raw = str(fr.fund_request_number or "").strip()
            return (1, raw)

        queryset.sort(key=_fr_sort_key)

        workbook = Workbook()
        worksheet = workbook.active
        worksheet.title = "Fund Requests"

        thin = Side(style="thin")
        border = Border(top=thin, left=thin, right=thin, bottom=thin)
        header_fill = PatternFill("solid", fgColor="E0E0E0")
        total_fill = PatternFill("solid", fgColor="D3D3D3")
        center = Alignment(horizontal="center", vertical="center", wrap_text=True)
        left = Alignment(horizontal="left", vertical="center", wrap_text=True)
        right = Alignment(horizontal="right", vertical="center")

        event_year = timezone.localdate().year
        birthday_number = self._event_birthday_number(event_year)

        current_row = 1
        worksheet.merge_cells(start_row=current_row, start_column=1, end_row=current_row, end_column=13)
        cell = worksheet.cell(current_row, 1)
        cell.value = "OMSAKTHI"
        cell.font = Font(size=10, bold=True)
        cell.alignment = center
        current_row += 1

        worksheet.merge_cells(start_row=current_row, start_column=1, end_row=current_row, end_column=13)
        cell = worksheet.cell(current_row, 1)
        cell.value = (
            f"MASM Makkal Nala Pani Payment Request Details for Distribution on the eve of "
            f"{birthday_number}th Birthday Celebrations of"
        )
        cell.font = Font(size=12, bold=True)
        cell.alignment = center
        current_row += 1

        worksheet.merge_cells(start_row=current_row, start_column=1, end_row=current_row, end_column=13)
        cell = worksheet.cell(current_row, 1)
        cell.value = f"His Holiness AMMA at Melmaruvathur on 03.03.{event_year}"
        cell.font = Font(size=12, bold=True)
        cell.alignment = center
        current_row += 2

        worksheet.merge_cells(start_row=current_row, start_column=1, end_row=current_row, end_column=13)
        cell = worksheet.cell(current_row, 1)
        label = "Payment Request - MASTER LIST"
        if export_status == models.FundRequestStatusChoices.DRAFT:
            label = "Payment Request - DRAFT MASTER LIST"
        elif export_status == models.FundRequestStatusChoices.SUBMITTED:
            label = "Payment Request - SUBMITTED MASTER LIST"
        cell.value = label
        cell.font = Font(size=14, bold=True)
        cell.alignment = center
        current_row += 2

        headers = [
            "FUND REQ NO.",
            "Request Type",
            "Beneficiary",
            "Name of Beneficiary/Article",
            "Name of Institution/Article",
            "GST/Aadhar Number",
            "Details",
            "Units",
            "Price incl GST",
            "Value",
            "Fund Request Value",
            "CHEQUE (OR) RTGS IN FAVOUR",
            "CHEQUE NO.",
        ]
        for idx, header in enumerate(headers, start=1):
            cell = worksheet.cell(current_row, idx)
            cell.value = header
            cell.font = Font(size=11, bold=True)
            cell.fill = header_fill
            cell.alignment = center
            cell.border = border
        current_row += 1

        all_rows = []
        fr_value_map = {}
        for fr in queryset:
            if fr.fund_request_type == models.FundRequestTypeChoices.AID:
                fr_total = Decimal("0")
                for recipient in fr.recipients.all():
                    amount = Decimal(str(recipient.fund_requested or 0))
                    fr_total += amount
                    all_rows.append(
                        {
                            "fr_id": fr.id,
                            "fund_request_number": fr.formatted_fund_request_number or "",
                            "request_type": fr.aid_type or "Aid",
                            "beneficiary": self._beneficiary_display_for_export(recipient, fr.fund_request_type),
                            "name_beneficiary_article": recipient.recipient_name or recipient.name_of_beneficiary or "",
                            "name_institution_article": recipient.name_of_institution or "",
                            "gst_aadhar": recipient.aadhar_number or "",
                            "details": recipient.notes or recipient.details or "",
                            "units": 1,
                            "price_incl_gst": float(amount),
                            "value": float(amount),
                            "fund_request_value": 0,
                            "cheque_in_favour": recipient.cheque_in_favour or "",
                            "cheque_no": recipient.cheque_no or "",
                        }
                    )
                fr_value_map[fr.id] = float(fr_total)
            else:
                fr_total = Decimal("0")
                first_recipient = fr.recipients.all().first()
                beneficiary = self._beneficiary_display_for_export(first_recipient, fr.fund_request_type)
                for article in fr.articles.all():
                    line_value = Decimal(str(article.value or 0))
                    fr_total += line_value
                    all_rows.append(
                        {
                            "fr_id": fr.id,
                            "fund_request_number": fr.formatted_fund_request_number or "",
                            "request_type": "Article",
                            "beneficiary": beneficiary,
                            "name_beneficiary_article": article.supplier_article_name or article.article_name or "",
                            "name_institution_article": article.article_name or "",
                            "gst_aadhar": article.gst_no or fr.gst_number or "",
                            "details": "",
                            "units": article.quantity or 0,
                            "price_incl_gst": float(article.price_including_gst or article.unit_price or 0),
                            "value": float(line_value),
                            "fund_request_value": 0,
                            "cheque_in_favour": article.cheque_in_favour or "",
                            "cheque_no": article.cheque_no or "",
                        }
                    )
                fr_value_map[fr.id] = float(fr_total)

        for row in all_rows:
            row["fund_request_value"] = fr_value_map.get(row["fr_id"], 0)

        fr_groups = {}
        current_fr_id = None
        group_start = current_row
        for row in all_rows:
            if row["fr_id"] != current_fr_id:
                if current_fr_id is not None:
                    fr_groups[current_fr_id] = (group_start, current_row - 1)
                current_fr_id = row["fr_id"]
                group_start = current_row

            values = [
                row["fund_request_number"],
                row["request_type"],
                row["beneficiary"],
                row["name_beneficiary_article"],
                row["name_institution_article"],
                row["gst_aadhar"],
                row["details"],
                row["units"],
                row["price_incl_gst"],
                row["value"],
                row["fund_request_value"],
                row["cheque_in_favour"],
                row["cheque_no"],
            ]
            for idx, value in enumerate(values, start=1):
                cell = worksheet.cell(current_row, idx)
                cell.value = value
                cell.border = border
                cell.alignment = right if idx in {8, 9, 10, 11} else left
            current_row += 1
        if current_fr_id is not None:
            fr_groups[current_fr_id] = (group_start, current_row - 1)

        for _fr_id, (start_row, end_row) in fr_groups.items():
            if end_row > start_row:
                worksheet.merge_cells(start_row=start_row, start_column=11, end_row=end_row, end_column=11)
                worksheet.cell(start_row, 11).alignment = right

        grand_total = sum(fr_value_map.values())
        total_row = current_row
        for col in range(1, 14):
            cell = worksheet.cell(total_row, col)
            cell.fill = total_fill
            cell.border = border
        worksheet.cell(total_row, 1).value = "TOTAL"
        worksheet.cell(total_row, 1).font = Font(size=11, bold=True)
        worksheet.cell(total_row, 1).alignment = left
        worksheet.cell(total_row, 11).value = grand_total
        worksheet.cell(total_row, 11).font = Font(size=11, bold=True)
        worksheet.cell(total_row, 11).alignment = right

        widths = {
            1: 18, 2: 18, 3: 20, 4: 25, 5: 25, 6: 18, 7: 30,
            8: 12, 9: 15, 10: 15, 11: 18, 12: 25, 13: 15,
        }
        for column_index, width in widths.items():
            worksheet.column_dimensions[get_column_letter(column_index)].width = width

        stream = io.BytesIO()
        workbook.save(stream)
        stream.seek(0)
        date_stamp = timezone.localtime().strftime("%Y-%m-%d")
        suffix = export_status or "all"
        if export_status == models.FundRequestStatusChoices.SUBMITTED:
            filename = f"Fund_Request_Sub_{date_stamp}.xlsx"
        elif export_status == models.FundRequestStatusChoices.DRAFT:
            filename = f"Fund_Request_dft_{date_stamp}.xlsx"
        else:
            filename = f"Fund_Request_{suffix}_{date_stamp}.xlsx"
        response = HttpResponse(
            stream.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response



def _fund_request_aid_type_choices():
    names = set()
    names.update(
        filter(
            None,
            models.DistrictBeneficiaryEntry.objects.filter(article__item_type=models.ItemTypeChoices.AID).values_list('article__article_name', flat=True),
        )
    )
    names.update(
        filter(
            None,
            models.PublicBeneficiaryEntry.objects.filter(article__item_type=models.ItemTypeChoices.AID).values_list('article__article_name', flat=True),
        )
    )
    names.update(
        filter(
            None,
            models.InstitutionsBeneficiaryEntry.objects.filter(article__item_type=models.ItemTypeChoices.AID).values_list('article__article_name', flat=True),
        )
    )
    return sorted(names)


def _fund_request_article_choices(current_fund_request=None):
    rows = [
        row
        for row in _build_order_management_rows()
        if row['item_type'] == models.ItemTypeChoices.ARTICLE and row['quantity_pending'] > 0
    ]
    if current_fund_request and current_fund_request.status == models.FundRequestStatusChoices.SUBMITTED:
        current_quantities = {}
        for line in current_fund_request.articles.all():
            article_name = (line.article_name or getattr(line.article, "article_name", "") or "").strip()
            if not article_name:
                continue
            current_quantities[article_name.casefold()] = current_quantities.get(article_name.casefold(), 0) + int(line.quantity or 0)
        for row in rows:
            row['quantity_pending'] += current_quantities.get(row['article_name'].casefold(), 0)
    article_map = {
        article.article_name.casefold(): article
        for article in models.Article.objects.filter(item_type=models.ItemTypeChoices.ARTICLE)
    }
    choices = []
    for row in rows:
        article = article_map.get(row['article_name'].casefold())
        choices.append(
            {
                'name': row['article_name'],
                'label': f"{row['article_name']} (Pending: {row['quantity_pending']})",
                'article_id': article.id if article else '',
                'default_price': str(article.cost_per_unit if article else 0),
                'pending_qty': int(row['quantity_pending'] or 0),
            }
        )
    return choices


def _aid_entry_queryset(aid_type, beneficiary_type):
    filters = {
        'article__item_type': models.ItemTypeChoices.AID,
        'article__article_name__iexact': aid_type,
    }
    if beneficiary_type == models.RecipientTypeChoices.DISTRICT:
        return models.DistrictBeneficiaryEntry.objects.select_related('district', 'article', 'fund_request').filter(**filters)
    if beneficiary_type == models.RecipientTypeChoices.PUBLIC:
        return models.PublicBeneficiaryEntry.objects.select_related('article', 'fund_request').filter(**filters)
    return models.InstitutionsBeneficiaryEntry.objects.select_related('article', 'fund_request').filter(**filters)


def _build_aid_option_payload(entry, beneficiary_type):
    amount = float(entry.total_amount or 0)
    amount_display = format(amount, ".2f").rstrip("0").rstrip(".")
    details_display = (entry.notes or "").strip() or "-"
    if beneficiary_type == models.RecipientTypeChoices.DISTRICT:
        beneficiary_name = entry.district.district_name
        return {
            'source_entry_id': entry.pk,
            'application_number': entry.application_number or '',
            'display_text': f"{entry.application_number or ''} - {beneficiary_name} - Rs.{amount_display} - {details_display}",
            'recipient_name': beneficiary_name,
            'name_of_beneficiary': entry.name_of_beneficiary or '',
            'name_of_institution': entry.name_of_institution or '',
            'details': entry.notes or '',
            'fund_requested': amount,
            'aadhar_number': entry.aadhar_number or '',
            'cheque_in_favour': entry.cheque_rtgs_in_favour or '',
            'district_name': beneficiary_name,
            'source_item': entry.article.article_name,
        }
    if beneficiary_type == models.RecipientTypeChoices.PUBLIC:
        beneficiary_name = entry.name
        return {
            'source_entry_id': entry.pk,
            'application_number': entry.application_number or '',
            'display_text': f"{entry.application_number or ''} - {beneficiary_name} - Rs.{amount_display} - {details_display}",
            'recipient_name': beneficiary_name,
            'name_of_beneficiary': beneficiary_name,
            'name_of_institution': entry.name_of_institution or '',
            'details': entry.notes or '',
            'fund_requested': amount,
            'aadhar_number': entry.aadhar_number or '',
            'cheque_in_favour': entry.cheque_rtgs_in_favour or '',
            'district_name': '',
            'source_item': entry.article.article_name,
        }
    beneficiary_name = entry.institution_name
    return {
        'source_entry_id': entry.pk,
        'application_number': entry.application_number or '',
        'display_text': f"{entry.application_number or ''} - {beneficiary_name} - Rs.{amount_display} - {details_display}",
        'recipient_name': beneficiary_name,
        'name_of_beneficiary': entry.name_of_beneficiary or '',
        'name_of_institution': entry.name_of_institution or beneficiary_name,
        'details': entry.notes or '',
        'fund_requested': amount,
        'aadhar_number': entry.aadhar_number or '',
        'cheque_in_favour': entry.cheque_rtgs_in_favour or '',
        'district_name': '',
        'source_item': entry.article.article_name,
    }


def _get_aid_beneficiary_options(aid_type, beneficiary_type, current_fund_request=None):
    aid_type = (aid_type or '').strip()
    blocked = set()
    options = []
    if not aid_type or beneficiary_type not in {
        models.RecipientTypeChoices.DISTRICT,
        models.RecipientTypeChoices.PUBLIC,
        models.RecipientTypeChoices.INSTITUTIONS,
    }:
        return options, []

    for entry in _aid_entry_queryset(aid_type, beneficiary_type).order_by('application_number', 'created_at'):
        if entry.fund_request_id and (not current_fund_request or entry.fund_request_id != current_fund_request.id):
            label = entry.fund_request.formatted_fund_request_number if entry.fund_request and entry.fund_request.fund_request_number else f'Draft #{entry.fund_request_id}'
            if entry.fund_request:
                blocked.add(f"{label} ({entry.fund_request.get_status_display()})")
            else:
                blocked.add(label)
            continue
        options.append(_build_aid_option_payload(entry, beneficiary_type))
    return options, sorted(blocked)


def _get_aid_available_beneficiary_type_choices(aid_type, current_fund_request=None):
    results = []
    for value, label in [
        (models.RecipientTypeChoices.DISTRICT, 'District'),
        (models.RecipientTypeChoices.PUBLIC, 'Public'),
        (models.RecipientTypeChoices.INSTITUTIONS, 'Institutions'),
    ]:
        options, _blocked = _get_aid_beneficiary_options(aid_type, value, current_fund_request=current_fund_request)
        if options:
            results.append({'value': value, 'label': label, 'count': len(options)})
    return results


class FundRequestAidOptionsView(LoginRequiredMixin, RoleRequiredMixin, View):
    module_key = models.ModuleKeyChoices.ORDER_FUND_REQUEST
    permission_action = 'create_edit'

    def get(self, request, *args, **kwargs):
        aid_type = request.GET.get('aid_type') or ''
        beneficiary_type = request.GET.get('beneficiary_type') or ''
        current_id = request.GET.get('fund_request_id') or ''
        current_fund_request = None
        if current_id:
            current_fund_request = models.FundRequest.objects.filter(pk=current_id).first()
        options_by_type = {}
        blocked_by_type = {}
        for type_key in [
            models.RecipientTypeChoices.DISTRICT,
            models.RecipientTypeChoices.PUBLIC,
            models.RecipientTypeChoices.INSTITUTIONS,
        ]:
            type_options, type_blocked = _get_aid_beneficiary_options(aid_type, type_key, current_fund_request=current_fund_request)
            options_by_type[str(type_key)] = type_options
            blocked_by_type[str(type_key)] = type_blocked
        payload = {
            'available_types': _get_aid_available_beneficiary_type_choices(aid_type, current_fund_request=current_fund_request),
            'options': options_by_type.get(str(beneficiary_type), []) if beneficiary_type else [],
            'blocked': blocked_by_type.get(str(beneficiary_type), []) if beneficiary_type else [],
            'options_by_type': options_by_type,
            'blocked_by_type': blocked_by_type,
        }
        return JsonResponse(payload)


class FundRequestCreateUpdateMixin(WriteRoleMixin):
    module_key = models.ModuleKeyChoices.ORDER_FUND_REQUEST
    permission_action = 'create_edit'
    form_class = FundRequestForm
    template_name = 'dashboard/fund_request_form.html'
    model = models.FundRequest
    success_url = reverse_lazy('ui:fund-request-list')

    def _build_formsets(self, instance: models.FundRequest | None = None):
        recipient_formset = FundRequestRecipientFormSet(self.request.POST or None, prefix='recipients', instance=instance)
        article_formset = FundRequestArticleFormSet(self.request.POST or None, prefix='articles', instance=instance)
        return recipient_formset, article_formset

    def _can_edit(self, fr: models.FundRequest):
        return _is_editable_by_user(self.request.user, fr)

    def is_purchase_order_mode(self):
        return False

    def dispatch(self, request, *args, **kwargs):
        self.object = getattr(self, 'object', None)
        if self.object and not self._can_edit(self.object):
            messages.error(request, 'Submitted fund requests must be reopened before editing.')
            return HttpResponseRedirect(reverse('ui:fund-request-detail', args=[self.object.pk]))
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['recipient_formset'] = kwargs.get('recipient_formset', None) or self._build_formsets(self.object)[0]
        context['article_formset'] = kwargs.get('article_formset', None) or self._build_formsets(self.object)[1]
        context['status_choices'] = models.FundRequestStatusChoices.choices
        context['aid_type_choices'] = _fund_request_aid_type_choices()
        context['article_request_choices_json'] = json.dumps(_fund_request_article_choices(self.object))
        context['current_fund_request_id'] = getattr(self.object, 'pk', '') or ''
        context['purchase_order_mode'] = self.is_purchase_order_mode()
        context['back_url'] = reverse('ui:purchase-order-list') if self.is_purchase_order_mode() else reverse('ui:fund-request-list')
        return context

    def _collect_totals(self, instance: models.FundRequest):
        for article in instance.articles.all():
            article.recompute_totals(unit_price=article.unit_price, quantity=article.quantity)
        services.sync_fund_request_totals(instance)

    def _resolve_article_record(self, article_name: str):
        article_name = (article_name or '').strip()
        if not article_name:
            return None
        article = models.Article.objects.filter(article_name__iexact=article_name).first()
        if article:
            return article
        return models.Article.objects.create(
            article_name=article_name,
            cost_per_unit=0,
            item_type=models.ItemTypeChoices.ARTICLE,
            combo=True,
            is_active=False,
        )

    def _link_aid_sources(self, fr: models.FundRequest):
        models.DistrictBeneficiaryEntry.objects.filter(fund_request=fr).update(fund_request=None)
        models.PublicBeneficiaryEntry.objects.filter(fund_request=fr).update(fund_request=None)
        models.InstitutionsBeneficiaryEntry.objects.filter(fund_request=fr).update(fund_request=None)
        if fr.fund_request_type != models.FundRequestTypeChoices.AID:
            return
        for recipient in fr.recipients.exclude(source_entry_id__isnull=True).exclude(source_entry_id__exact=0):
            if recipient.beneficiary_type == models.RecipientTypeChoices.DISTRICT:
                models.DistrictBeneficiaryEntry.objects.filter(pk=recipient.source_entry_id).update(fund_request=fr)
            elif recipient.beneficiary_type == models.RecipientTypeChoices.PUBLIC:
                models.PublicBeneficiaryEntry.objects.filter(pk=recipient.source_entry_id).update(fund_request=fr)
            elif recipient.beneficiary_type in {models.RecipientTypeChoices.INSTITUTIONS, models.RecipientTypeChoices.OTHERS}:
                models.InstitutionsBeneficiaryEntry.objects.filter(pk=recipient.source_entry_id).update(fund_request=fr)

    def _is_aid_source_available(self, beneficiary_type, source_entry_id, current_fund_request=None):
        if not source_entry_id or not beneficiary_type:
            return False, 'Select a valid beneficiary.'
        entry = None
        if beneficiary_type == models.RecipientTypeChoices.DISTRICT:
            entry = models.DistrictBeneficiaryEntry.objects.select_related('fund_request').filter(pk=source_entry_id).first()
        elif beneficiary_type == models.RecipientTypeChoices.PUBLIC:
            entry = models.PublicBeneficiaryEntry.objects.select_related('fund_request').filter(pk=source_entry_id).first()
        elif beneficiary_type in {models.RecipientTypeChoices.INSTITUTIONS, models.RecipientTypeChoices.OTHERS}:
            entry = models.InstitutionsBeneficiaryEntry.objects.select_related('fund_request').filter(pk=source_entry_id).first()
        if not entry:
            return False, 'This beneficiary is no longer available.'
        if entry.fund_request_id and (not current_fund_request or entry.fund_request_id != current_fund_request.id):
            label = entry.fund_request.formatted_fund_request_number if entry.fund_request and entry.fund_request.fund_request_number else f'Draft #{entry.fund_request_id}'
            if entry.fund_request:
                return False, f'Already present in {label} ({entry.fund_request.get_status_display()}).'
            return False, f'Already present in {label}.'
        return True, ''

    def _validate_fund_request_formsets(self, fr, action, recipient_formset, article_formset):
        is_valid = True
        if fr.fund_request_type == models.FundRequestTypeChoices.AID:
            if action == 'submit' and not (fr.aid_type or '').strip():
                self.request._messages.add(messages.ERROR, 'Select the aid type before submit.')
                return False
            active_forms = [form for form in recipient_formset.forms if form.cleaned_data and not form.cleaned_data.get('DELETE', False)]
            if action == 'submit' and not active_forms:
                recipient_formset._non_form_errors = recipient_formset.error_class(['Add at least one recipient.'])
                return False
            seen_source_keys = {}
            for form in active_forms:
                beneficiary_type = form.cleaned_data.get('beneficiary_type')
                source_entry_id = form.cleaned_data.get('source_entry_id')
                if beneficiary_type and source_entry_id:
                    source_key = (str(beneficiary_type), str(source_entry_id))
                    if source_key in seen_source_keys:
                        form.add_error('beneficiary', 'This recipient is already added in the same fund request.')
                        seen_source_keys[source_key].add_error('beneficiary', 'This recipient is already added in the same fund request.')
                        is_valid = False
                    else:
                        seen_source_keys[source_key] = form
                if source_entry_id:
                    ok, message = self._is_aid_source_available(
                        beneficiary_type,
                        source_entry_id,
                        current_fund_request=fr if getattr(fr, 'pk', None) else None,
                    )
                    if not ok:
                        form.add_error('beneficiary', message)
                        is_valid = False
                if action == 'submit':
                    required_fields = ['beneficiary_type', 'beneficiary', 'source_entry_id', 'fund_requested', 'name_of_beneficiary', 'name_of_institution', 'details', 'cheque_in_favour']
                    if beneficiary_type != models.RecipientTypeChoices.DISTRICT:
                        required_fields.append('aadhar_number')
                    for field_name in required_fields:
                        value = form.cleaned_data.get(field_name)
                        if value in (None, '', 0, '0'):
                            form.add_error(field_name, 'Required for submit.')
                            is_valid = False
        else:
            active_forms = [form for form in article_formset.forms if form.cleaned_data and not form.cleaned_data.get('DELETE', False)]
            if action == 'submit' and not active_forms:
                article_formset._non_form_errors = article_formset.error_class(['Add at least one item.'])
                return False
            if action == 'submit':
                for form in active_forms:
                    required_fields = ['article_name', 'supplier_article_name', 'description', 'quantity', 'unit_price']
                    if not self.is_purchase_order_mode():
                        required_fields.extend(['gst_no', 'cheque_in_favour'])
                    for field_name in required_fields:
                        value = form.cleaned_data.get(field_name)
                        if value in (None, '', 0, '0'):
                            form.add_error(field_name, 'Required for submit.')
                            is_valid = False
        return is_valid

    def _validate_article_header_fields(self, form, fr, action):
        if action != 'submit' or fr.fund_request_type != models.FundRequestTypeChoices.ARTICLE:
            return True
        valid = True
        labels = [
            ('supplier_name', 'Vendor Name' if self.is_purchase_order_mode() else 'Supplier Name'),
            ('supplier_address', 'Vendor Address' if self.is_purchase_order_mode() else 'Address'),
            ('supplier_city', 'City'),
            ('supplier_state', 'State'),
            ('supplier_pincode', 'Pincode'),
        ]
        for field_name, label in labels:
            value = getattr(fr, field_name, None)
            if not str(value or '').strip():
                form.add_error(field_name, f'{label} is required for submit.')
                valid = False
        return valid

    def _set_fund_request_status(self, fr, action):
        if action == 'submit':
            fr.status = models.FundRequestStatusChoices.SUBMITTED
        else:
            fr.status = models.FundRequestStatusChoices.DRAFT

    def form_valid(self, form):
        action = self.request.POST.get('action', 'draft')
        if action == 'submit' and self.object and self.object.status != models.FundRequestStatusChoices.DRAFT:
            messages.error(self.request, 'Only draft fund requests can be submitted.')
            return HttpResponseRedirect(self.get_success_url())

        fr = form.save(commit=False)
        if self.is_purchase_order_mode():
            fr.fund_request_type = models.FundRequestTypeChoices.ARTICLE
            fr.aid_type = None
        if self.object and self.object.fund_request_number:
            fr.fund_request_number = self.object.fund_request_number
        if self.object and self.object.purchase_order_number:
            fr.purchase_order_number = self.object.purchase_order_number
        if not fr.created_by:
            fr.created_by = self.request.user
        self._set_fund_request_status(fr, action)

        header_ok = self._validate_article_header_fields(form, fr, action)

        recipient_formset, article_formset = self._build_formsets(fr)
        formsets_ok = recipient_formset.is_valid() and article_formset.is_valid()
        if not header_ok or not formsets_ok or not self._validate_fund_request_formsets(fr, action, recipient_formset, article_formset):
            messages.error(self.request, 'Please fix errors in recipients/articles before saving.')
            return self.render_to_response(
                self.get_context_data(
                    form=form,
                    recipient_formset=recipient_formset,
                    article_formset=article_formset,
                )
            )

        try:
            with transaction.atomic():
                if action == 'submit' and not fr.fund_request_number:
                    fr.fund_request_number = services.next_fund_request_number()
                if action == 'submit' and fr.fund_request_type == models.FundRequestTypeChoices.ARTICLE and not fr.purchase_order_number:
                    fr.purchase_order_number = services.next_purchase_order_number()
                fr.save()

                recipient_formset.instance = fr
                article_formset.instance = fr

                for deleted_form in getattr(recipient_formset, "deleted_forms", []):
                    deleted_instance = getattr(deleted_form, "instance", None)
                    if deleted_instance and deleted_instance.pk:
                        deleted_instance.delete()
                recipient_instances = recipient_formset.save(commit=False)
                for recipient in recipient_instances:
                    recipient.fund_request = fr
                    if recipient.beneficiary_type == models.RecipientTypeChoices.DISTRICT:
                        recipient.recipient_name = (
                            recipient.name_of_beneficiary
                            or recipient.name_of_institution
                            or recipient.district_name
                            or recipient.recipient_name
                            or recipient.beneficiary
                            or 'Recipient'
                        )
                    elif recipient.beneficiary_type == models.RecipientTypeChoices.PUBLIC:
                        recipient.recipient_name = recipient.name_of_beneficiary or recipient.recipient_name or recipient.beneficiary or 'Recipient'
                    elif recipient.beneficiary_type in {
                        models.RecipientTypeChoices.INSTITUTIONS,
                        models.RecipientTypeChoices.OTHERS,
                    }:
                        recipient.recipient_name = (
                            recipient.name_of_institution
                            or recipient.name_of_beneficiary
                            or recipient.recipient_name
                            or recipient.beneficiary
                            or 'Recipient'
                        )
                    else:
                        recipient.recipient_name = recipient.recipient_name or recipient.name_of_beneficiary or recipient.name_of_institution or recipient.beneficiary or 'Recipient'
                    recipient.save()

                for deleted_form in getattr(article_formset, "deleted_forms", []):
                    deleted_instance = getattr(deleted_form, "instance", None)
                    if deleted_instance and deleted_instance.pk:
                        deleted_instance.delete()
                article_instances = article_formset.save(commit=False)
                for article in article_instances:
                    article.fund_request = fr
                    if not article.article_id:
                        article.article = self._resolve_article_record(article.article_name)
                    if article.article and not article.article_name:
                        article.article_name = article.article.article_name
                    article.vendor_name = fr.supplier_name
                    article.vendor_address = fr.supplier_address
                    article.vendor_city = fr.supplier_city
                    article.vendor_state = fr.supplier_state
                    article.vendor_pincode = fr.supplier_pincode
                    article.unit_price = article.unit_price or 0
                    article.price_including_gst = article.unit_price * (article.quantity or 0)
                    article.value = article.price_including_gst
                    article.cumulative = article.value
                    article.save()

                self._link_aid_sources(fr)
                self._collect_totals(fr)
                services.sync_order_entries_from_fund_request(fr, actor=self.request.user)
                self.object = fr

                if action == 'submit':
                    services.log_audit(
                        user=self.request.user,
                        action_type=models.ActionTypeChoices.STATUS_CHANGE,
                        entity_type='fund_request',
                        entity_id=str(fr.id),
                        details={'status': models.FundRequestStatusChoices.SUBMITTED},
                        ip_address=self.request.META.get('REMOTE_ADDR'),
                        user_agent=self.request.META.get('HTTP_USER_AGENT', ''),
                    )
                    messages.success(self.request, 'Fund request submitted.')
                else:
                    messages.success(self.request, 'Fund request saved as draft.')
        except IntegrityError:
            form.add_error(None, 'Fund request number already exists. Please try submitting again.')
            return self.render_to_response(
                self.get_context_data(
                    form=form,
                    recipient_formset=recipient_formset,
                    article_formset=article_formset,
                )
            )
        return HttpResponseRedirect(self.get_success_url())


class FundRequestCreateView(LoginRequiredMixin, FundRequestCreateUpdateMixin, CreateView):
    pass


class FundRequestUpdateView(LoginRequiredMixin, FundRequestCreateUpdateMixin, UpdateView):
    pass


class FundRequestDetailView(LoginRequiredMixin, RoleRequiredMixin, DetailView):
    module_key = models.ModuleKeyChoices.ORDER_FUND_REQUEST
    permission_action = "view"
    model = models.FundRequest
    template_name = "dashboard/fund_request_detail.html"
    context_object_name = "fund_request"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["media_url"] = settings.MEDIA_URL
        context["can_edit"] = _is_editable_by_user(self.request.user, self.object)
        context["can_reopen"] = self.request.user.role == "admin" and self.object.status == models.FundRequestStatusChoices.SUBMITTED
        context["can_delete"] = self.request.user.role == "admin" and self.request.user.has_module_permission(
            models.ModuleKeyChoices.ORDER_FUND_REQUEST,
            "delete",
        )
        return context


class FundRequestPDFView(LoginRequiredMixin, RoleRequiredMixin, View):
    module_key = models.ModuleKeyChoices.ORDER_FUND_REQUEST
    permission_action = "view"

    def get(self, request, pk):
        fund_request = get_object_or_404(
            models.FundRequest.objects.select_related("created_by").prefetch_related("recipients", "articles"),
            pk=pk,
        )
        pdf_buffer = services.generate_fund_request_pdf(fund_request)
        filename_base = fund_request.formatted_fund_request_number or f"FR-DRAFT-{fund_request.pk}"
        response = HttpResponse(pdf_buffer.getvalue(), content_type="application/pdf")
        response["Content-Disposition"] = f'inline; filename="{filename_base}.pdf"'
        return response


class FundRequestDeleteView(LoginRequiredMixin, AdminRequiredMixin, DeleteView):
    module_key = models.ModuleKeyChoices.ORDER_FUND_REQUEST
    permission_action = "delete"
    model = models.FundRequest
    template_name = "dashboard/fund_request_confirm_delete.html"
    success_url = reverse_lazy("ui:fund-request-list")

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        models.OrderEntry.objects.filter(fund_request=self.object).delete()
        messages.warning(self.request, "Fund request deleted.")
        return super().post(request, *args, **kwargs)


class FundRequestSubmitView(LoginRequiredMixin, WriteRoleMixin, View):
    module_key = models.ModuleKeyChoices.ORDER_FUND_REQUEST
    permission_action = "submit"
    allowed_roles = {"admin", "editor"}

    def post(self, request, pk):
        fr = models.FundRequest.objects.get(pk=pk)
        if not _is_editable_by_user(request.user, fr) or request.user.role == "viewer":
            return HttpResponse("Forbidden", status=403)
        if fr.status != models.FundRequestStatusChoices.DRAFT:
            messages.error(request, "Only draft fund requests can be submitted.")
            return HttpResponseRedirect(reverse("ui:fund-request-detail", args=[fr.pk]))
        fr.status = models.FundRequestStatusChoices.SUBMITTED
        if not fr.fund_request_number:
            fr.fund_request_number = services.next_fund_request_number()
        update_fields = ["status", "fund_request_number"]
        if fr.fund_request_type == models.FundRequestTypeChoices.ARTICLE and not fr.purchase_order_number:
            fr.purchase_order_number = services.next_purchase_order_number()
            update_fields.append("purchase_order_number")
        fr.save(update_fields=update_fields)
        services.log_audit(
            user=request.user,
            action_type=models.ActionTypeChoices.STATUS_CHANGE,
            entity_type="fund_request",
            entity_id=str(fr.id),
            details={"status": models.FundRequestStatusChoices.SUBMITTED},
            ip_address=request.META.get("REMOTE_ADDR"),
            user_agent=request.META.get("HTTP_USER_AGENT", ""),
        )
        services.sync_fund_request_totals(fr)
        services.sync_order_entries_from_fund_request(fr, actor=request.user)
        messages.success(request, "Fund request submitted.")
        return HttpResponseRedirect(reverse("ui:fund-request-detail", args=[fr.pk]))


class FundRequestReopenView(LoginRequiredMixin, AdminRequiredMixin, View):
    module_key = models.ModuleKeyChoices.ORDER_FUND_REQUEST
    permission_action = "reopen"

    def post(self, request, pk):
        fr = get_object_or_404(models.FundRequest, pk=pk)
        if fr.status != models.FundRequestStatusChoices.SUBMITTED:
            messages.error(request, "Only submitted fund requests can be reopened.")
            return HttpResponseRedirect(reverse("ui:fund-request-detail", args=[fr.pk]))
        previous_status = fr.status
        fr.status = models.FundRequestStatusChoices.DRAFT
        fr.save(update_fields=["status"])
        services.log_audit(
            user=request.user,
            action_type=models.ActionTypeChoices.STATUS_CHANGE,
            entity_type="fund_request",
            entity_id=str(fr.id),
            details={"from": previous_status, "to": models.FundRequestStatusChoices.DRAFT},
            **_request_audit_meta(request),
        )
        services.sync_fund_request_totals(fr)
        services.sync_order_entries_from_fund_request(fr, actor=request.user)
        messages.success(request, "Fund request reopened as draft.")
        return HttpResponseRedirect(reverse("ui:fund-request-edit", args=[fr.pk]))


class FundRequestDocumentUploadView(LoginRequiredMixin, WriteRoleMixin, FormView):
    module_key = models.ModuleKeyChoices.ORDER_FUND_REQUEST
    permission_action = "create_edit"
    template_name = "dashboard/fund_request_upload_document.html"
    form_class = FundRequestDocumentUploadForm

    def dispatch(self, request, *args, **kwargs):
        self.fund_request = models.FundRequest.objects.get(pk=kwargs["pk"])
        if not _is_editable_by_user(request.user, self.fund_request):
            return HttpResponse("Forbidden", status=403)
        return super().dispatch(request, *args, **kwargs)

    def get_success_url(self):
        return reverse("ui:fund-request-detail", args=[self.fund_request.pk])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["fund_request"] = self.fund_request
        return context

    def form_valid(self, form):
        uploaded_file = form.cleaned_data["file"]
        upload_dir = os.path.join("fund-request-docs", str(self.fund_request.pk))
        relative_path = os.path.join(upload_dir, uploaded_file.name)
        from django.core.files.storage import default_storage

        stored_path = default_storage.save(relative_path, uploaded_file)
        models.FundRequestDocument.objects.create(
            fund_request=self.fund_request,
            document_type=form.cleaned_data["document_type"],
            file_path=stored_path,
            file_name=uploaded_file.name,
            generated_by=self.request.user,
        )
        messages.success(self.request, "Document uploaded.")
        return HttpResponseRedirect(self.get_success_url())


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
            'id': article.id,
            'article_name': article.article_name,
            'cost_per_unit': str(article.cost_per_unit or 0),
        }
        for article in models.Article.objects.filter(
            item_type=models.ItemTypeChoices.ARTICLE,
            is_active=True,
        ).order_by('article_name')
    ]


class PurchaseOrderListView(LoginRequiredMixin, RoleRequiredMixin, ListView):
    module_key = models.ModuleKeyChoices.PURCHASE_ORDER
    permission_action = "view"
    model = models.PurchaseOrder
    template_name = "dashboard/purchase_order_list.html"
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
    template_name = "dashboard/purchase_order_form.html"
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
        return response


class PurchaseOrderSubmitView(LoginRequiredMixin, WriteRoleMixin, View):
    module_key = models.ModuleKeyChoices.PURCHASE_ORDER
    permission_action = "submit"
    allowed_roles = {"admin", "editor"}

    def post(self, request, pk):
        purchase_order = get_object_or_404(models.PurchaseOrder, pk=pk)
        if not _is_editable_purchase_order(request.user, purchase_order) or request.user.role == "viewer":
            return HttpResponse("Forbidden", status=403)
        if purchase_order.status != models.FundRequestStatusChoices.DRAFT:
            messages.error(request, "Only draft purchase orders can be submitted.")
            return HttpResponseRedirect(reverse("ui:purchase-order-list"))
        purchase_order.status = models.FundRequestStatusChoices.SUBMITTED
        if not purchase_order.purchase_order_number:
            purchase_order.purchase_order_number = services.next_purchase_order_number()
        purchase_order.save(update_fields=["status", "purchase_order_number"])
        services.log_audit(
            user=request.user,
            action_type=models.ActionTypeChoices.STATUS_CHANGE,
            entity_type="purchase_order",
            entity_id=str(purchase_order.id),
            details={"status": models.FundRequestStatusChoices.SUBMITTED},
            **_request_audit_meta(request),
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
        services.log_audit(
            user=request.user,
            action_type=models.ActionTypeChoices.STATUS_CHANGE,
            entity_type="purchase_order",
            entity_id=str(purchase_order.id),
            details={"from": previous_status, "to": models.FundRequestStatusChoices.DRAFT},
            **_request_audit_meta(request),
        )
        messages.success(request, "Purchase order reopened as draft.")
        return HttpResponseRedirect(reverse("ui:purchase-order-edit", args=[purchase_order.pk]))


class PurchaseOrderDeleteView(LoginRequiredMixin, AdminRequiredMixin, DeleteView):
    module_key = models.ModuleKeyChoices.PURCHASE_ORDER
    permission_action = "delete"
    model = models.PurchaseOrder
    template_name = "dashboard/purchase_order_confirm_delete.html"
    success_url = reverse_lazy("ui:purchase-order-list")

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        messages.warning(self.request, "Purchase order deleted.")
        return super().post(request, *args, **kwargs)


class AidRecipientTemplateDownloadView(LoginRequiredMixin, RoleRequiredMixin, View):
    module_key = models.ModuleKeyChoices.BASE_FILES
    permission_action = "view"

    def get(self, request, *args, **kwargs):
        headers = [
            "beneficiary_type",
            "application_number",
            "beneficiary",
            "fund_requested",
            "details",
            "cheque_rtgs_in_favour",
        ]
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="aid_recipients_template.csv"'
        writer = csv.writer(response)
        writer.writerow(headers)
        return response


class MasterDataBaseView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    module_key = models.ModuleKeyChoices.BASE_FILES
    permission_action = "view"
    template_name = "dashboard/module_master_data.html"
    data_key = None
    page_title = "Base Files"
    upload_help = "Upload a CSV file to refresh the stored records."

    def dispatch(self, request, *args, **kwargs):
        if not self.data_key:
            raise ValueError("MasterDataBaseView requires data_key")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "active_data_key": self.data_key,
                "page_title": self.page_title,
                "upload_help": self.upload_help,
                "upload_form": kwargs.get("upload_form") or MasterDataUploadForm(),
                "records": kwargs.get("records") if kwargs.get("records") is not None else self.get_records(),
                "summary": self.get_summary(),
                "replace_supported": self.data_key == "history",
            }
        )
        return context

    def get_records(self):
        if self.data_key == "districts":
            return list(models.DistrictMaster.objects.order_by("district_name")[:100])
        if self.data_key == "articles":
            return list(models.Article.objects.order_by("article_name")[:100])
        return list(models.PublicBeneficiaryHistory.objects.order_by("-year", "-created_at")[:100])

    def get_summary(self):
        return {
            "districts": models.DistrictMaster.objects.count(),
            "articles": models.Article.objects.count(),
            "history": models.PublicBeneficiaryHistory.objects.count(),
        }

    def post(self, request, *args, **kwargs):
        if not request.user.has_module_permission(self.module_key, "upload_replace"):
            messages.error(request, "You do not have permission to upload base files.")
            return HttpResponseRedirect(request.path)

        form = MasterDataUploadForm(request.POST, request.FILES)
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(upload_form=form))

        uploaded = form.cleaned_data["file"]
        replace_existing = bool(form.cleaned_data.get("replace_existing"))
        inserted, updated = self.import_rows(uploaded, replace_existing=replace_existing)
        messages.success(request, f"{self.page_title} import complete. inserted={inserted}, updated={updated}")
        return HttpResponseRedirect(request.path)

    def import_rows(self, uploaded_file, *, replace_existing=False):
        if self.data_key == "districts":
            return _import_district_master_csv(uploaded_file)
        if self.data_key == "articles":
            return _import_article_master_csv(uploaded_file)
        return _import_public_history_csv(uploaded_file, replace_existing=replace_existing)


class MasterDataDistrictView(MasterDataBaseView):
    data_key = "districts"
    page_title = "District Master"
    upload_help = "Upload the yearly district president file. The district code, president, budget, and mobile number will be updated in place."


class MasterDataArticleView(MasterDataBaseView):
    data_key = "articles"
    page_title = "Article Price List"
    upload_help = "Upload the latest article price list. Existing article names are updated; new article names are added."


class MasterDataHistoryView(MasterDataBaseView):
    data_key = "history"
    page_title = "Past Beneficiary History"
    upload_help = "Upload the past district/public beneficiary file. This is used for Aadhaar warnings and reference checks during entry."


def _csv_reader_from_upload(uploaded_file):
    uploaded_file.seek(0)
    return csv.DictReader(io.StringIO(uploaded_file.read().decode("utf-8-sig")))


def _import_district_master_csv(uploaded_file):
    inserted = 0
    updated = 0
    for row in _csv_reader_from_upload(uploaded_file):
        district_name = (row.get("district_name") or "").strip()
        if not district_name:
            continue
        budget_raw = (row.get("allotted_budget") or "0").strip().replace(",", "")
        allotted_budget = Decimal(budget_raw or "0")
        _, created = models.DistrictMaster.objects.update_or_create(
            district_name=district_name,
            defaults={
                "application_number": (row.get("application_number") or "").strip(),
                "allotted_budget": allotted_budget,
                "president_name": (row.get("president_name") or "").strip(),
                "mobile_number": (row.get("mobile_number") or "").strip(),
                "is_active": True,
            },
        )
        inserted += int(created)
        updated += int(not created)
    return inserted, updated


def _import_article_master_csv(uploaded_file):
    inserted = 0
    updated = 0
    valid_item_types = {choice for choice, _ in models.ItemTypeChoices.choices}
    for row in _csv_reader_from_upload(uploaded_file):
        article_name = (row.get("article_name") or "").strip()
        if not article_name:
            continue
        cost_raw = (row.get("cost_per_unit") or "0").strip().replace(",", "")
        cost_per_unit = Decimal(cost_raw or "0")
        item_type = (row.get("item_type") or models.ItemTypeChoices.ARTICLE).strip()
        if item_type not in valid_item_types:
            item_type = models.ItemTypeChoices.ARTICLE
        is_active_value = (row.get("is_active") or "").strip().lower()
        is_active = is_active_value in {"active", "true", "1", "yes"}
        _, created = models.Article.objects.update_or_create(
            article_name=article_name,
            defaults={
                "cost_per_unit": cost_per_unit,
                "item_type": item_type,
                "category": (row.get("category") or "").strip() or None,
                "master_category": (row.get("master_category") or "").strip() or None,
                "is_active": is_active,
            },
        )
        inserted += int(created)
        updated += int(not created)
    return inserted, updated


def _import_public_history_csv(uploaded_file, *, replace_existing=False):
    inserted = 0
    if replace_existing:
        models.PublicBeneficiaryHistory.objects.all().delete()
    for row in _csv_reader_from_upload(uploaded_file):
        year_raw = (row.get("year") or "").strip()
        if not year_raw:
            continue
        models.PublicBeneficiaryHistory.objects.create(
            aadhar_number=(row.get("aadhar_number") or "").strip(),
            name=(row.get("name") or "").strip(),
            year=int(year_raw),
            article_name=(row.get("article_name") or "").strip() or None,
            application_number=(row.get("application_number") or "").strip() or None,
            comments=(row.get("comments") or "").strip() or None,
            is_handicapped=_parse_bool(row.get("is_handicapped")),
            address=(row.get("address") or "").strip() or None,
            mobile=(row.get("mobile") or "").strip() or None,
            aadhar_number_sp=(row.get("aadhar_number_sp") or "").strip() or None,
            is_selected=_parse_bool(row.get("is_selected")),
            category=(row.get("category") or "").strip() or None,
        )
        inserted += 1
    return inserted, 0


def _parse_bool(value):
    text = str(value or "").strip().lower()
    if text in {"true", "1", "yes"}:
        return True
    if text in {"false", "0", "no"}:
        return False
    return None
