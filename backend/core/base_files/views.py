from __future__ import annotations

"""Views for backbone base-files management and template download."""

import csv
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse, HttpResponseRedirect
from django.views import View
from django.views.generic import TemplateView

from core import models
from core.base_files.forms import MasterDataUploadForm
from core.shared.csv_utils import _csv_reader_from_upload
from core.shared.permissions import RoleRequiredMixin


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
    template_name = "base_files/module_master_data.html"
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
