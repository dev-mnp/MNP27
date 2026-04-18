from __future__ import annotations

"""Dashboard business metrics service used by the dashboard module views."""

from decimal import Decimal

from core import models


def _zero() -> Decimal:
    return Decimal("0")


def _signed_currency_text(value) -> dict[str, Decimal | str]:
    amount = Decimal(str(value or 0))
    sign = "+" if amount >= 0 else "-"
    return {"sign": sign, "amount": abs(amount)}


def build_dashboard_metrics() -> dict:
    """
    Build the dashboard metric payload exactly as the legacy dashboard expected.

    This function intentionally preserves existing field names and calculations.
    """
    zero = _zero()
    district_entries = list(
        models.DistrictBeneficiaryEntry.objects.select_related("district", "article").all()
    )
    public_entries = list(
        models.PublicBeneficiaryEntry.objects.active().select_related("article").all()
    )
    institution_entries = list(
        models.InstitutionsBeneficiaryEntry.objects.select_related("article").all()
    )
    districts = list(models.DistrictMaster.objects.filter(is_active=True).order_by("district_name"))
    fund_requests = list(models.FundRequest.objects.all())

    district_article_ids = set()
    district_ids = set()
    district_articles_qty = 0
    district_value_accrued = zero
    district_spend_map = {}
    for entry in district_entries:
        if entry.article_id:
            district_article_ids.add(entry.article_id)
        if entry.district_id:
            district_ids.add(entry.district_id)
            district_spend_map[entry.district_id] = district_spend_map.get(entry.district_id, zero) + Decimal(
                str(entry.total_amount or 0)
            )
        district_articles_qty += int(entry.quantity or 0)
        district_value_accrued += Decimal(str(entry.total_amount or 0))

    public_article_ids = set()
    public_articles_qty = 0
    public_value_accrued = zero
    gender_counts = {"Male": 0, "Female": 0, "Transgender": 0}
    female_status_counts = {}
    handicapped = 0
    disability_category_counts = {}
    for entry in public_entries:
        if entry.article_id:
            public_article_ids.add(entry.article_id)
        public_articles_qty += int(entry.quantity or 0)
        public_value_accrued += Decimal(str(entry.total_amount or 0))
        if entry.gender in gender_counts:
            gender_counts[entry.gender] += 1
        if entry.female_status:
            female_status_counts[entry.female_status] = female_status_counts.get(entry.female_status, 0) + 1
        if entry.is_handicapped and entry.is_handicapped != models.HandicappedStatusChoices.NO:
            handicapped += 1
            disability_category_counts[entry.is_handicapped] = disability_category_counts.get(entry.is_handicapped, 0) + 1

    institution_article_ids = set()
    institution_applications = set()
    institution_articles_qty = 0
    institution_value_accrued = zero
    for entry in institution_entries:
        if entry.article_id:
            institution_article_ids.add(entry.article_id)
        if entry.application_number:
            institution_applications.add(entry.application_number)
        institution_articles_qty += int(entry.quantity or 0)
        institution_value_accrued += Decimal(str(entry.total_amount or 0))

    overall_article_ids = district_article_ids | public_article_ids | institution_article_ids
    overall_articles_qty = district_articles_qty + public_articles_qty + institution_articles_qty
    total_allotted_fund = sum((Decimal(str(d.allotted_budget or 0)) for d in districts), zero)
    received_district_allotted_fund = sum(
        (Decimal(str(d.allotted_budget or 0)) for d in districts if d.id in district_ids),
        zero,
    )
    district_variance = district_value_accrued - received_district_allotted_fund
    overall_actual_value_accrued = district_value_accrued + public_value_accrued + institution_value_accrued
    overall_planning_value_accrued = received_district_allotted_fund + public_value_accrued + institution_value_accrued
    overall_beneficiaries = district_articles_qty + public_articles_qty + len(institution_applications)

    fund_request_total_value = sum((Decimal(str(f.total_amount or 0)) for f in fund_requests), zero)

    pending_districts = [
        district.district_name
        for district in districts
        if district.id and district.id not in district_ids and district.district_name
    ]

    under_utilized_district_count = 0
    under_utilized_value = zero
    over_utilized_district_count = 0
    over_utilized_value = zero
    for district in districts:
        if district.id not in district_ids:
            continue
        allotted = Decimal(str(district.allotted_budget or 0))
        used = district_spend_map.get(district.id, zero)
        delta = used - allotted
        if delta > 0:
            over_utilized_district_count += 1
            over_utilized_value += delta
        elif delta < 0:
            under_utilized_district_count += 1
            under_utilized_value += abs(delta)

    preferred_female_order = ["Single", "Married", "Widowed", "Single Mother"]
    female_status_lines = []
    for label in preferred_female_order:
        female_status_lines.append(
            {
                "label": label,
                "value": female_status_counts.get(label, 0),
                "class_name": {
                    "Single": "female-unmarried",
                    "Married": "female-married",
                    "Widowed": "female-widow",
                    "Single Mother": "female-single-mother",
                }.get(label, ""),
            }
        )
    for label, value in female_status_counts.items():
        if label not in preferred_female_order:
            female_status_lines.append({"label": label, "value": value, "class_name": ""})

    return {
        "district": {
            "districts_received": len(district_ids),
            "districts_pending": max(len(districts) - len(district_ids), 0),
            "total_articles_qty": district_articles_qty,
            "unique_articles": len(district_article_ids),
            "total_beneficiaries": len(district_entries),
            "total_allotted_fund": total_allotted_fund,
            "total_value_accrued": district_value_accrued,
            "under_utilized_district_count": under_utilized_district_count,
            "under_utilized_value": under_utilized_value,
            "over_utilized_district_count": over_utilized_district_count,
            "over_utilized_value": over_utilized_value,
            "net_variance": district_variance,
        },
        "public": {
            "total_beneficiaries": len(public_entries),
            "total_articles_qty": public_articles_qty,
            "unique_articles": len(public_article_ids),
            "total_value_accrued": public_value_accrued,
            "gender_lines": [
                {"label": "Male", "value": gender_counts["Male"], "class_name": "gender-male"},
                {"label": "Female", "value": gender_counts["Female"], "class_name": "gender-female"},
                {"label": "Transgender", "value": gender_counts["Transgender"], "class_name": "gender-transgender"},
            ],
            "female_status_lines": female_status_lines,
            "handicapped": handicapped,
            "handicapped_lines": [
                {
                    "label": label,
                    "value": disability_category_counts.get(label, 0),
                    "color": color,
                }
                for label, color in [
                    ("Blindness / Low Vision", "#2563eb"),
                    ("Deaf / Hard of Hearing", "#9333ea"),
                    ("Locomotor Disability", "#ea580c"),
                    ("Cerebral Palsy", "#0f766e"),
                    ("Leprosy Cured", "#ca8a04"),
                    ("Dwarfism", "#db2777"),
                    ("Acid Attack Victim", "#dc2626"),
                    ("Muscular Dystrophy", "#16a34a"),
                    ("Autism Spectrum Disorder", "#4f46e5"),
                    ("Intellectual Disability", "#0891b2"),
                    ("Specific Learning Disability", "#65a30d"),
                    ("Mental Illness", "#d97706"),
                    ("Multiple Disability", "#7c3aed"),
                    ("Deaf-Blindness", "#334155"),
                    ("Other", "#64748b"),
                ]
                if disability_category_counts.get(label, 0)
            ]
            + [
                {"label": "No", "value": max(len(public_entries) - handicapped, 0), "color": "#cbd5e1"}
            ],
        },
        "institutions": {
            "total_beneficiaries": len(institution_entries),
            "application_count": len(institution_applications),
            "total_articles_qty": institution_articles_qty,
            "unique_articles": len(institution_article_ids),
            "total_value_accrued": institution_value_accrued,
        },
        "overall": {
            "total_beneficiaries": overall_beneficiaries,
            "total_articles_qty": overall_articles_qty,
            "unique_articles": len(overall_article_ids),
            "total_value_accrued": overall_planning_value_accrued,
            "actual_total_value_accrued": overall_actual_value_accrued,
            "district_variance": district_variance,
            "district_variance_signed": _signed_currency_text(district_variance),
            "district_contribution_signed": _signed_currency_text(-district_variance),
        },
        "fund_requests": {
            "count": len(fund_requests),
            "total_value": fund_request_total_value,
        },
        "total_districts": len(districts),
        "pending_districts": pending_districts,
    }
