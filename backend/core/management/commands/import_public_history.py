from __future__ import annotations

import csv

from django.core.management.base import BaseCommand, CommandError

from core import models


class Command(BaseCommand):
    help = "Import past public/district beneficiary history from CSV."

    def add_arguments(self, parser):
        parser.add_argument("--file", required=True, help="Absolute path to history CSV file")
        parser.add_argument(
            "--replace",
            action="store_true",
            help="Delete existing history rows before importing",
        )

    def handle(self, *args, **options):
        file_path = options["file"]
        inserted = 0

        try:
            with open(file_path, newline="", encoding="utf-8-sig") as csvfile:
                reader = csv.DictReader(csvfile)

                if options["replace"]:
                    models.PublicBeneficiaryHistory.objects.all().delete()

                for row in reader:
                    year_raw = (row.get("year") or "").strip()
                    if not year_raw:
                        continue

                    models.PublicBeneficiaryHistory.objects.create(
                        aadhar_number=(row.get("aadhar_number") or "").strip(),
                        name=(row.get("name") or "").strip(),
                        year=int(year_raw),
                        article_name=(row.get("article_name") or "").strip() or None,
                        application_number=(row.get("application_number") or "").strip() or None,
                        comments=(row.get("comments") or "").strip() or None,
                        is_handicapped=_parse_bool(row.get("is_handicapped")),
                        address=(row.get("address") or "").strip() or None,
                        mobile=(row.get("mobile") or "").strip() or None,
                        aadhar_number_sp=(row.get("aadhar_number_sp") or "").strip() or None,
                        is_selected=_parse_bool(row.get("is_selected")),
                        category=(row.get("category") or "").strip() or None,
                    )
                    inserted += 1
        except FileNotFoundError as exc:
            raise CommandError(f"File not found: {file_path}") from exc

        self.stdout.write(self.style.SUCCESS(f"Public history import complete. inserted={inserted}"))


def _parse_bool(value):
    text = str(value or "").strip().lower()
    if text in {"true", "1", "yes"}:
        return True
    if text in {"false", "0", "no"}:
        return False
    return None
