"""Service functions for base_files numbering utilities."""

from core import models


def next_public_application_number() -> str:
    prefix = "P"
    latest = (
        models.PublicBeneficiaryEntry.objects.filter(application_number__startswith=prefix)
        .order_by("-application_number")
        .values_list("application_number", flat=True)
        .first()
    )
    if not latest:
        return f"{prefix}001"
    try:
        seq = int(str(latest).replace(prefix, "", 1)) + 1
    except (TypeError, ValueError):
        seq = 1
    return f"{prefix}{seq:03d}"


def next_institution_application_number() -> str:
    prefix = "I"
    latest = (
        models.InstitutionsBeneficiaryEntry.objects.filter(application_number__startswith=prefix)
        .order_by("-application_number")
        .values_list("application_number", flat=True)
        .first()
    )
    if not latest:
        return f"{prefix}001"
    try:
        seq = int(str(latest).replace(prefix, "", 1)) + 1
    except (TypeError, ValueError):
        seq = 1
    return f"{prefix}{seq:03d}"


def next_others_application_number() -> str:
    prefix = "O"
    latest = (
        models.InstitutionsBeneficiaryEntry.objects.filter(
            application_number__startswith=prefix,
            institution_type=models.InstitutionTypeChoices.OTHERS,
        )
        .order_by("-application_number")
        .values_list("application_number", flat=True)
        .first()
    )
    if not latest:
        return f"{prefix}001"
    try:
        seq = int(str(latest).replace(prefix, "", 1)) + 1
    except (TypeError, ValueError):
        seq = 1
    return f"{prefix}{seq:03d}"
