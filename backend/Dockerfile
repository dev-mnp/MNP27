FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# ReportLab and image/PDF tooling need a few shared libs at runtime.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    libjpeg62-turbo \
    libfreetype6 \
    zlib1g \
  && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --upgrade pip \
  && pip install --no-cache-dir -r /app/requirements.txt

COPY . /app

RUN python manage.py collectstatic --noinput

ENV PORT=8080
EXPOSE 8080

CMD ["sh", "-c", "gunicorn mnp_backend.wsgi:application --bind 0.0.0.0:${PORT} --workers ${GUNICORN_WORKERS:-2} --timeout ${GUNICORN_TIMEOUT:-180} --access-logfile - --error-logfile -"]

