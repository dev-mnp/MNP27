# Application Entry

## Purpose

Application Entry is the source truth for all beneficiary applications. District, Public, Institution, and Others records are created here.

## How to use

- Choose the beneficiary type from Application Entry.
- Create the application and fill required beneficiary details.
- Add requested item rows where the form allows multiple items.
- Add attachments if supporting documents are available.
- Save as Draft when the record is incomplete.
- Submit only when the application is ready for downstream stages.

## Draft and change behavior

- Save as Draft keeps the record editable.
- The Save as Draft button becomes active when fields, item rows, or attachments change.
- After a successful draft save, the current saved data becomes the new baseline.
- Cancel should warn only when there are unsaved changes after the latest save.

## Attachments

- Attachments upload to Google Drive when added.
- The application stores the file link.
- Attachments are stored under their beneficiary type folder.
- Deleted attachments should no longer remain linked to the application.

## Public Aadhaar behavior

- Public records can be verified by Aadhaar.
- Aadhaar not available can be selected when the number is not available at entry time.
- Those records remain verification pending for fund request until Aadhaar is verified.

## Others

- Others is a separate beneficiary type.
- Others uses its own application number series starting with O.
- Others follows the Institution-style form and item logic, but it is not stored as Institution.
