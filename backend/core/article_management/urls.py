from __future__ import annotations

"""URL routes for the article management business module."""

from django.urls import path

from .views import ArticleCreateView, ArticleDeleteView, ArticleListView, ArticleUpdateView

urlpatterns = [
    path("articles/", ArticleListView.as_view(), name="article-list"),
    path("articles/new/", ArticleCreateView.as_view(), name="article-create"),
    path("articles/<int:pk>/edit/", ArticleUpdateView.as_view(), name="article-edit"),
    path("articles/<int:pk>/delete/", ArticleDeleteView.as_view(), name="article-delete"),
]

