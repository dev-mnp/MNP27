from __future__ import annotations

"""Post-migrate bootstrap for a guaranteed admin/superuser account."""

import logging
import json
import os

from django.apps import apps as global_apps
from django.contrib.auth.hashers import make_password
from django.db import transaction
from django.db.models.signals import post_migrate


logger = logging.getLogger(__name__)


MODULE_PERMISSION_ACTIONS = (
    "view",
    "view_page_2",
    "create_edit",
    "delete",
    "submit",
    "reopen",
    "export",
    "upload_replace",
    "reset_password",
)

MODULE_PERMISSION_DEFINITIONS = (
    ("dashboard", ("view", "view_page_2", "create_edit")),
    ("application_entry", ("view", "create_edit", "delete", "submit", "reopen")),
    ("article_management", ("view", "create_edit", "delete")),
    ("base_files", ("view", "upload_replace")),
    ("inventory_planning", ("view", "export")),
    ("seat_allocation", ("view", "create_edit", "export", "upload_replace")),
    ("sequence_list", ("view", "create_edit", "export")),
    ("token_generation", ("view", "create_edit", "export", "upload_replace")),
    ("labels", ("view", "create_edit", "export", "upload_replace")),
    ("reports", ("view", "create_edit", "export", "upload_replace")),
    ("order_fund_request", ("view", "create_edit", "delete", "submit", "reopen")),
    ("purchase_order", ("view", "create_edit", "delete", "submit", "reopen")),
    ("vendors", ("view", "create_edit", "delete", "export")),
    ("audit_logs", ("view",)),
    ("user_management", ("view", "create_edit", "delete", "reset_password")),
    ("user_guide", ("view",)),
)


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


def _normalize_bootstrap_permission_actions(raw_actions, allowed_actions: tuple[str, ...]) -> set[str]:
    if raw_actions is True:
        return set(allowed_actions)
    if raw_actions in (False, None, ""):
        return set()
    if isinstance(raw_actions, dict):
        actions = set()
        for action in allowed_actions:
            if raw_actions.get(action) or raw_actions.get(f"can_{action}"):
                actions.add(action)
        return actions
    if isinstance(raw_actions, str):
        raw_actions = [value.strip() for value in raw_actions.split(",") if value.strip()]
    if not isinstance(raw_actions, (list, tuple, set)):
        return set()
    return {str(action).strip() for action in raw_actions if str(action).strip() in allowed_actions}


def _sync_bootstrap_user_permissions(*, user, permission_payload, PermissionModel) -> None:
    if permission_payload is None:
        permission_payload = {}
    if not isinstance(permission_payload, dict):
        logger.warning("Bootstrap user permissions ignored for %s: permissions must be an object.", user.email)
        permission_payload = {}

    global_actions = permission_payload.get("*")
    existing = {permission.module_key: permission for permission in PermissionModel.objects.filter(user=user)}
    for module_key, allowed_actions in MODULE_PERMISSION_DEFINITIONS:
        raw_actions = permission_payload.get(module_key, global_actions)
        enabled_actions = _normalize_bootstrap_permission_actions(raw_actions, allowed_actions)
        permission = existing.get(module_key) or PermissionModel(user=user, module_key=module_key)
        for action in MODULE_PERMISSION_ACTIONS:
            if hasattr(permission, f"can_{action}"):
                setattr(permission, f"can_{action}", action in enabled_actions)
        permission.save()


def _bootstrap_regular_users_impl(*, apps_registry) -> None:
    payload_raw = _env("DJANGO_BOOTSTRAP_USERS")
    if not payload_raw:
        return

    try:
        user_payloads = json.loads(payload_raw)
    except json.JSONDecodeError as exc:
        logger.error("Bootstrap users skipped: DJANGO_BOOTSTRAP_USERS is invalid JSON (%s).", exc)
        return
    if not isinstance(user_payloads, list):
        logger.error("Bootstrap users skipped: DJANGO_BOOTSTRAP_USERS must be a JSON array.")
        return

    try:
        UserModel = apps_registry.get_model("core", "AppUser")
        PermissionModel = apps_registry.get_model("core", "UserModulePermission")
    except LookupError:
        logger.debug("Bootstrap users skipped: core user models unavailable in current app registry.")
        return

    for index, payload in enumerate(user_payloads, start=1):
        if not isinstance(payload, dict):
            logger.warning("Bootstrap user %s skipped: each entry must be an object.", index)
            continue
        email = (payload.get("email") or "").strip()
        password = str(payload.get("password") or "").strip()
        if not email or not password:
            logger.warning("Bootstrap user %s skipped: email and password are required.", index)
            continue

        normalized_email = UserModel.objects.normalize_email(email)
        role = str(payload.get("role") or "viewer").strip().lower()
        if role not in {"admin", "editor", "viewer"}:
            role = "viewer"
        status = str(payload.get("status") or "active").strip().lower()
        if status not in {"active", "inactive"}:
            status = "active"
        first_name = str(payload.get("first_name") or "").strip()
        last_name = str(payload.get("last_name") or "").strip()
        if not first_name and not last_name:
            first_name, last_name = _parse_name(str(payload.get("name") or ""))

        with transaction.atomic():
            user = UserModel.objects.filter(email__iexact=normalized_email).order_by("id").first()
            created = user is None
            if created:
                user = UserModel.objects.create(
                    email=normalized_email,
                    is_staff=False,
                    is_superuser=False,
                    is_active=status == "active",
                    status=status,
                    role=role,
                    first_name=first_name,
                    last_name=last_name,
                    password=make_password(password),
                )
            else:
                update_fields: list[str] = []
                if user.email != normalized_email:
                    user.email = normalized_email
                    update_fields.append("email")
                if getattr(user, "status", "") != status:
                    user.status = status
                    update_fields.append("status")
                if getattr(user, "is_active", True) != (status == "active"):
                    user.is_active = status == "active"
                    update_fields.append("is_active")
                if getattr(user, "role", "") != role:
                    user.role = role
                    update_fields.append("role")
                if first_name and user.first_name != first_name:
                    user.first_name = first_name
                    update_fields.append("first_name")
                if last_name and user.last_name != last_name:
                    user.last_name = last_name
                    update_fields.append("last_name")
                if hasattr(user, "check_password"):
                    if not user.check_password(password):
                        user.password = make_password(password)
                        update_fields.append("password")
                else:
                    user.password = make_password(password)
                    update_fields.append("password")
                if update_fields:
                    user.save(update_fields=sorted(set(update_fields)))

            _sync_bootstrap_user_permissions(
                user=user,
                permission_payload=payload.get("permissions", {}),
                PermissionModel=PermissionModel,
            )
            logger.info("Bootstrap user %s: %s", "created" if created else "updated", normalized_email)


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
    apps_registry = apps or global_apps
    _bootstrap_admin_impl(apps_registry=apps_registry)
    _bootstrap_regular_users_impl(apps_registry=apps_registry)


def register_bootstrap_admin_signal() -> None:
    post_migrate.connect(
        bootstrap_admin_post_migrate,
        dispatch_uid="core.bootstrap_admin_post_migrate",
    )
