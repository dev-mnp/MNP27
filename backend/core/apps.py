from __future__ import annotations

from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"
    verbose_name = "MNP Core Domain"

    def ready(self):
        from core.bootstrap_admin import register_bootstrap_admin_signal

        register_bootstrap_admin_signal()
