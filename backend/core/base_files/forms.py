from __future__ import annotations

"""Forms owned by the base_files module."""

from django import forms


class MasterDataUploadForm(forms.Form):
    file = forms.FileField(required=True, widget=forms.ClearableFileInput(attrs={"class": "input"}))
    replace_existing = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={"style": "width: auto; margin-right: 8px;"}),
        help_text="For past history only: clear the old imported rows before loading the new file.",
    )
