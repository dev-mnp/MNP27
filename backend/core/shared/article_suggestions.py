from __future__ import annotations

"""Shared helpers for normalized article category/super-category suggestions."""

from core import models


def get_article_text_suggestions(field_name: str) -> list[str]:
    """Return trimmed, unique, case-insensitive suggestions for an Article text field."""
    raw_values = models.Article.objects.order_by(field_name).values_list(field_name, flat=True)
    seen = set()
    suggestions: list[str] = []
    for value in raw_values:
        cleaned = (value or "").strip()
        if not cleaned:
            continue
        key = cleaned.casefold()
        if key in seen:
            continue
        seen.add(key)
        suggestions.append(cleaned)
    return sorted(suggestions, key=lambda item: item.casefold())

