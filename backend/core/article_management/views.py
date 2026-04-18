from __future__ import annotations

"""Views for article listing, create/edit, and delete workflows."""

import csv
import json

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.cache import cache
from django.db.models import Q
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from core import models
from core.article_management.forms import ArticleForm
from core.shared.permissions import AdminRequiredMixin, RoleRequiredMixin, WriteRoleMixin
from core.shared.article_suggestions import get_article_text_suggestions


class ArticleListView(LoginRequiredMixin, RoleRequiredMixin, ListView):
    module_key = models.ModuleKeyChoices.ARTICLE_MANAGEMENT
    permission_action = "view"
    model = models.Article
    template_name = "article_management/article_list.html"
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
        category_choices = cache.get("mnp27:article:category_choices")
        if category_choices is None:
            category_choices = get_article_text_suggestions("category")
            cache.set("mnp27:article:category_choices", category_choices, timeout=300)

        master_category_choices = cache.get("mnp27:article:master_category_choices")
        if master_category_choices is None:
            master_category_choices = get_article_text_suggestions("master_category")
            cache.set("mnp27:article:master_category_choices", master_category_choices, timeout=300)
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
    template_name = "article_management/article_form.html"
    success_url = reverse_lazy("ui:article-list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["popup_mode"] = self.request.GET.get("popup") == "1"
        context["category_suggestions"] = get_article_text_suggestions("category")
        context["master_category_suggestions"] = get_article_text_suggestions("master_category")
        return context

    def form_valid(self, form):
        self.object = form.save()
        if self.request.GET.get("popup") == "1" and self.request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse(
                {
                    "ok": True,
                    "article": {
                        "id": self.object.id,
                        "article_name": self.object.article_name,
                        "cost_per_unit": str(self.object.cost_per_unit),
                        "item_type": self.object.item_type,
                    },
                }
            )
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

    def form_invalid(self, form):
        if self.request.GET.get("popup") == "1" and self.request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({"ok": False, "errors": form.errors}, status=400)
        return super().form_invalid(form)


class ArticleUpdateView(LoginRequiredMixin, WriteRoleMixin, UpdateView):
    module_key = models.ModuleKeyChoices.ARTICLE_MANAGEMENT
    permission_action = "create_edit"
    model = models.Article
    form_class = ArticleForm
    template_name = "article_management/article_form.html"
    success_url = reverse_lazy("ui:article-list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["popup_mode"] = False
        context["category_suggestions"] = get_article_text_suggestions("category")
        context["master_category_suggestions"] = get_article_text_suggestions("master_category")
        return context

    def form_valid(self, form):
        messages.success(self.request, "Article updated.")
        return super().form_valid(form)


class ArticleDeleteView(LoginRequiredMixin, AdminRequiredMixin, DeleteView):
    module_key = models.ModuleKeyChoices.ARTICLE_MANAGEMENT
    permission_action = "delete"
    model = models.Article
    template_name = "article_management/article_confirm_delete.html"
    success_url = reverse_lazy("ui:article-list")

    def post(self, request, *args, **kwargs):
        messages.warning(self.request, "Article deleted.")
        return super().post(request, *args, **kwargs)
