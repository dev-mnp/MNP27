from __future__ import annotations

"""Forms owned by the order_fund_request module."""

from django import forms

from core import models


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
            "gst_number",
            "supplier_name",
            "supplier_address",
            "supplier_city",
            "supplier_state",
            "supplier_pincode",
            "purchase_order_number",
        ]
        widgets = {
            "fund_request_type": forms.RadioSelect(),
            "aid_type": forms.TextInput(attrs={"class": "input"}),
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
        self.fields["fund_request_type"].choices = [
            (value, label) for value, label in self.fields["fund_request_type"].choices if value
        ]


class FundRequestRecipientForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["beneficiary_type"].choices = [("", "Select beneficiary type")] + [
            (value, label) for value, label in models.RecipientTypeChoices.choices
            if value in {
                models.RecipientTypeChoices.DISTRICT,
                models.RecipientTypeChoices.PUBLIC,
                models.RecipientTypeChoices.INSTITUTIONS,
            }
        ]
        beneficiary_choices = [("", "Select beneficiary")]
        if getattr(self.instance, "beneficiary", None):
            current_label = (
                self.instance.recipient_name
                or self.instance.name_of_beneficiary
                or self.instance.name_of_institution
                or self.instance.district_name
                or self.instance.beneficiary
            )
            beneficiary_choices.append((self.instance.beneficiary, current_label))
        self.fields["beneficiary"].widget.choices = beneficiary_choices

    class Meta:
        model = models.FundRequestRecipient
        fields = [
            "beneficiary_type",
            "beneficiary",
            "source_entry_id",
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
            "beneficiary_type": forms.Select(attrs={"class": "input js-beneficiary-type-select"}),
            "beneficiary": forms.Select(attrs={"class": "input js-beneficiary-select"}),
            "source_entry_id": forms.HiddenInput(),
            "recipient_name": forms.HiddenInput(),
            "name_of_beneficiary": forms.TextInput(attrs={"class": "input", "placeholder": "Name of beneficiary"}),
            "name_of_institution": forms.TextInput(attrs={"class": "input", "placeholder": "Name of institution"}),
            "details": forms.Textarea(attrs={"class": "textarea", "rows": 3, "placeholder": "Details"}),
            "fund_requested": forms.NumberInput(attrs={"class": "input", "step": "0.01", "min": "0"}),
            "aadhar_number": forms.TextInput(attrs={"class": "input", "placeholder": "Aadhaar number"}),
            "address": forms.HiddenInput(),
            "cheque_in_favour": forms.Textarea(attrs={"class": "textarea", "rows": 3, "placeholder": "Cheque / RTGS in Favour"}),
            "cheque_no": forms.HiddenInput(),
            "notes": forms.HiddenInput(),
            "district_name": forms.HiddenInput(),
        }


class FundRequestArticleForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["article"].required = False
        article_choices = [("", "Select article")]
        if getattr(self.instance, "article_name", None):
            article_choices.append((self.instance.article_name, self.instance.article_name))
        self.fields["article_name"].choices = article_choices

    class Meta:
        model = models.FundRequestArticle
        fields = [
            "article",
            "beneficiary",
            "article_name",
            "gst_no",
            "supplier_article_name",
            "description",
            "quantity",
            "unit_price",
            "price_including_gst",
            "value",
            "cumulative",
            "cheque_in_favour",
            "cheque_no",
        ]
        widgets = {
            "article": forms.HiddenInput(),
            "beneficiary": forms.HiddenInput(),
            "article_name": forms.Select(attrs={"class": "input js-article-select"}),
            "gst_no": forms.TextInput(attrs={"class": "input", "placeholder": "GST number"}),
            "supplier_article_name": forms.TextInput(attrs={"class": "input", "placeholder": "Supplier article name"}),
            "description": forms.TextInput(attrs={"class": "input", "placeholder": "Description"}),
            "quantity": forms.NumberInput(attrs={"class": "input", "min": "0"}),
            "unit_price": forms.NumberInput(attrs={"class": "input", "step": "0.01", "min": "0"}),
            "price_including_gst": forms.HiddenInput(),
            "value": forms.NumberInput(attrs={"class": "input", "step": "0.01", "readonly": "readonly"}),
            "cumulative": forms.HiddenInput(),
            "cheque_in_favour": forms.Textarea(attrs={"class": "textarea", "rows": 3, "placeholder": "Cheque / RTGS in Favour"}),
            "cheque_no": forms.HiddenInput(),
        }

    def clean(self):
        cleaned = super().clean()
        article = cleaned.get("article")
        if article and not cleaned.get("article_name"):
            cleaned["article_name"] = article.article_name
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
