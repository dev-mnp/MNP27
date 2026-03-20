from __future__ import annotations

import csv
from decimal import Decimal, InvalidOperation

from django.core.management.base import BaseCommand, CommandError

from core import models


class Command(BaseCommand):
    help = "Import district Budget data from CSV."

    def add_arguments(self, parser):
        parser.add_argument("--file", required=True, help="Absolute path to district CSV file")

    def handle(self, *args, **options):
        file_path = options["file"]
        inserted = 0
        updated = 0

        try:
            with open(file_path, newline="", encoding="utf-8-sig") as csvfile:
                reader = csv.DictReader(csvfile)
                for row in reader:
                    district_name = (row.get("district_name") or "").strip()
                    if not district_name:
                        continue

                    allotted_budget_raw = (row.get("allotted_budget") or "0").strip().replace(",", "")
                    try:
                        allotted_budget = Decimal(allotted_budget_raw or "0")
                    except InvalidOperation as exc:
                        raise CommandError(f"Invalid allotted_budget for district '{district_name}': {allotted_budget_raw}") from exc

                    defaults = {
                        "application_number": (row.get("application_number") or "").strip(),
                        "allotted_budget": allotted_budget,
                        "president_name": (row.get("president_name") or "").strip(),
                        "mobile_number": (row.get("mobile_number") or "").strip(),
                        "is_active": True,
                    }

                    obj, created = models.DistrictMaster.objects.update_or_create(
                        district_name=district_name,
                        defaults=defaults,
                    )
                    inserted += int(created)
                    updated += int(not created)
        except FileNotFoundError as exc:
            raise CommandError(f"File not found: {file_path}") from exc

        self.stdout.write(self.style.SUCCESS(f"District import complete. inserted={inserted}, updated={updated}"))
