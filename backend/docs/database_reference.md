# Database Reference (Core)

This is a developer-facing documentation of the project tables in `core/models.py`.

## How Data Flows

1. Application Entry tables collect beneficiary rows (`district/public/institutions`) + attachments.
2. Fund Request tables consume selected rows and create aid/article requests.
3. Phase-2 pipeline uses session-scoped tables:
   - `seat_allocation_rows` -> `sequence_list_items` -> `token_generation_rows`
4. Labels and Reports sync from token-generation data.

## Shared Conventions

- Most tables have:
  - `id`
  - `created_at`
  - `updated_at`
- Most user-tracked writes use `created_by` / `updated_by` (`app_users` FK).
- `event_sessions` scopes the phase-2 dataset.

---

## 1) User & Permissions

### `app_users` (Model: `AppUser`)

Purpose:
- Login identity, role, active status, ownership tracking.

Columns:
- `id` (UUID, PK)
- `email` (unique)
- `password`
- `first_name`, `last_name`
- `role`, `status`
- `is_staff`, `is_superuser`, `is_active`, `last_login`, `date_joined`
- `created_by` (FK -> `app_users.id`)
- `created_at`, `updated_at`
- `groups` (M2M -> `auth_group`)
- `user_permissions` (M2M -> `auth_permission`)

Used in:
- User Management and ownership/audit in all modules.

### `user_module_permissions` (Model: `UserModulePermission`)

Purpose:
- Per-user permission matrix per module.

Columns:
- `id`
- `user` (FK -> `app_users.id`)
- `module_key`
- `can_view`
- `can_create_edit`
- `can_delete`
- `can_submit`
- `can_reopen`
- `can_export`
- `can_upload_replace`
- `can_reset_password`
- `created_at`, `updated_at`

Used in:
- Access-control checks for each feature page.

---

## 2) Master Data

### `articles` (Model: `Article`)

Purpose:
- Master item catalog for Aid/Article/Project and pricing behavior.

Columns:
- `id`
- `article_name` (unique)
- `article_name_tk`
- `cost_per_unit`
- `allow_manual_price`
- `item_type`
- `category`
- `master_category`
- `comments`
- `is_active`
- `combo`
- `created_at`, `updated_at`

Used in:
- Article Management, Application Entry, Fund Request, Inventory, Reports.

### `vendors` (Model: `Vendor`)

Purpose:
- Vendor master for procurement/fund request article entries.

Columns:
- `id`
- `vendor_name`
- `gst_number`
- `phone_number`
- `address`, `city`, `state`, `pincode`
- `cheque_in_favour`
- `is_active`
- `created_at`, `updated_at`

Used in:
- Fund Request article mode, Purchase Order.

### `district_master` (Model: `DistrictMaster`)

Purpose:
- District setup + contribution/budget metadata.

Columns:
- `id`
- `district_name` (unique)
- `allotted_budget`
- `president_name`
- `mobile_number`
- `application_number`
- `is_active`
- `created_at`, `updated_at`

Used in:
- Base Files, District Entry, Dashboard, Reports.

---

## 3) Application Entry

### `district_beneficiary_entries` (Model: `DistrictBeneficiaryEntry`)

Purpose:
- District beneficiary application rows.

Columns:
- `id`
- `district` (FK -> `district_master.id`)
- `application_number`
- `article` (FK -> `articles.id`)
- `article_cost_per_unit`
- `quantity`
- `total_amount`
- `item_comes_here`
- `name_of_beneficiary`
- `name_of_institution`
- `aadhar_number`
- `cheque_rtgs_in_favour`
- `notes`
- `internal_notes`
- `status`
- `fund_request` (FK -> `fund_request.id`, nullable)
- `created_by` (FK -> `app_users.id`)
- `created_at`, `updated_at`

Used in:
- District application entry lifecycle (draft/submitted/reopen/archive).

### `public_beneficiary_entries` (Model: `PublicBeneficiaryEntry`)

Purpose:
- Public beneficiary application rows with Aadhaar verification state.

Columns:
- `id`
- `application_number` (unique, nullable)
- `name`
- `aadhar_number`
- `aadhaar_status`
- `is_handicapped`
- `gender`
- `female_status`
- `address`
- `mobile`
- `article` (FK -> `articles.id`)
- `article_cost_per_unit`
- `quantity`
- `total_amount`
- `item_comes_here`
- `name_of_institution`
- `cheque_rtgs_in_favour`
- `notes`
- `status`
- `archived_previous_status`
- `archived_at`
- `archived_by` (FK -> `app_users.id`, nullable)
- `created_by` (FK -> `app_users.id`, nullable)
- `fund_request` (FK -> `fund_request.id`, nullable)
- `created_at`, `updated_at`

Used in:
- Public entry + Aadhaar-specific behavior.

### `institutions_beneficiary_entries` (Model: `InstitutionsBeneficiaryEntry`)

Purpose:
- Institution/Others beneficiary application rows.

Columns:
- `id`
- `institution_name`
- `institution_type`
- `application_number`
- `address`
- `mobile`
- `article` (FK -> `articles.id`)
- `article_cost_per_unit`
- `quantity`
- `total_amount`
- `item_comes_here`
- `name_of_beneficiary`
- `name_of_institution`
- `aadhar_number`
- `cheque_rtgs_in_favour`
- `notes`
- `internal_notes`
- `status`
- `created_by` (FK -> `app_users.id`, nullable)
- `fund_request` (FK -> `fund_request.id`, nullable)
- `created_at`, `updated_at`

Used in:
- Institution and Others beneficiary flows.

### `application_attachments` (Model: `ApplicationAttachment`)

Purpose:
- Attachment metadata and lifecycle (draft/final, local + Drive metadata).

Columns:
- `id`
- `application_type`
- `application_id`
- `draft_uid`
- `district` (FK -> `district_master.id`, nullable)
- `public_entry` (FK -> `public_beneficiary_entries.id`, nullable)
- `institution_application_number`
- `original_filename`
- `display_filename`
- `prefix`
- `file` (FileField)
- `file_name`
- `drive_file_id`
- `drive_mime_type`
- `drive_view_url`
- `form_token`
- `status`
- `temp_expires_at`
- `uploaded_by` (FK -> `app_users.id`, nullable)
- `created_at`, `updated_at`

Used in:
- Attachments in district/public/institution/others pages and overviews.

### `public_beneficiary_history` (Model: `PublicBeneficiaryHistory`)

Purpose:
- Historical (past years) public data reference.

Columns:
- `id`
- `aadhar_number`
- `name`
- `year`
- `article_name`
- `application_number`
- `comments`
- `is_handicapped`
- `handicapped_status`
- `address`
- `mobile`
- `aadhar_number_sp`
- `is_selected`
- `category`
- `gender`
- `gender_status`
- `created_at`, `updated_at`

Used in:
- Cross-year checks and import/reference workflows.

---

## 4) Fund Request + PO

### `fund_request` (Model: `FundRequest`)

Purpose:
- Header/master record for each fund request.

Columns:
- `id`
- `fund_request_type` (Aid/Article)
- `fund_request_number` (unique, nullable)
- `status`
- `total_amount`
- `aid_type`
- `notes`
- Supplier snapshot fields:
  - `gst_number`
  - `supplier_name`
  - `supplier_address`
  - `supplier_city`
  - `supplier_state`
  - `supplier_pincode`
- `purchase_order_number`
- `created_by` (FK -> `app_users.id`, nullable)
- `created_at`, `updated_at`

Used in:
- Fund Request list/detail/draft/submit/reopen flows.

### `fund_request_recipients` (Model: `FundRequestRecipient`)

Purpose:
- Aid-mode detail rows within a fund request.

Columns:
- `id`
- `fund_request` (FK -> `fund_request.id`)
- `beneficiary_type`
- `source_entry_id`
- `beneficiary`
- `recipient_name`
- `name_of_beneficiary`
- `name_of_institution`
- `details`
- `fund_requested`
- `aadhar_number`
- `address`
- `cheque_in_favour`
- `cheque_no`
- `notes`
- `district_name`
- `created_at`, `updated_at`

Used in:
- Aid request row editing, validation, duplicate Aadhaar checks.

### `fund_request_articles` (Model: `FundRequestArticle`)

Purpose:
- Article-mode line items within a fund request.

Columns:
- `id`
- `fund_request` (FK -> `fund_request.id`)
- `article` (FK -> `articles.id`)
- `vendor` (FK -> `vendors.id`, nullable)
- `sl_no`
- `beneficiary`
- `article_name`
- `vendor_name`
- `gst_no`
- `vendor_address`, `vendor_city`, `vendor_state`, `vendor_pincode`
- `quantity`
- `unit_price`
- `price_including_gst`
- `value`
- `cumulative`
- `cheque_in_favour`
- `cheque_no`
- `supplier_article_name`
- `description`
- `created_at`, `updated_at`

Used in:
- Article procurement request building and exports.

### `fund_request_documents` (Model: `FundRequestDocument`)

Purpose:
- Generated/uploaded docs linked to a fund request.

Columns:
- `id`
- `fund_request` (FK -> `fund_request.id`)
- `document_type`
- `file_path`
- `file_name`
- `generated_at`
- `generated_by` (FK -> `app_users.id`, nullable)
- `created_at`, `updated_at`

Used in:
- PDF/XLS exports and document audit trail.

### `purchase_order` (Model: `PurchaseOrder`)

Purpose:
- Purchase order header.

Columns:
- `id`
- `purchase_order_number` (unique, nullable)
- `status`
- `vendor_name`
- `gst_number`
- `vendor_address`, `vendor_city`, `vendor_state`, `vendor_pincode`
- `comments`
- `total_amount`
- `created_by` (FK -> `app_users.id`, nullable)
- `created_at`, `updated_at`

Used in:
- Purchase Order module.

### `purchase_order_items` (Model: `PurchaseOrderItem`)

Purpose:
- Purchase order line items.

Columns:
- `id`
- `purchase_order` (FK -> `purchase_order.id`)
- `article` (FK -> `articles.id`)
- `article_name`
- `supplier_article_name`
- `description`
- `quantity`
- `unit_price`
- `total_value`
- `created_at`, `updated_at`

Used in:
- PO detail and exports.

### `order_entries` (Model: `OrderEntry`)

Purpose:
- Order/inventory planning records.

Columns:
- `id`
- `article` (FK -> `articles.id`)
- `quantity_ordered`
- `order_date`
- `status`
- `supplier_name`
- `supplier_contact`
- `unit_price`
- `total_amount`
- `expected_delivery_date`
- `notes`
- `created_by` (FK -> `app_users.id`, nullable)
- `fund_request` (FK -> `fund_request.id`, nullable)
- `created_at`, `updated_at`

Used in:
- Inventory planning and order tracking.

---

## 5) Event Session + Phase-2 Pipeline

### `event_sessions` (Model: `EventSession`)

Purpose:
- Session anchor for phase-2 data and reconciliation snapshots.

Columns:
- `id`
- `session_name` (unique)
- `event_year`
- `is_active`
- `notes`
- `phase2_source_name`
- `phase2_source_row_count`
- `phase2_grouped_row_count`
- `phase2_source_quantity_total`
- `phase2_grouped_quantity_total`
- `phase2_reconciliation_snapshot` (JSON)
- `created_at`, `updated_at`

Used in:
- Seat Allocation, Sequence List, Token Generation, Labels, Reports.

### `seat_allocation_rows` (Model: `SeatAllocationRow`)

Purpose:
- Canonical seat-allocation dataset rows for a session.

Columns:
- `id`
- `session` (FK -> `event_sessions.id`)
- `source_file_name`
- `application_number`
- `beneficiary_name`
- `district`
- `requested_item`
- `quantity`
- `waiting_hall_quantity`
- `token_quantity`
- `beneficiary_type`
- `item_type`
- `comments`
- `master_row` (JSON)
- `master_headers` (JSON)
- `sort_order`
- `sequence_no`
- `created_by` / `updated_by` (FK -> `app_users.id`, nullable)
- `created_at`, `updated_at`

Used in:
- Seat allocation reconciliation and sync source for sequence list.

### `sequence_list_items` (Model: `SequenceListItem`)

Purpose:
- Item-to-sequence mapping for each session.

Columns:
- `id`
- `session` (FK -> `event_sessions.id`)
- `item_name`
- `sequence_no`
- `sort_order`
- `created_by` / `updated_by` (FK -> `app_users.id`, nullable)
- `created_at`, `updated_at`

Used in:
- Sequence assignment UI; source for token-generation sync.

### `token_generation_rows` (Model: `TokenGenerationRow`)

Purpose:
- Final token-generated master rows (source of truth for reports/labels sync).

Columns:
- `id`
- `session` (FK -> `event_sessions.id`)
- `source_file_name`
- `application_number`
- `beneficiary_name`
- `requested_item`
- `beneficiary_type`
- `sequence_no`
- `start_token_no`
- `end_token_no`
- `row_data` (JSON full row)
- `headers` (JSON)
- `sort_order`
- `created_by` / `updated_by` (FK -> `app_users.id`, nullable)
- `created_at`, `updated_at`

Used in:
- Token Generation module + Sync source for Labels and Reports.

### `label_generation_rows` (Model: `LabelGenerationRow`)

Purpose:
- Labels module synchronized snapshot from token-generation rows.

Columns:
- `id`
- `session` (FK -> `event_sessions.id`)
- `source_file_name`
- `application_number`
- `beneficiary_name`
- `requested_item`
- `beneficiary_type`
- `sequence_no`
- `start_token_no`
- `end_token_no`
- `row_data` (JSON full row)
- `headers` (JSON)
- `sort_order`
- `created_by` / `updated_by` (FK -> `app_users.id`, nullable)
- `created_at`, `updated_at`

Used in:
- Labels module for stable previews/downloads.

---

## 6) Dashboard + Audit

### `dashboard_settings` (Model: `DashboardSetting`)

Purpose:
- Dashboard-level budget setting.

Columns:
- `id`
- `event_budget`
- `updated_by` (FK -> `app_users.id`, nullable)
- `created_at`, `updated_at`

Used in:
- Dashboard totals/planning calculations.

### `audit_logs` (Model: `AuditLog`)

Purpose:
- Action audit trail across modules.

Columns:
- `id`
- `user` (FK -> `app_users.id`, nullable)
- `action_type`
- `entity_type`
- `entity_id`
- `details` (JSON)
- `ip_address`
- `user_agent`
- `created_at`, `updated_at`

Used in:
- Audit Logs module and change tracing.

---

## Reports/Labels Sync Safety Notes

- Reports (Segregation, Stage Distribution) sync creates a session-scoped snapshot in `request.session` state keys:
  - `reports_segregation`
  - `reports_distribution`
- Labels sync stores a DB snapshot in `label_generation_rows`.
- In both cases, source token rows in `token_generation_rows` are not mutated by filters/previews/downloads.

## Suggested Reading Order for New Developers

1. `core/models.py`
2. `core/application_entry/views.py`
3. `core/order_fund_request/views.py`
4. `core/seat_allocation/views.py`
5. `core/sequence_list/views.py`
6. `core/token_generation/views.py`
7. `core/labels/services.py`
8. `core/reports/views.py` + `core/reports/services.py`
