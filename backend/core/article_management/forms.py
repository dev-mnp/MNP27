from __future__ import annotations

"""Forms owned by the article_management module."""

from django import forms

from core import models


class ArticleForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].widget.attrs["list"] = "article-category-options"
        self.fields["master_category"].widget.attrs["list"] = "article-master-category-options"

    class Meta:
        model = models.Article
        fields = [
            "article_name",
            "article_name_tk",
            "cost_per_unit",
            "item_type",
            "category",
            "master_category",
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
        }
