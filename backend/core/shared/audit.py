"""Shared audit helper functions used across multiple modules."""
from __future__ import annotations
import logging

from typing import Optional

from core import models

logger = logging.getLogger(__name__)

def get_request_audit_meta(request):
    return {
        "ip_address": request.META.get("REMOTE_ADDR"),
        "user_agent": request.META.get("HTTP_USER_AGENT", ""),
    }


def log_audit(
    *,
    user: Optional[models.AppUser],
    action_type: str,
    entity_type: str,
    entity_id: str | None,
    details: dict,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> None:
    # Audit logs should never block core workflows (edit/delete/reopen/submit etc).
    # If the audit table is missing or DB policies deny writes, we log and continue.
    try:
        models.AuditLog.objects.create(
            user=user,
            action_type=action_type,
            entity_type=entity_type,
            entity_id=entity_id,
            details=details,
            ip_address=ip_address,
            user_agent=user_agent,
        )
    except Exception:
        logger.exception(
            "Failed to write audit log (action=%s entity=%s id=%s). Continuing without audit row.",
            action_type,
            entity_type,
            entity_id,
        )
