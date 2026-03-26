# MNP27 Change Map

Use this file as a fast lookup table when you know what you want to change but
do not yet know where that logic lives.

## If you want to change...

### Sidebar order, module labels, or which modules appear

- `templates/base.html`

### Login redirects, allowed hosts, static/media paths, or database config

- `mnp_backend/settings.py`

### Master Entry overview page filters, search, export, or row layout

- `core/web_views.py`
  `MasterEntryView`, export helpers, filter helpers
- `templates/dashboard/module_master_entry.html`

### District master entry form fields or save workflow

- `core/forms.py`
- `core/web_views.py`
  district helper functions and `DistrictMasterEntry...` views
- `templates/dashboard/master_entry_district_form.html`

### Public master entry form fields or duplicate/Aadhaar behavior

- `core/forms.py`
- `core/web_views.py`
  public helper functions and `PublicMasterEntry...` views
- `templates/dashboard/master_entry_public_form.html`

### Institution master entry form fields or grouped-row behavior

- `core/forms.py`
- `core/web_views.py`
  institution helper functions and `InstitutionsMasterEntry...` views
- `templates/dashboard/master_entry_institution_form.html`

### Article master fields, categories, active/combo behavior

- `core/models.py` -> `Article`
- `core/forms.py` -> `ArticleForm`
- `core/web_views.py` -> article CRUD views
- `templates/dashboard/article_list.html`
- `templates/dashboard/article_form.html`

### Inventory Planning numbers or derived order rows

- `core/web_views.py`
  `_build_order_management_rows()`
  `OrderManagementView`
- `templates/dashboard/order_management.html`

### Fund Request list page columns, actions, filters, or expanded rows

- `core/web_views.py` -> `FundRequestListView`
- `templates/dashboard/fund_request_list.html`

### Fund Request form fields, Aid CSV import, or recipient/article row behavior

- `core/forms.py`
  `FundRequestForm`, `FundRequestRecipientForm`, `FundRequestArticleForm`
- `core/web_views.py`
  `FundRequestCreateUpdateMixin`
  `_fund_request_aid_type_choices()`
  `_fund_request_article_choices()`
  `_get_aid_beneficiary_options()`
- `templates/dashboard/fund_request_form.html`

### Fund Request number format

- `core/models.py`
  `parse_fund_request_sequence()`
  `format_fund_request_number()`
- `core/services.py`
  `next_fund_request_number()`

### Fund Request PDF layout

- `core/services.py`
  `generate_fund_request_pdf()`

### Fund Request document upload behavior

- `core/forms.py`
  `FundRequestDocumentUploadForm`
- `core/web_views.py`
  `FundRequestDocumentUploadView`
- `templates/dashboard/fund_request_upload_document.html`

### Purchase Order list page, filters, expanded rows, or actions

- `core/web_views.py`
  `PurchaseOrderListView`
- `templates/dashboard/purchase_order_list.html`

### Purchase Order form fields or default comments

- `core/models.py`
  `PurchaseOrder`, `PURCHASE_ORDER_DEFAULT_COMMENTS`
- `core/forms.py`
  `PurchaseOrderForm`, `PurchaseOrderItemForm`
- `templates/dashboard/purchase_order_form.html`

### Purchase Order number format

- `core/services.py`
  `next_purchase_order_number()`
  `ensure_purchase_order_number()`

### Purchase Order PDF content or layout

- `core/services.py`
  `generate_purchase_order_pdf()`

### User roles, module permissions, or default access by role

- `core/models.py`
  `RoleChoices`
  `ModuleKeyChoices`
  `build_role_module_permission_map()`
  `UserModulePermission`
- `core/forms.py`
  `AppUserPermissionFormMixin`

### User management screens

- `core/web_views.py`
  `UserManagement...` views
- `core/forms.py`
  `AppUserCreateForm`, `AppUserUpdateForm`, `AppUserPasswordResetForm`
- `templates/dashboard/user_management.html`
- `templates/dashboard/user_form.html`

### Audit log behavior

- `core/services.py`
  `log_audit()`
- `core/web_views.py`
  audit label/format helper functions
  `ApplicationAuditLogListView`
- `core/views.py`
  `AuditLogViewSet`

### Base file uploads and CSV imports

- `core/web_views.py`
  `MasterDataBaseView`
  `_import_district_master_csv()`
  `_import_article_master_csv()`
  `_import_public_history_csv()`
- `templates/dashboard/module_master_data.html`

### API behavior instead of UI behavior

- `core/urls.py`
- `core/views.py`
- `core/serializers.py`

## Quick debug checklist

When debugging a feature:

1. Find the template first.
2. Find the `/ui/` route in `core/web_urls.py`.
3. Open the matching view in `core/web_views.py`.
4. Check whether the form is defined in `core/forms.py`.
5. Check whether numbering/PDF/totals/audit rules live in `core/services.py`.
6. If a DB field is involved, confirm the model in `core/models.py`.
