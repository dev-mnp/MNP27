#!/usr/bin/env python
"""Django management utility for the MNP project."""

from __future__ import annotations

import os
import sys


def main() -> None:
    """Run administrative tasks for the Django project."""
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mnp_backend.settings")
    try:
        from django.core.management import execute_from_command_line
    except Exception as exc:
        raise ImportError(
            "Could not import Django. "
            "Activate your virtual environment and run `pip install -r requirements.txt`."
        ) from exc

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()

