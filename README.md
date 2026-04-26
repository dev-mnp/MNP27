# MNP27

MNP27 is a Django application for managing Makkal Nala Pani beneficiary applications, base files, article management, inventory planning, fund requests, seat allocation, sequence list, token generation, labels, reports, purchase orders, vendors, users, and audit logs.

## Project Structure

- `backend/`: Django project and application code.
- `backend/manage.py`: Django command entry point.
- `backend/core/`: Main app modules, models, services, views, templates, and reports.
- `backend/templates/`: Shared UI templates such as login and base layout.
- `backend/requirements.txt`: Python dependencies.
- `Dockerfile`: Production container build.
- `Deployment.md`: Deployment reference.

## Local Setup

Create `backend/.env` with the required local settings.

Minimum required values:

```env
DJANGO_SECRET_KEY=change-me
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost
CSRF_TRUSTED_ORIGINS=http://127.0.0.1:8000,http://localhost:8000
DATABASE_URL=postgresql://user:password@localhost:5432/mnp27
DJANGO_TIME_ZONE=Asia/Kolkata
```

Install and run:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

Open:

`http://127.0.0.1:8000/ui/`

## Checks

Run this before committing:

```bash
cd backend
python manage.py check
python manage.py test
```

## Docker

Build from the repository root:

```bash
docker build -t mnp27 .
```

Run locally:

```bash
docker run --env-file backend/.env -p 8080:8080 mnp27
```

Open:

`http://127.0.0.1:8080`

## Deployment

Production uses:

- Supabase PostgreSQL
- Google Cloud Run
- Google Drive OAuth for attachments
- Cloudflare Worker reverse proxy for the custom domain

Keep secrets out of Git. Do not commit `.env`, database passwords, Google OAuth secrets, or service account credentials.

See the in-app User Manual and `Deployment.md` for detailed deployment steps.
