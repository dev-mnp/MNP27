# Labels & Tags

## What this module is

Labels & Tags creates printable PDF labels from token-generated rows.

## Main code files

- View: `core/labels/views.py`
- URLs: `core/labels/urls.py`
- Templates: `core/templates/labels/`
- Models: `LabelGenerationRow`, `TokenGenerationRow`, `EventSession`

## Main tables

- `label_generation_rows`
- `token_generation_rows`
- `event_sessions`

## Important fields

- `LabelGenerationRow.application_number`
- `LabelGenerationRow.beneficiary_name`
- `LabelGenerationRow.requested_item`
- `LabelGenerationRow.beneficiary_type`
- `LabelGenerationRow.sequence_no`
- `LabelGenerationRow.start_token_no`
- `LabelGenerationRow.end_token_no`
- `LabelGenerationRow.row_data`

## Data flow

- Sync Data copies final token-generated rows into label-stage rows.
- Preview and download use the same label-stage data.
- Article labels, Public labels, Institution labels, Others labels, and District labels filter from this source.

## Debug checklist

- Excluded token row appears in label: check whether labels were synced after exclusion.
- Unknown filename from preview: inspect preview download response filename.
- Others showing under Institution: check label type filter.
- Token range wrong: inspect copied `start_token_no` and `end_token_no`.

## Label sections and fields

- Article labels: item labels for physical articles.
- District labels: district beneficiary labels.
- Public labels: public beneficiary labels.
- Institution labels: institution labels.
- Others labels: others beneficiary labels.
- Chair/custom labels: special operational labels.
- Rows, expected, generated, tokens, duplicates, invalid, and pages are status counters.

## Buttons and actions

- Sync Data copies from Token Generation into Labels.
- Upload replaces label-stage source data.
- Preview opens PDF preview.
- Download downloads the final PDF.

## Common errors and fixes

- Preview and download differ: make both paths use the same filtered row builder.
- Button disabled with rows present: check validation summary counters.
- Duplicate labels: inspect token ranges and source row duplication.
- Others label says unknown type: add Others to label type dispatch.
