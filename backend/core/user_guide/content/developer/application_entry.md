# Application Entry

## What this module is

Application Entry is the source of beneficiary demand. Most later modules depend on these records, so this module is the first place to debug wrong beneficiary names, item names, quantities, values, Aadhaar state, and attachments.

## Main code files

- Views: `core/application_entry/views.py`
- URLs: `core/application_entry/urls.py`
- Templates: `core/templates/application_entry/`
- Attachment service: `core/services/attachment_service.py`
- Google Drive helper: `core/services/google_drive.py`
- Shared models: `core/models.py`

## Main tables

- `district_master`: district reference and budget.
- `district_beneficiary_entries`: district requested items.
- `public_beneficiary_entries`: public beneficiary records.
- `institutions_beneficiary_entries`: institution beneficiary records.
- `others_beneficiary_entries`: others beneficiary records.
- `application_attachments`: Google Drive/file links for applications.
- `articles`: article, aid, and project master.
- `public_beneficiary_history`: past-year public history used for verification.

## Key models and fields

- `DistrictMaster`: `district_name`, `application_number`, `allotted_budget`, `president_name`, `mobile_number`, `is_active`.
- `DistrictBeneficiaryEntry`: `district_id`, `application_number`, `article_id`, `quantity`, `total_amount`, `name_of_beneficiary`, `name_of_institution`, `aadhar_number`, `status`.
- `PublicBeneficiaryEntry`: `application_number`, `name`, `aadhar_number`, `aadhaar_status`, `is_handicapped`, `gender`, `female_status`, `article_id`, `quantity`, `total_amount`, `status`, `archived_*`.
- `InstitutionsBeneficiaryEntry`: `institution_name`, `institution_type`, `application_number`, `article_id`, `quantity`, `total_amount`, `status`.
- `OthersBeneficiaryEntry`: same operating fields as Institution, but stored separately in `others_beneficiary_entries`.
- `ApplicationAttachment`: `application_type`, `application_id`, `draft_uid`, `drive_file_id`, `drive_view_url`, `status`, `form_token`.

## Numbering rules

- Public uses public application numbers.
- Institution uses the institution number series.
- Others uses the others number series starting with `O`.
- District application rows are tied to `district_master.application_number`.

## Dirty state and save behavior

- The browser form should compare current normalized form state with the last saved baseline.
- Fields, item rows, and attachments must all feed one final dirty flag.
- After Save as Draft succeeds, the current state becomes the new baseline.
- Cancel should warn only if current state differs from the latest saved baseline.

## Attachment behavior

- Upload happens immediately to Drive.
- Save Draft or Submit links uploaded files to the application.
- Deleting should remove the app link and delete the Drive file when applicable.
- Others attachments must use `application_type = others`, not institution.

## Downstream impact

- Submitted application rows feed Inventory Planning and later stage exports.
- Public Aadhaar state feeds Fund Request validation.
- Wrong article price or item type here will affect planning, seat allocation, reports, labels, and exports.

## Debug checklist

- If Others appears under Institution, check query filters and `RecipientTypeChoices`.
- If an attachment shows in UI but not Drive, inspect `application_attachments.drive_file_id`.
- If a Drive file exists but not UI, inspect whether the attachment is still `TEMP` or linked to the wrong `application_type`.
- If Save as Draft stays active, compare baseline snapshot with current snapshot.
- If Aadhaar verification behaves wrongly, inspect `public_beneficiary_entries.aadhaar_status` and `public_beneficiary_history`.

## Form fields by beneficiary type

- District fields: district, application number, president name, mobile number, allotted budget, remaining fund, item rows, aid details, notes, internal notes, attachments.
- Public fields: name, Aadhaar number, Aadhaar not available, gender, female status, handicapped status, disability category, address, mobile, article/aid, quantity, cost, total, institution name, cheque/RTGS in favour, notes, attachments.
- Institution fields: institution name, application number, address, mobile, item rows, aid details, notes, internal notes, attachments.
- Others fields: same operating fields as Institution, but saved in `others_beneficiary_entries` and numbered with the O-series.
- Item row fields: article, item type, cost per unit, quantity, total amount, item comes here, beneficiary name, institution name, Aadhaar, cheque/RTGS in favour, details/notes.

## Buttons and actions

- Save as Draft writes an editable record and refreshes the dirty-state baseline.
- Submit marks the record ready for downstream modules.
- Cancel returns to the overview and should warn only when unsaved changes exist.
- Add Item creates a new item row in forms that support multiple items.
- Edit Item updates a row and should activate Save as Draft.
- Delete Item removes a row and should activate Save as Draft.
- Add Attachment uploads the file and prepares it for linking.
- Delete Attachment removes the UI link and should remove the Drive file when the attachment belongs to that application.
- Archive hides a public application from active working lists without permanently deleting it.
- Unarchive restores an archived public application.
- Export downloads application data in the current overview format.

## Common errors and fixes

- Save button always active: compare normalized strings, numbers, nulls, item rows, and attachment rows against the saved baseline.
- Save button never active: check event listeners on item and attachment changes.
- Cancel warns after save: baseline was not refreshed after successful draft save.
- Attachment uploaded but not shown: check `draft_uid`, `form_token`, `application_type`, and `application_id`.
- Others attachment saved in institution folder: check Drive folder resolver and `ApplicationAttachment.application_type`.
- Public duplicate Aadhaar not blocked: check normalized Aadhaar and `aadhaar_status`.
- Wrong application number series: inspect number generation function for selected beneficiary type.
