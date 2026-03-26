# MNP Django Backend (Python-first migration target)

This backend mirrors the existing Supabase schema as Django models and DRF APIs.

## Quick start

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # then fill real DB credentials
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

## Developer guide

If you are new to this codebase, start with:

- `CODEBASE_GUIDE.md` for the architecture overview
- `CHANGE_MAP.md` for "if I want to change X, where do I go?"

## What is included

- Custom user model with roles (`admin`, `editor`, `viewer`) in `core.AppUser`
- DRF API viewsets for:
  - `articles`
  - `district-masters`
  - `district-beneficiaries`
  - `public-beneficiaries`
  - `institutions-beneficiaries`
  - `fund-requests`, `fund-request-recipients`, `fund-request-articles`, `fund-request-documents`
  - `order-entries`
  - `beneficiary-history` (read-only)
  - `audit-logs` (read-only)
  - `users`
- JWT auth:
  - `POST /api/auth/token/`
  - `POST /api/auth/token/refresh/`
  - `GET /api/auth/me/`
- Fund request status workflow:
  - default draft on create
  - `POST /api/fund-requests/{id}/submit/`
  - `POST /api/fund-requests/{id}/set-status/`
  - `POST /api/fund-requests/{id}/allocate-po/`
- Python UI (Django templates):
  - `GET /ui/` master entry landing page
  - `GET /ui/articles/` manage articles
  - `GET /ui/articles/new/` create article
  - `GET /ui/login/` sign in with Django session
  - `GET /ui/fund-requests/` list fund requests
  - `GET /ui/fund-requests/new/` create draft fund request
  - `GET /ui/fund-requests/{id}/` view fund request
  - `POST /ui/fund-requests/{id}/submit/` submit draft
  - `GET /ui/fund-requests/{id}/documents/new/` upload fund request documents

## Migration notes from Supabase

1. Create the database in PostgreSQL and import existing data CSV/SQL dump.
2. Create a Django user in `db` with migration rights.
3. Run Django migrations against the same DB connection.
4. Check `fund_request_number`/`purchase_order_number` formats if you have a legacy numbering policy.
5. Backfill `app_users` with role/status for your team users and mark existing users as active.
6. Keep this API as the single backend source so only one stack runs from now on.

## CSV import commands

Load your admin-prepared master data into `MNP27` with:

```bash
python manage.py import_districts --file "/Users/aswathshakthi/Desktop/district_president.csv"
python manage.py import_articles --file "/Users/aswathshakthi/Desktop/ Aswath Files/App_Databases_Codes/Files/article_list-2026-03-09.csv"
python manage.py import_public_history --file "/Users/aswathshakthi/Desktop/Past_Dist_Public_beneficiary.csv"
```

If you want to replace all old beneficiary history before importing:

```bash
python manage.py import_public_history --file "/Users/aswathshakthi/Desktop/Past_Dist_Public_beneficiary.csv" --replace
```
