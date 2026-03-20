from __future__ import annotations

from django import forms
from django.core.exceptions import ValidationError

from . import models


class ArticleForm(forms.ModelForm):
    class Meta:
        model = models.Article
        fields = [
            "article_name",
            "article_name_tk",
            "cost_per_unit",
            "item_type",
            "category",
            "master_category",
            "comments",
            "is_active",
            "combo",
        ]
        widgets = {
            "article_name": forms.TextInput(attrs={"class": "input", "autofocus": True}),
            "article_name_tk": forms.TextInput(attrs={"class": "input"}),
            "cost_per_unit": forms.NumberInput(attrs={"class": "input", "step": "0.01"}),
            "item_type": forms.Select(attrs={"class": "input"}),
            "category": forms.TextInput(attrs={"class": "input"}),
            "master_category": forms.TextInput(attrs={"class": "input"}),
            "comments": forms.Textarea(attrs={"class": "textarea", "rows": 3}),
        }


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
            "article": forms.Select(attrs={"class": "input"}),
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
        if article and unit_cost in (None, 0):
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
            "article": forms.Select(attrs={"class": "input"}),
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
        if article and unit_cost in (None, 0):
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
            "article": forms.Select(attrs={"class": "input"}),
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
        if article and unit_cost in (None, 0):
            unit_cost = article.cost_per_unit
            cleaned["article_cost_per_unit"] = unit_cost
        if unit_cost is not None:
            cleaned["total_amount"] = unit_cost * quantity
        return cleaned


class ApplicationAttachmentUploadForm(forms.Form):
    ALLOWED_EXTENSIONS = {"pdf", "jpg", "jpeg", "png", "webp", "doc", "docx", "xls", "xlsx", "csv"}
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
        return uploaded

    def clean_file_name(self):
        value = (self.cleaned_data.get("file_name") or "").strip()
        return value


class FundRequestForm(forms.ModelForm):
    action = forms.ChoiceField(
        required=False,
        choices=[
            ("draft", "Save draft"),
            ("submit", "Submit"),
        ],
        initial="draft",
    )

    class Meta:
        model = models.FundRequest
        fields = [
            "fund_request_type",
            "aid_type",
            "notes",
            "fund_request_number",
            "gst_number",
            "supplier_name",
            "supplier_address",
            "supplier_city",
            "supplier_state",
            "supplier_pincode",
            "purchase_order_number",
        ]
        widgets = {
            "fund_request_type": forms.Select(attrs={"class": "input"}),
            "aid_type": forms.TextInput(attrs={"class": "input"}),
            "notes": forms.Textarea(attrs={"class": "textarea", "rows": 4}),
            "fund_request_number": forms.TextInput(attrs={"class": "input"}),
            "gst_number": forms.TextInput(attrs={"class": "input"}),
            "supplier_name": forms.TextInput(attrs={"class": "input"}),
            "supplier_address": forms.Textarea(attrs={"class": "textarea", "rows": 3}),
            "supplier_city": forms.TextInput(attrs={"class": "input"}),
            "supplier_state": forms.TextInput(attrs={"class": "input"}),
            "supplier_pincode": forms.TextInput(attrs={"class": "input"}),
            "purchase_order_number": forms.TextInput(attrs={"class": "input"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["fund_request_number"].required = False
        if self.instance.pk:
            self.fields["fund_request_number"].help_text = "System number can be generated after submit."
        else:
            self.fields["fund_request_number"].help_text = "Optional in draft."


class FundRequestRecipientForm(forms.ModelForm):
    class Meta:
        model = models.FundRequestRecipient
        fields = [
            "beneficiary_type",
            "beneficiary",
            "recipient_name",
            "name_of_beneficiary",
            "name_of_institution",
            "details",
            "fund_requested",
            "aadhar_number",
            "address",
            "cheque_in_favour",
            "cheque_no",
            "notes",
            "district_name",
        ]
        widgets = {
            "beneficiary_type": forms.Select(attrs={"class": "input"}),
            "beneficiary": forms.Textarea(attrs={"class": "textarea", "rows": 2}),
            "recipient_name": forms.TextInput(attrs={"class": "input"}),
            "name_of_beneficiary": forms.TextInput(attrs={"class": "input"}),
            "name_of_institution": forms.TextInput(attrs={"class": "input"}),
            "details": forms.Textarea(attrs={"class": "textarea", "rows": 2}),
            "fund_requested": forms.NumberInput(attrs={"class": "input"}),
            "aadhar_number": forms.TextInput(attrs={"class": "input"}),
            "address": forms.Textarea(attrs={"class": "textarea", "rows": 2}),
            "cheque_in_favour": forms.TextInput(attrs={"class": "input"}),
            "cheque_no": forms.TextInput(attrs={"class": "input"}),
            "notes": forms.Textarea(attrs={"class": "textarea", "rows": 2}),
            "district_name": forms.TextInput(attrs={"class": "input"}),
        }


class FundRequestArticleForm(forms.ModelForm):
    class Meta:
        model = models.FundRequestArticle
        fields = [
            "article",
            "beneficiary",
            "article_name",
            "gst_no",
            "quantity",
            "unit_price",
            "price_including_gst",
            "value",
            "cumulative",
            "cheque_in_favour",
            "cheque_no",
            "supplier_article_name",
            "description",
        ]
        widgets = {
            "article": forms.Select(attrs={"class": "input"}),
            "beneficiary": forms.Textarea(attrs={"class": "textarea", "rows": 2}),
            "article_name": forms.TextInput(attrs={"class": "input"}),
            "gst_no": forms.TextInput(attrs={"class": "input"}),
            "quantity": forms.NumberInput(attrs={"class": "input"}),
            "unit_price": forms.NumberInput(attrs={"class": "input", "step": "0.01"}),
            "price_including_gst": forms.NumberInput(attrs={"class": "input", "step": "0.01"}),
            "value": forms.NumberInput(attrs={"class": "input", "step": "0.01"}),
            "cumulative": forms.NumberInput(attrs={"class": "input", "step": "0.01"}),
            "cheque_in_favour": forms.TextInput(attrs={"class": "input"}),
            "cheque_no": forms.TextInput(attrs={"class": "input"}),
            "supplier_article_name": forms.TextInput(attrs={"class": "input"}),
            "description": forms.Textarea(attrs={"class": "textarea", "rows": 2}),
        }

    def clean(self):
        cleaned = super().clean()
        article = cleaned.get("article")
        if article and not cleaned.get("article_name"):
            cleaned["article_name"] = article.article_name
        if article and cleaned.get("unit_price") in (None, 0):
            cleaned["unit_price"] = article.cost_per_unit
        quantity = cleaned.get("quantity") or 0
        unit_price = cleaned.get("unit_price") or 0
        cleaned["price_including_gst"] = unit_price * quantity
        cleaned["value"] = unit_price * quantity
        cleaned["cumulative"] = unit_price * quantity
        return cleaned


class FundRequestDocumentUploadForm(forms.Form):
    document_type = forms.ChoiceField(
        required=True,
        choices=models.FundRequestDocumentType.choices,
        widget=forms.Select(attrs={"class": "input"}),
    )
    file = forms.FileField(required=True, widget=forms.ClearableFileInput(attrs={"class": "input"}))


class MasterDataUploadForm(forms.Form):
    file = forms.FileField(required=True, widget=forms.ClearableFileInput(attrs={"class": "input"}))
    replace_existing = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={"style": "width: auto; margin-right: 8px;"}),
        help_text="For past history only: clear the old imported rows before loading the new file.",
    )
