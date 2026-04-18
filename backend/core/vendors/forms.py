from __future__ import annotations

"""Forms owned by the vendors module."""

from django import forms

from core import models


class VendorForm(forms.ModelForm):
    class Meta:
        model = models.Vendor
        fields = [
            "vendor_name",
            "gst_number",
            "phone_number",
            "address",
            "city",
            "state",
            "pincode",
            "cheque_in_favour",
            "is_active",
        ]
        widgets = {
            "vendor_name": forms.TextInput(attrs={"class": "input", "placeholder": "Vendor name"}),
            "gst_number": forms.TextInput(attrs={"class": "input", "placeholder": "GST number"}),
            "phone_number": forms.TextInput(attrs={"class": "input", "placeholder": "Phone number"}),
            "address": forms.Textarea(attrs={"class": "textarea", "rows": 3, "placeholder": "Address"}),
            "city": forms.TextInput(attrs={"class": "input", "placeholder": "City"}),
            "state": forms.TextInput(attrs={"class": "input", "placeholder": "State"}),
            "pincode": forms.TextInput(attrs={"class": "input", "placeholder": "Pincode"}),
            "cheque_in_favour": forms.TextInput(attrs={"class": "input", "placeholder": "Cheque / RTGS in favour"}),
            "is_active": forms.CheckboxInput(attrs={"class": "input"}),
        }

