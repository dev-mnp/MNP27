from __future__ import annotations

import csv
from decimal import Decimal, InvalidOperation

from django.core.management.base import BaseCommand, CommandError

from core import models


class Command(BaseCommand):
    help = "Import article price list data from CSV."

    def add_arguments(self, parser):
        parser.add_argument("--file", required=True, help="Absolute path to article CSV file")

    def handle(self, *args, **options):
        file_path = options["file"]
        inserted = 0
        updated = 0

        try:
            with open(file_path, newline="", encoding="utf-8-sig") as csvfile:
                reader = csv.DictReader(csvfile)
                for row in reader:
                    article_name = (row.get("article_name") or "").strip()
                    if not article_name:
                        continue

                    cost_raw = (row.get("cost_per_unit") or "0").strip().replace(",", "")
                    try:
                        cost_per_unit = Decimal(cost_raw or "0")
                    except InvalidOperation as exc:
                        raise CommandError(f"Invalid cost_per_unit for article '{article_name}': {cost_raw}") from exc

                    item_type = (row.get("item_type") or models.ItemTypeChoices.ARTICLE).strip()
                    valid_item_types = {choice for choice, _ in models.ItemTypeChoices.choices}
                    if item_type not in valid_item_types:
                        item_type = models.ItemTypeChoices.ARTICLE

                    is_active_value = (row.get("is_active") or "").strip().lower()
                    is_active = is_active_value in {"active", "true", "1", "yes"}

                    defaults = {
                        "cost_per_unit": cost_per_unit,
                        "item_type": item_type,
                        "category": (row.get("category") or "").strip() or None,
                        "master_category": (row.get("master_category") or "").strip() or None,
                        "is_active": is_active,
                    }

                    obj, created = models.Article.objects.update_or_create(
                        article_name=article_name,
                        defaults=defaults,
                    )
                    inserted += int(created)
                    updated += int(not created)
        except FileNotFoundError as exc:
            raise CommandError(f"File not found: {file_path}") from exc

        self.stdout.write(self.style.SUCCESS(f"Article import complete. inserted={inserted}, updated={updated}"))
