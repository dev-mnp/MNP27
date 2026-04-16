# MNP27 - Python-first Django backend + UI migration

This repository now contains the Python migration target for the MNP app.
The old Node/ Vite frontend was removed from this repo and the app is now
managed from Django templates for easier long-term maintenance by Python-only teams.

## What is in this repo

- `backend/` — Django project:
  - custom users with role-based access (`admin`, `editor`, `viewer`)
  - REST APIs (DRF) for all core resources
  - Django web UI for core operations (`/ui/*`)
  - fund request management with draft/submit workflow

## Quick start

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```


## Key UI routes

- Login: `/ui/login/`
- Dashboard: `/ui/`
- Articles: `/ui/articles/`
- Fund Requests: `/ui/fund-requests/`
- Fund Request details: `/ui/fund-requests/<id>/`

## Notes

- This project is intended to be the single place for app logic and storage integration.
- Frontend was intentionally simplified during migration to keep this repo lightweight and
  easy for a Python maintainer to operate.
