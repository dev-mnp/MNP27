from __future__ import annotations

"""Post-migrate bootstrap for a guaranteed admin/superuser account."""

import logging
import os

from django.apps import apps as global_apps
from django.contrib.auth.hashers import make_password
from django.db import transaction
from django.db.models.signals import post_migrate


logger = logging.getLogger(__name__)


def _env(name: str) -> str:
    return (os.getenv(name) or "").strip()


def _parse_name(full_name: str) -> tuple[str, str]:
    cleaned = " ".join((full_name or "").strip().split())
    if not cleaned:
        return "", ""
    parts = cleaned.split(" ", 1)
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], parts[1]


def _bootstrap_admin_impl(*, apps_registry) -> None:
    email = _env("DJANGO_SUPERUSER_EMAIL")
    password = _env("DJANGO_SUPERUSER_PASSWORD")
    if not email or not password:
        logger.warning(
            "Bootstrap admin skipped: set DJANGO_SUPERUSER_EMAIL and DJANGO_SUPERUSER_PASSWORD."
        )
        return

    try:
        UserModel = apps_registry.get_model("core", "AppUser")
    except LookupError:
        # Can happen when post_migrate fires for app subsets / historical states.
        logger.debug("Bootstrap admin skipped: core.AppUser unavailable in current app registry.")
        return
    role_admin_value = "admin"

    display_name = _env("DJANGO_SUPERUSER_NAME") or _env("DJANGO_SUPERUSER_USERNAME")
    first_name, last_name = _parse_name(display_name)
    normalized_email = UserModel.objects.normalize_email(email)

    with transaction.atomic():
        user = UserModel.objects.filter(email__iexact=normalized_email).order_by("id").first()
        if user is None:
            user = UserModel.objects.create(
                email=normalized_email,
                is_staff=True,
                is_superuser=True,
                is_active=True,
                status="active",
                role=role_admin_value,
                first_name=first_name,
                last_name=last_name,
                password=make_password(password),
            )
            logger.info("Bootstrap admin created: %s", normalized_email)
            return

        update_fields: list[str] = []
        if user.email != normalized_email:
            user.email = normalized_email
            update_fields.append("email")
        if not user.is_staff:
            user.is_staff = True
            update_fields.append("is_staff")
        if not user.is_superuser:
            user.is_superuser = True
            update_fields.append("is_superuser")
        if not user.is_active:
            user.is_active = True
            update_fields.append("is_active")
        if getattr(user, "status", "") != "active":
            user.status = "active"
            update_fields.append("status")
        if getattr(user, "role", "") != role_admin_value:
            user.role = role_admin_value
            update_fields.append("role")
        if first_name and user.first_name != first_name:
            user.first_name = first_name
            update_fields.append("first_name")
        if display_name and user.last_name != last_name:
            user.last_name = last_name
            update_fields.append("last_name")
        if hasattr(user, "check_password"):
            if not user.check_password(password):
                user.password = make_password(password)
                update_fields.append("password")
        elif hasattr(user, "password"):
            # Historical migration states may not expose auth helper methods.
            user.password = make_password(password)
            update_fields.append("password")
        if update_fields:
            user.save(update_fields=sorted(set(update_fields)))
            logger.info("Bootstrap admin updated: %s (%s)", normalized_email, ", ".join(sorted(set(update_fields))))


def bootstrap_admin_post_migrate(sender, app_config=None, apps=None, **kwargs):
    label = getattr(sender, "label", "") or getattr(app_config, "label", "")
    if label != "core":
        return
    _bootstrap_admin_impl(apps_registry=apps or global_apps)


def register_bootstrap_admin_signal() -> None:
    post_migrate.connect(
        bootstrap_admin_post_migrate,
        dispatch_uid="core.bootstrap_admin_post_migrate",
    )
