from __future__ import annotations

import os
import time

from django.conf import settings
from django.db import connection, reset_queries


class RequestTimingMiddleware:
    """
    Lightweight request timing instrumentation.

    Enable by setting DJANGO_ENABLE_REQUEST_TIMING=1.
    Optionally include DB query stats in DEBUG mode with DJANGO_REQUEST_TIMING_DB=1.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self.include_db = os.getenv("DJANGO_REQUEST_TIMING_DB", "0").lower() in {"1", "true", "yes", "on"}

    def __call__(self, request):
        start = time.monotonic()
        if self.include_db and settings.DEBUG:
            reset_queries()

        response = self.get_response(request)

        total_ms = (time.monotonic() - start) * 1000.0
        server_timing_parts = [f"app;dur={total_ms:.1f}"]

        if self.include_db and settings.DEBUG:
            queries = connection.queries
            try:
                db_ms = sum(float(q.get("time") or 0) for q in queries) * 1000.0
            except (TypeError, ValueError):
                db_ms = 0.0
            server_timing_parts.append(f"db;dur={db_ms:.1f}")
            # Helpful for quick curl checks without opening DevTools.
            response["X-DB-Queries"] = str(len(queries))
            response["X-DB-Time-ms"] = f"{db_ms:.1f}"

        response["Server-Timing"] = ", ".join(server_timing_parts)
        return response

