# MNP27 - Developer and End-User Guide

MNP27 is a Django monolith used to manage beneficiary entries, fund requests, purchase orders, planning pipelines (seat/sequence/token/labels), and reporting.

It provides:

- A server-rendered web UI under `/ui/`
- A REST API under `/api/`
- Role- and module-based access control for admin, editor, and viewer users

---

## 1) Tech Stack and Project Layout

### Stack

- Python 3.11+ (project currently configured for Django 4.2)
- Django + Django REST Framework
- PostgreSQL (required)
- JWT auth for API (`simplejwt`) + session auth for UI
- WhiteNoise for static files
- Gunicorn for production app serving

### Repository Layout

- `backend/manage.py`: Django CLI entry point
- `backend/mnp_backend/`: Django project config (`settings.py`, `urls.py`, `wsgi.py`, `asgi.py`)
- `backend/core/`: Main business app (models, web modules, API views, shared services)
- `backend/core/templates/`: Module-specific UI templates
- `backend/templates/`: global templates (login/base)
- `backend/core/tests/`: regression and workflow tests
- `backend/requirements.txt`: Python dependencies
- `backend/entrypoint.sh`: container startup

---

## 2) Local Developer Setup

## Prerequisites

- PostgreSQL instance
- Python 3.11 or 3.12
- `DATABASE_URL` for Postgres

### Environment

Create `backend/.env` (or update existing):

```env
DJANGO_SECRET_KEY=change-me
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost
DATABASE_URL=postgresql://user:password@localhost:5432/mnp27
DJANGO_TIME_ZONE=Asia/Kolkata
```

Optional settings commonly used:

- `DJANGO_ENABLE_REQUEST_TIMING=True`
- `DJANGO_DB_CONN_MAX_AGE=60`
- `CORS_ALLOW_ALL_ORIGINS=True` (dev only)

### Install and Run

From `backend/`:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

UI: [http://127.0.0.1:8000/ui/](http://127.0.0.1:8000/ui/)  
API: [http://127.0.0.1:8000/api/](http://127.0.0.1:8000/api/)

---

## 3) Runtime Routing and Entry Points

Defined in `backend/mnp_backend/urls.py`:

- `/` -> redirects to `/ui/`
- `/ui/login/`, `/ui/logout/`
- `/ui/` -> module routes from `core.web_urls`
- `/api/auth/token/` and `/api/auth/token/refresh/`
- `/api/` -> DRF routes from `core.urls`

UI module mounting is centralized in `backend/core/web_urls.py`.

---

## 4) Data and Domain Overview

The domain model is centralized in `backend/core/models.py`.

### Core entities

- `AppUser`, `UserModulePermission`: authentication and fine-grained module actions
- `Article`, `Vendor`, `DistrictMaster`: master data
- `DistrictBeneficiaryEntry`, `PublicBeneficiaryEntry`, `InstitutionsBeneficiaryEntry`: application entry domain
- `FundRequest`, `FundRequestRecipient`, `FundRequestArticle`, `FundRequestDocument`
- `PurchaseOrder`, `PurchaseOrderItem`, `OrderEntry`
- `EventSession` + seat/sequence/token/label rows for pipeline modules
- `AuditLog` for system action history

### Business status lifecycles (high-level)

- Beneficiary entries: draft/submitted (+ archived for public flows)
- Fund request and purchase order: draft/submitted with reopen paths
- Order entries generated from submitted fund requests

---

## 5) Security and Permission Model

### Authentication

- UI: session-based login
- API: JWT (plus DRF session auth support)

### Authorization

- Roles: `admin`, `editor`, `viewer`
- User must be `active`
- Module permissions are action-based, e.g.:
  - `view`
  - `create_edit`
  - `delete`
  - `submit`
  - `reopen`
  - `export`
  - `upload_replace`
  - `reset_password`

### Enforcement points

- UI mixins in `core/shared/permissions.py`
- API permissions in `core/permissions.py`
- Template checks via module permission tags

---

## 6) End-User Flow Guide (By Module)

This section is written for operators and admins using the UI.

### 6.1 Dashboard

1. Open `/ui/` or `/ui/dashboard/`
2. Review rollups across district/public/institution datasets
3. Use values as monitoring checkpoints before submitting downstream workflows

### 6.2 Application Entry (Master Entry)

1. Go to `/ui/master-entry/`
2. Select beneficiary type: District, Public, or Institutions
3. Create or edit entry rows (article, quantity, amounts, beneficiary details)
4. Save as Draft while data is in progress
5. Submit when finalized
6. Reopen if edits are required later (permission-dependent)
7. Export CSV when needed

Attachment flow:

1. Upload attachment to entry
2. Preview/download attachment from entry views
3. Replace/remove attachment if corrections are needed

### 6.3 Article Management

1. Open `/ui/articles/`
2. Add or edit article master data (name, type, category, cost)
3. Keep inactive records disabled instead of deleting when possible

### 6.4 Vendor Management

1. Open `/ui/vendors/`
2. Create and maintain vendor profile details (GST, address, payment details)
3. Use vendor records in fund request and purchase order flows

### 6.5 Order & Fund Request

1. Open `/ui/fund-requests/`
2. Create fund request (Aid or Article mode)
3. Add recipients/articles and financial details
4. Save draft while compiling
5. Submit finalized request
6. Generate and download PDF
7. Reopen when authorized and necessary

On submit:

- System syncs order entries from submitted request data
- Request becomes part of planning and downstream records

### 6.6 Purchase Order

1. Open `/ui/purchase-orders/`
2. Create PO from vendor and item details
3. Review computed totals
4. Save draft
5. Submit PO and generate PO PDF
6. Reopen if a correction cycle is required

### 6.7 Inventory Planning

1. Open `/ui/order-management/`
2. Review required vs ordered/pending quantities by article
3. Use as planning bridge between beneficiary demand and procurement state

### 6.8 Seat Allocation -> Sequence -> Token -> Labels Pipeline

This is the operational event pipeline:

1. **Seat Allocation** (`/ui/seat-allocation/`)
   - Load/sync source data
   - Verify quantity splits and grouping
2. **Sequence List** (`/ui/sequence-list/`)
   - Assign and validate sequence ordering
3. **Token Generation** (`/ui/token-generation/`)
   - Build token ranges and export output
4. **Labels** (`/ui/labels/`)
   - Generate label-ready outputs from token data

Each stage expects validated output from the previous stage.

### 6.9 Reports

1. Open `/ui/reports/`
2. Generate module-specific reports (PDF/XLSX/DOCX, depending on report)
3. Use report exports for audit, acknowledgments, and event operations

### 6.10 Audit Logs

1. Open `/ui/applications/audit-logs/`
2. Search/filter by user, action, module, or record
3. Review change history for operational traceability

### 6.11 User Management (Admin)

1. Open `/ui/users/`
2. Create user, assign role, set status
3. Configure module-level action permissions
4. Reset password when needed
5. Deactivate users instead of deleting when historical trace is required

---

## 7) Developer Flow Guide (How Changes Usually Move)

### Typical feature implementation flow

1. **Model updates** in `core/models.py` + create migration
2. **Business logic** in module `services.py` or `shared/` utility services
3. **UI behavior** in module `views.py`, `forms.py`, and templates
4. **API behavior** in `core/views.py` + `core/serializers.py`
5. **Permissions** in mixins/permission classes and template checks
6. **Audit logging** for all significant create/update/delete/status transitions
7. **Tests** in `core/tests/` for workflow and regression coverage

### Suggested command sequence

From `backend/`:

```bash
python manage.py makemigrations
python manage.py migrate
python manage.py test
```

If static assets/templates changed, verify affected UI pages manually.

---

## 8) API Quick Reference

Main endpoints (under `/api/`):

- `auth/me/`
- `users/`
- `articles/`
- `district-masters/`
- `district-beneficiaries/`
- `public-beneficiaries/`
- `institutions-beneficiaries/`
- `fund-requests/` (with submit/status/PO allocation actions)
- `fund-request-recipients/`
- `fund-request-articles/`
- `fund-request-documents/`
- `order-entries/`
- `beneficiary-history/`
- `audit-logs/`

JWT:

- `POST /api/auth/token/`
- `POST /api/auth/token/refresh/`

---

## 9) Deployment Notes

- Production startup goes through `backend/entrypoint.sh`
- Static handling via WhiteNoise (`collectstatic` in deploy flow where needed)
- Gunicorn serves `mnp_backend.wsgi:application`
- Ensure secure `DJANGO_SECRET_KEY`, strict `DJANGO_ALLOWED_HOSTS`, and production-safe CORS/CSRF settings

---

## 10) Troubleshooting

### App fails on startup with database error

- Verify `DATABASE_URL` in `backend/.env`
- Confirm DB is reachable and credentials are valid
- Run `python manage.py migrate`

### Permission denied on UI actions

- Check user status (`active`)
- Confirm module action permission exists for that user
- Verify role is appropriate for requested operation

### Missing records in pipeline modules

- Confirm upstream stage has completed successfully
- Validate session/event selection and uploaded source files
- Check audit logs for rejected/blocked transitions

---

## 11) Current Test Focus and Gaps

Existing tests are strong around:

- Application entry workflows
- Fund request and purchase order flows
- Phase-2 pipeline and report generation

Potential expansion areas:

- More API permission matrix tests
- Attachment/Google Drive failure-path tests
- Additional user-management negative-case coverage

---

## 12) Contribution Guidelines (Recommended)

- Keep business logic in service modules; keep views thin
- Add/update tests for every status transition and permission-sensitive action
- Preserve audit logging for all significant mutations
- Avoid cross-module coupling unless a shared service abstraction is needed

