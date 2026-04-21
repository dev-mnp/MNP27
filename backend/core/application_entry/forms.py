from __future__ import annotations

"""Forms owned by the application_entry module."""

from django import forms
from django.core.exceptions import ValidationError

from core import models


class DistrictBeneficiaryEntryForm(forms.ModelForm):
    class Meta:
        model = models.DistrictBeneficiaryEntry
        fields = [
            "district",
            "application_number",
            "article",
            "article_cost_per_unit",
            "quantity",
            "total_amount",
            "notes",
            "status",
            "fund_request",
        ]
        widgets = {
            "district": forms.Select(attrs={"class": "input"}),
            "application_number": forms.TextInput(attrs={"class": "input"}),
            "article": forms.HiddenInput(),
            "article_cost_per_unit": forms.NumberInput(attrs={"class": "input", "step": "0.01"}),
            "quantity": forms.NumberInput(attrs={"class": "input"}),
            "total_amount": forms.NumberInput(attrs={"class": "input", "step": "0.01"}),
            "notes": forms.Textarea(attrs={"class": "textarea", "rows": 3}),
            "status": forms.Select(attrs={"class": "input"}),
            "fund_request": forms.Select(attrs={"class": "input"}),
        }

    def clean(self):
        cleaned = super().clean()
        article = cleaned.get("article")
        quantity = cleaned.get("quantity") or 0
        unit_cost = cleaned.get("article_cost_per_unit")
        if article and not article.allow_manual_price:
            unit_cost = article.cost_per_unit
            cleaned["article_cost_per_unit"] = unit_cost
        if unit_cost is not None:
            cleaned["total_amount"] = unit_cost * quantity
        return cleaned


class PublicBeneficiaryEntryForm(forms.ModelForm):
    class Meta:
        model = models.PublicBeneficiaryEntry
        fields = [
            "application_number",
            "name",
            "aadhar_number",
            "is_handicapped",
            "gender",
            "female_status",
            "address",
            "mobile",
            "article",
            "article_cost_per_unit",
            "quantity",
            "total_amount",
            "notes",
            "status",
            "fund_request",
        ]
        widgets = {
            "application_number": forms.TextInput(attrs={"class": "input"}),
            "name": forms.TextInput(attrs={"class": "input"}),
            "aadhar_number": forms.TextInput(attrs={"class": "input"}),
            "gender": forms.Select(attrs={"class": "input"}),
            "female_status": forms.Select(attrs={"class": "input"}),
            "address": forms.Textarea(attrs={"class": "textarea", "rows": 3}),
            "mobile": forms.TextInput(attrs={"class": "input"}),
            "article": forms.HiddenInput(),
            "article_cost_per_unit": forms.NumberInput(attrs={"class": "input", "step": "0.01"}),
            "quantity": forms.NumberInput(attrs={"class": "input"}),
            "total_amount": forms.NumberInput(attrs={"class": "input", "step": "0.01"}),
            "notes": forms.Textarea(attrs={"class": "textarea", "rows": 3}),
            "status": forms.Select(attrs={"class": "input"}),
            "fund_request": forms.Select(attrs={"class": "input"}),
        }

    def clean(self):
        cleaned = super().clean()
        article = cleaned.get("article")
        quantity = cleaned.get("quantity") or 0
        unit_cost = cleaned.get("article_cost_per_unit")
        if article and not article.allow_manual_price:
            unit_cost = article.cost_per_unit
            cleaned["article_cost_per_unit"] = unit_cost
        if unit_cost is not None:
            cleaned["total_amount"] = unit_cost * quantity
        return cleaned


class InstitutionsBeneficiaryEntryForm(forms.ModelForm):
    class Meta:
        model = models.InstitutionsBeneficiaryEntry
        fields = [
            "institution_name",
            "institution_type",
            "application_number",
            "address",
            "mobile",
            "article",
            "article_cost_per_unit",
            "quantity",
            "total_amount",
            "notes",
            "status",
            "fund_request",
        ]
        widgets = {
            "institution_name": forms.TextInput(attrs={"class": "input"}),
            "institution_type": forms.Select(attrs={"class": "input"}),
            "application_number": forms.TextInput(attrs={"class": "input"}),
            "address": forms.Textarea(attrs={"class": "textarea", "rows": 3}),
            "mobile": forms.TextInput(attrs={"class": "input"}),
            "article": forms.HiddenInput(),
            "article_cost_per_unit": forms.NumberInput(attrs={"class": "input", "step": "0.01"}),
            "quantity": forms.NumberInput(attrs={"class": "input"}),
            "total_amount": forms.NumberInput(attrs={"class": "input", "step": "0.01"}),
            "notes": forms.Textarea(attrs={"class": "textarea", "rows": 3}),
            "status": forms.Select(attrs={"class": "input"}),
            "fund_request": forms.Select(attrs={"class": "input"}),
        }

    def clean(self):
        cleaned = super().clean()
        article = cleaned.get("article")
        quantity = cleaned.get("quantity") or 0
        unit_cost = cleaned.get("article_cost_per_unit")
        if article and not article.allow_manual_price:
            unit_cost = article.cost_per_unit
            cleaned["article_cost_per_unit"] = unit_cost
        if unit_cost is not None:
            cleaned["total_amount"] = unit_cost * quantity
        return cleaned


class ApplicationAttachmentUploadForm(forms.Form):
    ALLOWED_EXTENSIONS = {"pdf", "jpg", "jpeg", "png", "webp", "doc", "docx", "xls", "xlsx", "csv"}
    ALLOWED_CONTENT_TYPES = {
        "application/pdf",
        "image/jpeg",
        "image/png",
        "image/webp",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.ms-excel",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "text/csv",
        "application/csv",
    }
    MAX_FILE_SIZE = 10 * 1024 * 1024
    MAX_FILES_PER_APPLICATION = 2

    file_name = forms.CharField(
        required=False,
        max_length=255,
        widget=forms.TextInput(
            attrs={
                "class": "input",
                "placeholder": "Optional display name",
            }
        ),
    )
    file = forms.FileField(
        widget=forms.ClearableFileInput(
            attrs={
                "class": "input",
                "accept": ".pdf,.jpg,.jpeg,.png,.webp,.doc,.docx,.xls,.xlsx,.csv",
            }
        )
    )

    def clean_file(self):
        uploaded = self.cleaned_data["file"]
        name = uploaded.name or ""
        extension = name.rsplit(".", 1)[-1].lower() if "." in name else ""
        if extension not in self.ALLOWED_EXTENSIONS:
            allowed = ", ".join(sorted(ext.upper() for ext in self.ALLOWED_EXTENSIONS))
            raise ValidationError(f"Unsupported file type. Allowed types: {allowed}.")
        if uploaded.size > self.MAX_FILE_SIZE:
            raise ValidationError("File size must be 10 MB or less.")
        content_type = str(getattr(uploaded, "content_type", "") or "").strip().lower()
        if content_type and content_type not in self.ALLOWED_CONTENT_TYPES:
            raise ValidationError("Unsupported file content type.")
        return uploaded

    def clean_file_name(self):
        value = (self.cleaned_data.get("file_name") or "").strip()
        return value
