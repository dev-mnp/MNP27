
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

ENV PORT=8080
EXPOSE 8080

RUN chmod +x /app/entrypoint.sh

# Collect static at build time to reduce cold-start work on Cloud Run.
# Provide a dummy DATABASE_URL because our Django settings require it,
# but collectstatic does not actually connect to the database.
RUN DJANGO_DEBUG=False \
  DATABASE_URL='postgresql://user:pass@localhost:5432/dbname' \
  python manage.py collectstatic --noinput

CMD ["/app/entrypoint.sh"]
