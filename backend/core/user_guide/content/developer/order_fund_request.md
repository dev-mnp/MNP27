# Order & Fund Request

## What this module is

Order & Fund Request creates Aid fund requests and Article order requests. Submitted requests affect ordered quantities and duplicate Aadhaar checks.

## Main code files

- Views: `core/order_fund_request/views.py`
- URLs: `core/order_fund_request/urls.py`
- Templates: `core/templates/order_fund_request/`
- Models: `FundRequest`, `FundRequestRecipient`, `FundRequestArticle`, `FundRequestDocument`, `Vendor`

## Main tables

- `fund_request`
- `fund_request_recipients`
- `fund_request_articles`
- `fund_request_documents`
- `vendors`
- Beneficiary source tables for quick populate

## Important fields

- `FundRequest.fund_request_type`: `Aid` or `Article`.
- `FundRequest.fund_request_number`: formatted as `FR-001`, `FR-002`, etc.
- `FundRequest.status`: `draft` or `submitted`.
- `FundRequest.total_amount`: request total.
- `FundRequestRecipient.beneficiary_type`: District, Public, Institutions, or Others.
- `FundRequestRecipient.source_entry_id`: original beneficiary row id.
- `FundRequestRecipient.aadhar_number`: used for duplicate checks.
- `FundRequestArticle.vendor_id`, `article_id`, `quantity`, `unit_price`, `value`.

## Data flow

- Aid quick populate reads eligible application beneficiary rows.
- Article requests group item rows under vendors.
- Submit finalizes the request and affects Inventory Planning ordered quantities.
- Submitted Aadhaar values are checked against future draft submissions.

## Important validation

- Public rows with Aadhaar not available should block save/submit in fund request.
- District, Institution, and Others Aadhaar are not verified the same way as Public.
- Duplicate Aadhaar warnings compare draft rows against submitted fund requests.

## Debug checklist

- Quick Populate empty: check beneficiary source query, item type, aid type, and status.
- Others appears in Institutions: check `beneficiary_type` and source table mapping.
- Duplicate Aadhaar not detected: inspect submitted `fund_request_recipients.aadhar_number`.
- Counts wrong on list page: Aid count counts recipients; Article count counts article item rows.

## Form fields

- Request type: Aid or Article.
- Aid: selected when request type is Aid.
- Beneficiary filter: limits quick populate to District, Public, Institution, Others, or All.
- Beneficiary type: stored recipient type for each row.
- Beneficiary: selected source application row.
- Fund requested: aid amount requested.
- Name of beneficiary, name of institution, Aadhaar number, details, cheque/RTGS in favour: copied or edited recipient details.
- Article request fields: vendor, article, quantity, unit price, GST, supplier article name, description, cheque details.

## Buttons and actions

- Create starts a new request.
- Save as Draft stores editable request data.
- Submit finalizes the request and updates downstream ordered state.
- Quick Populate adds selected source beneficiaries.
- Reset clears quick populate selections.
- Delete row removes a recipient or article row from the draft.
- Delete request removes the request where allowed.
- Download exports the request document.
- Reopen returns a submitted request to editable state where permission allows.

## Common errors and fixes

- Submit accepted duplicate Aadhaar: check draft Aadhaar normalization and submitted recipient query.
- Public Aadhaar pending not blocked: check source `aadhaar_status` and warning flag.
- Beneficiary dropdown still editable after quick populate: lock beneficiary type and beneficiary fields after selection.
- Submit confirmation missing: inspect submit form handler.
- Ordered quantity not reflected in Inventory Planning: check submitted status and linked article rows.
