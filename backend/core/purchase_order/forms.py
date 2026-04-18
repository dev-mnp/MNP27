from __future__ import annotations

"""Forms owned by the purchase_order module."""

from django import forms

from core import models


class PurchaseOrderForm(forms.ModelForm):
    action = forms.ChoiceField(
        required=False,
        choices=[
            ("draft", "Save draft"),
            ("submit", "Submit"),
        ],
        initial="draft",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.is_bound:
            comments_value = ""
            if getattr(self.instance, "pk", None):
                comments_value = str(self.instance.comments or "").strip()
            if not comments_value:
                self.initial["comments"] = models.PURCHASE_ORDER_DEFAULT_COMMENTS
                self.fields["comments"].initial = models.PURCHASE_ORDER_DEFAULT_COMMENTS

    class Meta:
        model = models.PurchaseOrder
        fields = [
            "vendor_name",
            "gst_number",
            "vendor_address",
            "vendor_city",
            "vendor_state",
            "vendor_pincode",
            "comments",
        ]
        widgets = {
            "vendor_name": forms.TextInput(attrs={"class": "input"}),
            "gst_number": forms.TextInput(attrs={"class": "input"}),
            "vendor_address": forms.Textarea(attrs={"class": "textarea", "rows": 3}),
            "vendor_city": forms.TextInput(attrs={"class": "input"}),
            "vendor_state": forms.TextInput(attrs={"class": "input"}),
            "vendor_pincode": forms.TextInput(attrs={"class": "input"}),
            "comments": forms.Textarea(attrs={"class": "textarea", "rows": 4, "placeholder": "Comments or special instructions"}),
        }


class PurchaseOrderItemForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["article"].required = False
        article_choices = [("", "Select article")]
        if getattr(self.instance, "article_name", None):
            article_choices.append((self.instance.article_name, self.instance.article_name))
        self.fields["article_name"].choices = article_choices

    class Meta:
        model = models.PurchaseOrderItem
        fields = [
            "article",
            "article_name",
            "supplier_article_name",
            "description",
            "quantity",
            "unit_price",
            "total_value",
        ]
        widgets = {
            "article": forms.HiddenInput(),
            "article_name": forms.Select(attrs={"class": "input js-po-article-select"}),
            "supplier_article_name": forms.TextInput(attrs={"class": "input", "placeholder": "Supplier article name"}),
            "description": forms.TextInput(attrs={"class": "input", "placeholder": "Description"}),
            "quantity": forms.NumberInput(attrs={"class": "input", "min": "0"}),
            "unit_price": forms.NumberInput(attrs={"class": "input", "step": "0.01", "min": "0"}),
            "total_value": forms.NumberInput(attrs={"class": "input", "step": "0.01", "readonly": "readonly"}),
        }

    def clean(self):
        cleaned = super().clean()
        article = cleaned.get("article")
        if article and not cleaned.get("article_name"):
            cleaned["article_name"] = article.article_name
        quantity = cleaned.get("quantity") or 0
        unit_price = cleaned.get("unit_price") or 0
        cleaned["total_value"] = unit_price * quantity
        return cleaned
