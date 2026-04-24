from __future__ import annotations

"""Forms owned by the article_management module."""

from django import forms

from core import models


class ArticleForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields["article_name"].widget.attrs.pop("autofocus", None)
        self.fields["category"].widget.attrs["list"] = "article-category-options"
        self.fields["master_category"].widget.attrs["list"] = "article-master-category-options"
        self.fields["article_name"].widget.attrs["autocomplete"] = "off"
        self.fields["article_name_tk"].widget.attrs["autocomplete"] = "off"
        self.fields["article_name"].required = True
        self.fields["article_name_tk"].required = True
        self.fields["cost_per_unit"].required = True
        self.fields["item_type"].required = True
        self.fields["category"].required = True
        self.fields["master_category"].required = True
        self.fields["item_type"].choices = [
            (models.ItemTypeChoices.AID, models.ItemTypeChoices.AID.label),
            (models.ItemTypeChoices.ARTICLE, models.ItemTypeChoices.ARTICLE.label),
            (models.ItemTypeChoices.PROJECT, models.ItemTypeChoices.PROJECT.label),
        ]

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
            "category": forms.TextInput(attrs={"class": "input", "list": "article-category-options"}),
            "master_category": forms.TextInput(attrs={"class": "input", "list": "article-master-category-options"}),
        }

    def clean_article_name(self):
        article_name = (self.cleaned_data.get("article_name") or "").strip()
        if not article_name:
            return article_name
        queryset = models.Article.objects.filter(article_name__iexact=article_name)
        if self.instance and self.instance.pk:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise forms.ValidationError("An article with this name already exists.")
        return article_name

    def clean_article_name_tk(self):
        article_name_tk = (self.cleaned_data.get("article_name_tk") or "").strip()
        if not article_name_tk:
            return article_name_tk
        queryset = models.Article.objects.filter(article_name_tk__iexact=article_name_tk)
        if self.instance and self.instance.pk:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise forms.ValidationError("An article with this token name already exists.")
        return article_name_tk

    def clean_category(self):
        return (self.cleaned_data.get("category") or "").strip()

    def clean_master_category(self):
        return (self.cleaned_data.get("master_category") or "").strip()
