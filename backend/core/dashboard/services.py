from __future__ import annotations

"""Dashboard business metrics service used by the dashboard module views."""

from decimal import Decimal

from django.conf import settings
from django.core.cache import cache
from django.db import connection
from django.db.models import (
    Case,
    Count,
    DecimalField,
    ExpressionWrapper,
    F,
    IntegerField,
    Q,
    Sum,
    Value,
    When,
)
from django.db.models.functions import Coalesce

from core import models


DECIMAL_ZERO = Decimal("0.00")
DASHBOARD_METRICS_CACHE_KEY = "dashboard:metrics:v2"
DASHBOARD_METRICS_CACHE_SECONDS = 45

DISABILITY_COLOR_MAP = [
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


def _signed_currency_text(value) -> dict[str, Decimal | str]:
    amount = Decimal(str(value or 0))
    sign = "+" if amount >= 0 else "-"
    return {"sign": sign, "amount": abs(amount)}


def _decimal_sum(field_name: str):
    return Coalesce(
        Sum(field_name),
        Value(DECIMAL_ZERO),
        output_field=DecimalField(max_digits=18, decimal_places=2),
    )


def _active_beneficiary_filter(prefix: str = "") -> Q:
    field_name = f"{prefix}status" if prefix else "status"
    return ~Q(**{field_name: models.BeneficiaryStatusChoices.ARCHIVED})


def build_dashboard_metrics() -> dict:
    """
    Performance-focused dashboard builder:
    - keeps business formulas unchanged
    - batches per-domain aggregates
    - returns cached payload for warm requests
    """
    cached = cache.get(DASHBOARD_METRICS_CACHE_KEY)
    if cached is not None:
        return cached

    active_filter = _active_beneficiary_filter()
    district_related_active = _active_beneficiary_filter("beneficiaries__")

    # 1) District allocation + utilization + under/over/net in one annotated aggregate query.
    utilized_expr = Coalesce(
        Sum(
            "beneficiaries__total_amount",
            filter=Q(beneficiaries__isnull=False) & district_related_active,
        ),
        Value(DECIMAL_ZERO),
        output_field=DecimalField(max_digits=18, decimal_places=2),
    )
    district_qs = (
        models.DistrictMaster.objects.filter(is_active=True)
        .annotate(utilized_amount=utilized_expr)
        .annotate(
            under_amount=Case(
                When(
                    allotted_budget__gt=F("utilized_amount"),
                    then=ExpressionWrapper(
                        F("allotted_budget") - F("utilized_amount"),
                        output_field=DecimalField(max_digits=18, decimal_places=2),
                    ),
                ),
                default=Value(DECIMAL_ZERO),
                output_field=DecimalField(max_digits=18, decimal_places=2),
            ),
            over_amount=Case(
                When(
                    utilized_amount__gt=F("allotted_budget"),
                    then=ExpressionWrapper(
                        F("utilized_amount") - F("allotted_budget"),
                        output_field=DecimalField(max_digits=18, decimal_places=2),
                    ),
                ),
                default=Value(DECIMAL_ZERO),
                output_field=DecimalField(max_digits=18, decimal_places=2),
            ),
        )
    )
    district_summary = district_qs.aggregate(
        total_allocated=_decimal_sum("allotted_budget"),
        underutilized_total=_decimal_sum("under_amount"),
        overutilized_total=_decimal_sum("over_amount"),
        district_count=Count("id", distinct=True),
        districts_received=Coalesce(
            Sum(
                Case(
                    When(utilized_amount__gt=0, then=Value(1)),
                    default=Value(0),
                    output_field=IntegerField(),
                )
            ),
            Value(0),
            output_field=IntegerField(),
        ),
        underutilized_count=Coalesce(
            Sum(
                Case(
                    When(under_amount__gt=0, then=Value(1)),
                    default=Value(0),
                    output_field=IntegerField(),
                )
            ),
            Value(0),
            output_field=IntegerField(),
        ),
        overutilized_count=Coalesce(
            Sum(
                Case(
                    When(over_amount__gt=0, then=Value(1)),
                    default=Value(0),
                    output_field=IntegerField(),
                )
            ),
            Value(0),
            output_field=IntegerField(),
        ),
    )
    # 2) Pending district names list (separate because we need ordered names payload).
    pending_districts = list(
        district_qs.filter(utilized_amount=0)
        .order_by("district_name")
        .values_list("district_name", flat=True)
    )

    # 3) District beneficiary rollup in one query.
    district_rollup = models.DistrictBeneficiaryEntry.objects.filter(active_filter).aggregate(
        total_beneficiaries=Count("id"),
        total_articles_qty=Coalesce(Sum("quantity"), Value(0), output_field=IntegerField()),
        unique_articles=Count("article", distinct=True),
        total_value_accrued=_decimal_sum("total_amount"),
    )

    public_qs = models.PublicBeneficiaryEntry.objects.active()
    # 4) Public main + gender + disability counts in one query.
    public_rollup = public_qs.aggregate(
        total_beneficiaries=Count("id"),
        total_articles_qty=Coalesce(Sum("quantity"), Value(0), output_field=IntegerField()),
        unique_articles=Count("article", distinct=True),
        total_value_accrued=_decimal_sum("total_amount"),
        male_count=Count("id", filter=Q(gender="Male")),
        female_count=Count("id", filter=Q(gender="Female")),
        transgender_count=Count("id", filter=Q(gender="Transgender")),
        handicapped_total=Count(
            "id",
            filter=~Q(is_handicapped__isnull=True)
            & ~Q(is_handicapped="")
            & ~Q(is_handicapped=models.HandicappedStatusChoices.NO),
        ),
        **{
            f"disability_{index}": Count("id", filter=Q(is_handicapped=label))
            for index, (label, _color) in enumerate(DISABILITY_COLOR_MAP)
        },
    )
    # 5) Female status grouped query (kept separate to preserve dynamic "extra" statuses).
    female_status_counts = {
        item["female_status"]: item["total"]
        for item in public_qs.exclude(female_status__isnull=True).exclude(female_status="").values("female_status").annotate(
            total=Count("id")
        )
    }

    # 6) Institution rollup in one query.
    institution_rollup = models.InstitutionsBeneficiaryEntry.objects.filter(active_filter).aggregate(
        total_beneficiaries=Count("id"),
        application_count=Count(
            "application_number",
            distinct=True,
            filter=Q(application_number__isnull=False) & ~Q(application_number=""),
        ),
        total_articles_qty=Coalesce(Sum("quantity"), Value(0), output_field=IntegerField()),
        unique_articles=Count("article", distinct=True),
        total_value_accrued=_decimal_sum("total_amount"),
    )

    # 7) One query for overall unique-article distinct count.
    overall_unique_articles = models.Article.objects.filter(
        (Q(district_entries__isnull=False) & _active_beneficiary_filter("district_entries__"))
        | (Q(public_entries__isnull=False) & _active_beneficiary_filter("public_entries__"))
        | (Q(institution_entries__isnull=False) & _active_beneficiary_filter("institution_entries__"))
    ).distinct().count()

    # 8) Fund request summary in one query.
    fund_request_rollup = models.FundRequest.objects.aggregate(
        count=Count("id"),
        total_value=_decimal_sum("total_amount"),
    )

    district_total = Decimal(str(district_rollup["total_value_accrued"] or 0))
    public_total = Decimal(str(public_rollup["total_value_accrued"] or 0))
    institution_total = Decimal(str(institution_rollup["total_value_accrued"] or 0))
    total_accrued = district_total + public_total + institution_total
    district_contribution = Decimal(str(district_summary["overutilized_total"] or 0))
    planning_total = total_accrued - district_contribution

    preferred_female_order = ["Single", "Married", "Widowed", "Single Mother"]
    female_status_lines = [
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
        for label in preferred_female_order
    ]
    for label, value in female_status_counts.items():
        if label not in preferred_female_order:
            female_status_lines.append({"label": label, "value": value, "class_name": ""})

    disability_lines = []
    for index, (label, color) in enumerate(DISABILITY_COLOR_MAP):
        value = int(public_rollup.get(f"disability_{index}", 0) or 0)
        if value:
            disability_lines.append({"label": label, "value": value, "color": color})
    disability_lines.append(
        {
            "label": "No",
            "value": max(int(public_rollup["total_beneficiaries"] or 0) - int(public_rollup["handicapped_total"] or 0), 0),
            "color": "#cbd5e1",
        }
    )

    payload = {
        "district": {
            "districts_received": int(district_summary["districts_received"] or 0),
            "districts_pending": max(
                int(district_summary["district_count"] or 0) - int(district_summary["districts_received"] or 0),
                0,
            ),
            "total_articles_qty": int(district_rollup["total_articles_qty"] or 0),
            "unique_articles": int(district_rollup["unique_articles"] or 0),
            "total_beneficiaries": int(district_rollup["total_beneficiaries"] or 0),
            "total_allotted_fund": Decimal(str(district_summary["total_allocated"] or 0)),
            "total_value_accrued": district_total,
            "under_utilized_district_count": int(district_summary["underutilized_count"] or 0),
            "under_utilized_value": Decimal(str(district_summary["underutilized_total"] or 0)),
            "over_utilized_district_count": int(district_summary["overutilized_count"] or 0),
            "over_utilized_value": district_contribution,
            "net_variance": Decimal(str(district_summary["overutilized_total"] or 0))
            - Decimal(str(district_summary["underutilized_total"] or 0)),
            "net_variance_signed": _signed_currency_text(
                Decimal(str(district_summary["overutilized_total"] or 0))
                - Decimal(str(district_summary["underutilized_total"] or 0))
            ),
        },
        "public": {
            "total_beneficiaries": int(public_rollup["total_beneficiaries"] or 0),
            "total_articles_qty": int(public_rollup["total_articles_qty"] or 0),
            "unique_articles": int(public_rollup["unique_articles"] or 0),
            "total_value_accrued": public_total,
            "gender_lines": [
                {"label": "Male", "value": int(public_rollup["male_count"] or 0), "class_name": "gender-male"},
                {"label": "Female", "value": int(public_rollup["female_count"] or 0), "class_name": "gender-female"},
                {"label": "Transgender", "value": int(public_rollup["transgender_count"] or 0), "class_name": "gender-transgender"},
            ],
            "female_status_lines": female_status_lines,
            "handicapped": int(public_rollup["handicapped_total"] or 0),
            "handicapped_lines": disability_lines,
        },
        "institutions": {
            "total_beneficiaries": int(institution_rollup["total_beneficiaries"] or 0),
            "application_count": int(institution_rollup["application_count"] or 0),
            "total_articles_qty": int(institution_rollup["total_articles_qty"] or 0),
            "unique_articles": int(institution_rollup["unique_articles"] or 0),
            "total_value_accrued": institution_total,
        },
        "overall": {
            "total_beneficiaries": (
                int(district_rollup["total_articles_qty"] or 0)
                + int(public_rollup["total_articles_qty"] or 0)
                + int(institution_rollup["application_count"] or 0)
            ),
            "total_articles_qty": (
                int(district_rollup["total_articles_qty"] or 0)
                + int(public_rollup["total_articles_qty"] or 0)
                + int(institution_rollup["total_articles_qty"] or 0)
            ),
            "unique_articles": overall_unique_articles,
            "total_value_accrued": planning_total,
            "actual_total_value_accrued": total_accrued,
            "district_variance": district_contribution,
            "district_variance_signed": _signed_currency_text(district_contribution),
            "district_contribution_signed": _signed_currency_text(district_contribution),
        },
        "fund_requests": {
            "count": int(fund_request_rollup["count"] or 0),
            "total_value": Decimal(str(fund_request_rollup["total_value"] or 0)),
        },
        "total_districts": int(district_summary["district_count"] or 0),
        "pending_districts": pending_districts,
    }

    # Temporary debug counter requested for optimization measurement.
    if settings.DEBUG:
        print(f"[Dashboard] query_count={len(connection.queries)}")

    cache.set(DASHBOARD_METRICS_CACHE_KEY, payload, DASHBOARD_METRICS_CACHE_SECONDS)
    return payload
