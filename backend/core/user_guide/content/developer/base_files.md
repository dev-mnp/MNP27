# Base Files

## What this module is

Base Files stores reference data used by Application Entry and verification. It is not the same as transactional application data.

## Main code files

- Views: `core/base_files/views.py`
- URLs: `core/base_files/urls.py`
- Templates: `core/templates/base_files/`
- Models: `DistrictMaster`, `Article`, `PublicBeneficiaryHistory`

## Main tables

- `district_master`
- `articles`
- `public_beneficiary_history`

## Important fields

- `DistrictMaster.district_name`, `application_number`, `allotted_budget`, `president_name`, `mobile_number`, `is_active`.
- `Article.article_name`, `article_name_tk`, `cost_per_unit`, `item_type`, `category`, `master_category`, `is_active`, `combo`.
- `PublicBeneficiaryHistory.aadhar_number`, `name`, `year`, `article_name`, `application_number`, `gender`, `category`.

## Data flow

- District master feeds district application setup.
- Article list feeds Article Management and item selection.
- Public beneficiary history feeds Aadhaar verification.

## Debug checklist

- District missing in application entry: inspect `district_master.is_active`.
- Article dropdown wrong: inspect `articles.is_active` and `item_type`.
- Aadhaar history not found: inspect normalized Aadhaar in `public_beneficiary_history`.
- Upload changed app behavior: compare uploaded column names with parser expectations.

## Screen fields and upload columns

- District file should provide district name, application number, president name, mobile number, and allotted budget.
- Article file should provide article name, token name, cost, item type, category, master category, active state, and combo state.
- Public history file should provide Aadhaar number, name, year, article name, application number, and available demographic/reference fields.

## Buttons and actions

- Upload imports or replaces the selected base file.
- Download template or export downloads the current reference file where available.
- Replace should be treated as a controlled action because downstream modules depend on these tables.

## Common errors and fixes

- Upload succeeds but rows empty: check header names and parser mapping.
- Numeric values wrong: inspect comma/rupee formatting before Decimal conversion.
- Duplicate article import: check unique `article_name`.
- Duplicate district import: check unique `district_name`.
