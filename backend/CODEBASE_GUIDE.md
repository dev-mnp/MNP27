# MNP27 Codebase Guide

This guide is for developers who are new to the Django rewrite of the MNP app.
It is intentionally practical: the goal is to help someone answer "where do I
change this?" quickly without reading every file first.

## 1. Project shape

The active backend lives under `backend/`.

Main areas:

- `mnp_backend/settings.py`
  Production settings, database config, allowed hosts, static/media paths.
- `core/models.py`
  All persisted business entities and most enum/choice definitions.
- `core/forms.py`
  Django forms used by the server-rendered UI.
- `core/web_views.py`
  Main server-rendered UI logic.
- `core/web_urls.py`
  `/ui/` routes for the Django templates.
- `core/views.py`
  `/api/` REST API viewsets and actions.
- `core/services.py`
  Shared business logic, numbering, totals, PDFs, audits.
- `templates/base.html`
  Shared page shell, sidebar, top bar, global styles.
- `templates/dashboard/*.html`
  Module-specific HTML templates.
- `core/tests/`
  Focused regression tests for important workflows.

## 2. How requests flow

### Server-rendered UI flow

1. `core/web_urls.py` maps a `/ui/...` route.
2. `core/web_views.py` loads or validates data.
3. `core/forms.py` handles form validation where needed.
4. `core/services.py` handles reusable business rules and document generation.
5. `templates/dashboard/...` renders the HTML.

### API flow

1. `core/urls.py` registers the API endpoints.
2. `core/views.py` exposes DRF viewsets/actions.
3. `core/serializers.py` shapes request/response payloads.
4. `core/models.py` persists the data.

## 3. Module ownership

### Authentication / roles / permissions

- User model: `core/models.py`
  `AppUser`, `UserModulePermission`, `ModuleKeyChoices`
- UI permission gates: `core/web_views.py`
  `RoleRequiredMixin`, `WriteRoleMixin`, `AdminRequiredMixin`
- API permission gates: `core/permissions.py`

### Dashboard

- Route: `core/web_urls.py`
- View: `DashboardView` in `core/web_views.py`
- Template: `templates/dashboard/dashboard.html`

### Master Entry

This covers district, public, and institutions entry workflows.

- Main list/filter/export page:
  - `MasterEntryView` in `core/web_views.py`
  - `templates/dashboard/module_master_entry.html`
- District workflow:
  - views near `DistrictMasterEntryBaseView`
  - template `master_entry_district_form.html`
- Public workflow:
  - views near `PublicMasterEntryBaseView`
  - template `master_entry_public_form.html`
- Institution workflow:
  - views near `InstitutionsMasterEntryBaseView`
  - template `master_entry_institution_form.html`

### Attachments

- download/upload/delete helpers and views: `core/web_views.py`
- attachment model: `ApplicationAttachment` in `core/models.py`

### Article Management

- list/create/edit/delete views: `core/web_views.py`
- form: `ArticleForm` in `core/forms.py`
- template: `article_list.html`, `article_form.html`

### Inventory Planning / Order Management

- route: `/ui/order-management/`
- core row-building logic: `_build_order_management_rows()` in `core/web_views.py`
- page view: `OrderManagementView` in `core/web_views.py`
- template: `templates/dashboard/order_management.html`

This module is heavily derived from master-entry + fund-request state, so most
logic lives in helper functions, not a single model.

### Fund Request

- model: `FundRequest`, `FundRequestRecipient`, `FundRequestArticle`,
  `FundRequestDocument` in `core/models.py`
- UI list/detail/create/update:
  - `FundRequestListView`
  - `FundRequestCreateUpdateMixin`
  - `FundRequestDetailView`
  - `FundRequestSubmitView`
  - `FundRequestReopenView`
  in `core/web_views.py`
- templates:
  - `fund_request_list.html`
  - `fund_request_form.html`
  - `fund_request_detail.html`
- numbering / PDF / totals:
  - `next_fund_request_number()`
  - `generate_fund_request_pdf()`
  - `sync_fund_request_totals()`
  in `core/services.py`

### Purchase Order

Standalone module, independent from Fund Request in the current app version.

- models:
  - `PurchaseOrder`
  - `PurchaseOrderItem`
  in `core/models.py`
- UI routes: `core/web_urls.py`
- list/create/update/PDF workflow:
  - `PurchaseOrderListView`
  - `PurchaseOrderCreateUpdateMixin`
  - `PurchaseOrderPDFView`
  - `PurchaseOrderSubmitView`
  in `core/web_views.py`
- templates:
  - `purchase_order_list.html`
  - `purchase_order_form.html`
  - `purchase_order_confirm_delete.html`
- numbering / PDF / totals:
  - `next_purchase_order_number()`
  - `generate_purchase_order_pdf()`
  - `sync_purchase_order_totals()`
  in `core/services.py`

### Base Files / Master data imports

- base page:
  - `MasterDataBaseView`
  - `module_master_data.html`
- import helpers:
  - `_import_district_master_csv()`
  - `_import_article_master_csv()`
  - `_import_public_history_csv()`
  in `core/web_views.py`
- management commands:
  - `core/management/commands/...`

### User Management

- model: `AppUser`
- forms:
  - `AppUserCreateForm`
  - `AppUserUpdateForm`
  - `AppUserPasswordResetForm`
- views:
  - `UserManagementListView`
  - `UserManagementCreateView`
  - `UserManagementUpdateView`
  - `UserManagementPasswordResetView`
  - `UserManagementDeleteView`

### Audit Logs

- model: `AuditLog`
- logger helper: `log_audit()` in `core/services.py`
- UI page: `ApplicationAuditLogListView` in `core/web_views.py`
- API page: `AuditLogViewSet` in `core/views.py`

## 4. Common change locations

### Change a field label, widget, default, or validation in a form

Go to `core/forms.py`.

Typical examples:

- Article form fields: `ArticleForm`
- Fund request header fields: `FundRequestForm`
- Purchase order comments default: `PurchaseOrderForm`

### Change what appears on a page

Use both:

- `templates/dashboard/...`
- matching view in `core/web_views.py`

Example:

- fund request list columns -> `fund_request_list.html` + `FundRequestListView`
- purchase order expanded row -> `purchase_order_list.html` + `PurchaseOrderListView`

### Change numbering logic

Go to `core/services.py`.

- Fund request numbering -> `next_fund_request_number()`
- Purchase order numbering -> `next_purchase_order_number()`

### Change sidebar modules or order

Go to `templates/base.html`.

### Change search/filter/sort logic

Go to `core/web_views.py`, usually the list page view:

- `MasterEntryView`
- `ArticleListView`
- `OrderManagementView`
- `FundRequestListView`
- `PurchaseOrderListView`
- `ApplicationAuditLogListView`

### Change PDF layout

Go to `core/services.py`.

- fund request PDF -> `generate_fund_request_pdf()`
- purchase order PDF -> `generate_purchase_order_pdf()`

### Change imports/exports

Go to `core/web_views.py`.

- master entry CSV export helpers
- base-file import helpers
- inventory/fund request exports

## 5. File guide by responsibility

### `core/models.py`

Use when:

- adding/removing DB fields
- adding new models
- changing enum choices
- changing permission keys

Be careful:

- every schema change needs a migration in `core/migrations/`

### `core/forms.py`

Use when:

- changing what the user can type/select
- adding defaults to the HTML form
- tightening or relaxing validation

### `core/services.py`

Use when:

- a rule is shared by multiple views
- generating PDFs
- computing totals
- assigning numbers
- writing audit log helper logic

### `core/web_views.py`

Use when:

- changing a UI workflow
- adding a filter/search rule
- changing list expansion behavior
- changing create/edit/submit/reopen/delete behavior

This is currently the heaviest file in the project.

### `core/views.py`

Use when:

- changing DRF API behavior
- changing API-only permissions or actions

### `templates/base.html`

Use when:

- changing layout used by all UI pages
- changing sidebar items
- changing global button/input/table styles

## 6. Testing strategy currently in repo

Existing focused regression tests:

- `core/tests/test_fund_request_list.py`
- `core/tests/test_search_bars.py`
- `core/tests/test_purchase_order_module.py`

These are good places to add protection when fixing:

- duplicate rows in list views
- search/filter regressions
- numbering issues
- purchase order behavior

## 7. Safe workflow for new developers

When changing anything, use this order:

1. identify the template or page first
2. identify the matching view in `core/web_views.py`
3. check whether the rule belongs in `forms.py` or `services.py`
4. update tests if behavior changes
5. run `manage.py check`
6. run the smallest relevant test module

## 8. Recommended first files to read

If someone is brand new, read in this order:

1. `templates/base.html`
2. `core/web_urls.py`
3. `core/models.py`
4. `core/forms.py`
5. `core/web_views.py`
6. `core/services.py`

Then jump to the module you actually want to change.
