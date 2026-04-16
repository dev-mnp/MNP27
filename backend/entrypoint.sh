#!/bin/sh
set -eu

: "${PORT:=8080}"

# Collect static at container start if explicitly enabled.
# Recommended: collect at build time (Dockerfile) and leave this off in Cloud Run.
if [ "${RUN_COLLECTSTATIC:-0}" = "1" ]; then
  python manage.py collectstatic --noinput
fi

# Run migrations at startup (on by default).
# Set RUN_MIGRATIONS=0 if you ever want to skip migrations (for example, if you only want to use schema.sql).
if [ "${RUN_MIGRATIONS:-1}" = "1" ]; then
  python manage.py migrate --noinput
fi

workers="${GUNICORN_WORKERS:-${WEB_CONCURRENCY:-1}}"
timeout="${GUNICORN_TIMEOUT:-180}"

exec gunicorn mnp_backend.wsgi:application \
  --bind "0.0.0.0:${PORT}" \
  --workers "${workers}" \
  --timeout "${timeout}" \
  --access-logfile - \
  --error-logfile - \
  --worker-tmp-dir /tmp
