#!/bin/sh
set -eu

: "${PORT:=8080}"

# Collect static at container start so builds do not require DATABASE_URL.
# Cloud Run will inject env vars at runtime (DATABASE_URL, DJANGO_DEBUG, etc).
if [ "${RUN_COLLECTSTATIC:-1}" = "1" ]; then
  python manage.py collectstatic --noinput
fi

# Run migrations at startup (on by default).
# Set RUN_MIGRATIONS=0 if you ever want to skip migrations (for example, if you only want to use schema.sql).
if [ "${RUN_MIGRATIONS:-1}" = "1" ]; then
  python manage.py migrate --noinput
fi

workers="${GUNICORN_WORKERS:-${WEB_CONCURRENCY:-2}}"
timeout="${GUNICORN_TIMEOUT:-180}"

exec gunicorn mnp_backend.wsgi:application \
  --bind "0.0.0.0:${PORT}" \
  --workers "${workers}" \
  --timeout "${timeout}" \
  --access-logfile - \
  --error-logfile - \
  --worker-tmp-dir /tmp
