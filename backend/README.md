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

## Migration notes from Supabase

1. Create the database in PostgreSQL and import existing data CSV/SQL dump.
2. Create a Django user in `db` with migration rights.
3. Run Django migrations against the same DB connection.
4. Check `fund_request_number`/`purchase_order_number` formats if you have a legacy numbering policy.
5. Backfill `app_users` with role/status for your team users and mark existing users as active.
6. Keep this API as the single backend source so only one stack runs from now on.

