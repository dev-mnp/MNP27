from __future__ import annotations

import csv
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core import models


def _clean(value):
    return (value or "").strip()


def _decimal(value, default="0"):
    raw = _clean(value).replace(",", "")
    if not raw:
        return Decimal(default)
    try:
        return Decimal(raw)
    except (InvalidOperation, ValueError):
        return Decimal(default)


def _int(value, default=0):
    try:
        return int(_decimal(value, str(default)))
    except (InvalidOperation, ValueError, TypeError):
        return default


def _legacy_disability_sample_values():
    excluded = {
        models.HandicappedStatusChoices.NO,
        models.HandicappedStatusChoices.MIXED,
        models.HandicappedStatusChoices.CEREBRAL_PALSY,
        models.HandicappedStatusChoices.LEPROSY_CURED,
        models.HandicappedStatusChoices.DWARFISM,
        models.HandicappedStatusChoices.ACID_ATTACK_VICTIM,
        models.HandicappedStatusChoices.MUSCULAR_DYSTROPHY,
        models.HandicappedStatusChoices.AUTISM_SPECTRUM_DISORDER,
    }
    return [
        value
        for value, _label in models.HandicappedStatusChoices.choices
        if value not in excluded
    ]


class Command(BaseCommand):
    help = "Import district/public/institution application entries from a flat master-entry export CSV."

    def add_arguments(self, parser):
        parser.add_argument("--file", required=True, help="Absolute path to the exported master-entry CSV file")
        parser.add_argument(
            "--replace",
            action="store_true",
            help="Delete existing district/public/institution application entries before importing",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        file_path = Path(options["file"]).expanduser().resolve()
        if not file_path.exists():
            raise CommandError(f"File does not exist: {file_path}")

        with file_path.open("r", encoding="utf-8-sig", newline="") as csvfile:
            rows = list(csv.DictReader(csvfile))

        if not rows:
            raise CommandError("CSV file is empty.")

        required_headers = {
            "Application Number",
            "Beneficiary Name",
            "Requested Item",
            "Quantity",
            "Cost Per Unit",
            "Total Value",
            "Address",
            "Mobile",
            "Aadhar Number",
            "Handicapped Status",
            "Gender",
            "Gender Category",
            "Beneficiary Type",
            "Item Type",
            "Article Category",
            "Super Category Article",
            "Requested Item Tk",
            "Comments",
        }
        missing = sorted(required_headers - set(rows[0].keys()))
        if missing:
            raise CommandError(f"CSV is missing required columns: {', '.join(missing)}")

        article_payloads = {}
        for row in rows:
            article_name = _clean(row.get("Requested Item"))
            if not article_name:
                continue
            payload = article_payloads.setdefault(
                article_name,
                {
                    "article_name": article_name,
                    "article_name_tk": "",
                    "cost_per_unit": Decimal("0"),
                    "item_type": models.ItemTypeChoices.ARTICLE,
                    "category": "",
                    "master_category": "",
                    "comments": "",
                    "combo": "+" in article_name,
                },
            )
            payload["article_name_tk"] = payload["article_name_tk"] or _clean(row.get("Requested Item Tk"))
            payload["category"] = payload["category"] or _clean(row.get("Article Category"))
            payload["master_category"] = payload["master_category"] or _clean(row.get("Super Category Article"))
            payload["comments"] = payload["comments"] or _clean(row.get("Comments"))
            payload["item_type"] = _clean(row.get("Item Type")) or payload["item_type"]
            row_cost = _decimal(row.get("Cost Per Unit"))
            if row_cost > 0:
                payload["cost_per_unit"] = row_cost

        existing_articles = {article.article_name.strip(): article for article in models.Article.objects.all()}
        created_articles = 0
        updated_articles = 0
        for article_name, payload in article_payloads.items():
            article = existing_articles.get(article_name)
            if article is None:
                article = models.Article(article_name=article_name, is_active=True)
                created_articles += 1
            else:
                updated_articles += 1
            article.article_name_tk = payload["article_name_tk"] or None
            article.cost_per_unit = payload["cost_per_unit"]
            article.item_type = payload["item_type"] or models.ItemTypeChoices.ARTICLE
            article.category = payload["category"] or None
            article.master_category = payload["master_category"] or None
            article.comments = payload["comments"] or None
            article.combo = payload["combo"]
            article.is_active = True
            article.save()
            existing_articles[article_name] = article

        district_map = {district.district_name.strip(): district for district in models.DistrictMaster.objects.all()}
        first_mobile_by_district = defaultdict(str)
        first_app_number_by_district = defaultdict(str)
        for row in rows:
            if _clean(row.get("Beneficiary Type")) != "District":
                continue
            district_name = _clean(row.get("Beneficiary Name"))
            if not district_name:
                continue
            first_mobile_by_district[district_name] = first_mobile_by_district[district_name] or _clean(row.get("Mobile"))
            first_app_number_by_district[district_name] = first_app_number_by_district[district_name] or _clean(row.get("Application Number"))

        created_districts = 0
        for district_name in sorted(first_app_number_by_district.keys()):
            if district_name in district_map:
                continue
            district = models.DistrictMaster.objects.create(
                district_name=district_name,
                allotted_budget=Decimal("0"),
                president_name=district_name,
                mobile_number=first_mobile_by_district.get(district_name) or "-",
                application_number=first_app_number_by_district.get(district_name) or district_name[:20],
                is_active=True,
            )
            district_map[district_name] = district
            created_districts += 1

        if options["replace"]:
            models.DistrictBeneficiaryEntry.objects.all().delete()
            models.PublicBeneficiaryEntry.objects.all().delete()
            models.InstitutionsBeneficiaryEntry.objects.all().delete()

        inserted_counts = {
            "district": 0,
            "public": 0,
            "institutions": 0,
        }
        disability_sample_values = _legacy_disability_sample_values()
        disability_sample_index = 0

        for row in rows:
            beneficiary_type = _clean(row.get("Beneficiary Type"))
            application_number = _clean(row.get("Application Number")) or None
            beneficiary_name = _clean(row.get("Beneficiary Name"))
            article_name = _clean(row.get("Requested Item"))
            article = existing_articles.get(article_name)
            if not article:
                continue

            quantity = max(_int(row.get("Quantity"), 1), 0)
            unit_cost = _decimal(row.get("Cost Per Unit"))
            total_value = _decimal(row.get("Total Value"))
            notes = _clean(row.get("Comments")) or None

            if beneficiary_type == "District":
                district = district_map.get(beneficiary_name)
                if district is None:
                    continue
                models.DistrictBeneficiaryEntry.objects.create(
                    district=district,
                    application_number=application_number,
                    article=article,
                    article_cost_per_unit=unit_cost,
                    quantity=quantity,
                    total_amount=total_value,
                    cheque_rtgs_in_favour=None,
                    notes=notes,
                    status=models.BeneficiaryStatusChoices.SUBMITTED,
                )
                inserted_counts["district"] += 1
            elif beneficiary_type == "Public":
                handicapped_status = _clean(row.get("Handicapped Status")) or models.HandicappedStatusChoices.NO
                if handicapped_status.lower() == "yes":
                    handicapped_status = disability_sample_values[disability_sample_index % len(disability_sample_values)]
                    disability_sample_index += 1
                models.PublicBeneficiaryEntry.objects.create(
                    application_number=application_number,
                    name=beneficiary_name or "Unknown",
                    aadhar_number=_clean(row.get("Aadhar Number")),
                    is_handicapped=handicapped_status,
                    gender=_clean(row.get("Gender")) or None,
                    female_status=_clean(row.get("Gender Category")) or None,
                    address=_clean(row.get("Address")) or None,
                    mobile=_clean(row.get("Mobile")) or None,
                    article=article,
                    article_cost_per_unit=unit_cost,
                    quantity=quantity,
                    total_amount=total_value,
                    cheque_rtgs_in_favour=None,
                    notes=notes,
                    status=models.BeneficiaryStatusChoices.SUBMITTED,
                )
                inserted_counts["public"] += 1
            elif beneficiary_type == "Institutions":
                models.InstitutionsBeneficiaryEntry.objects.create(
                    institution_name=beneficiary_name or "Unknown",
                    institution_type=models.InstitutionTypeChoices.INSTITUTIONS,
                    application_number=application_number,
                    address=_clean(row.get("Address")) or None,
                    mobile=_clean(row.get("Mobile")) or None,
                    article=article,
                    article_cost_per_unit=unit_cost,
                    quantity=quantity,
                    total_amount=total_value,
                    cheque_rtgs_in_favour=None,
                    notes=notes,
                    status=models.BeneficiaryStatusChoices.SUBMITTED,
                )
                inserted_counts["institutions"] += 1

        self.stdout.write(
            self.style.SUCCESS(
                "Master-entry import complete. "
                f"articles_created={created_articles}, "
                f"articles_updated={updated_articles}, "
                f"districts_created={created_districts}, "
                f"district_entries={inserted_counts['district']}, "
                f"public_entries={inserted_counts['public']}, "
                f"institution_entries={inserted_counts['institutions']}"
            )
        )
