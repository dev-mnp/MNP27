# Token Generation

## What this module is

Token Generation creates the final token-stage working data. Reports and Labels should use this data after optional exclusions.

## Main code files

- View: `core/token_generation/views.py`
- URLs: `core/token_generation/urls.py`
- Templates: `core/templates/token_generation/`
- Models: `TokenGenerationRow`, `SequenceListItem`, `SeatAllocationRow`, `EventSession`

## Main tables

- `token_generation_rows`
- `sequence_list_items`
- `seat_allocation_rows`
- `event_sessions`

## Important fields

- `TokenGenerationRow.application_number`
- `TokenGenerationRow.beneficiary_name`
- `TokenGenerationRow.requested_item`
- `TokenGenerationRow.beneficiary_type`
- `TokenGenerationRow.sequence_no`
- `TokenGenerationRow.start_token_no`
- `TokenGenerationRow.end_token_no`
- `TokenGenerationRow.row_data`: full token export row JSON.
- `TokenGenerationRow.headers`: header order for export.

## Data flow

- Sync Data reads Seat Allocation and Sequence List.
- Optional transformations can exclude rows.
- Token numbers are assigned using token quantity.
- Labels and Reports sync from token-generated data.

## Important logic

- Token numbers belong to Token quantity, not Waiting Hall quantity.
- Rows excluded during optional transformation should not appear in Labels or Reports.
- Empty token datasets must be handled gracefully.

## Debug checklist

- `min() arg is an empty sequence`: ensure empty token row lists are handled before calling min/max.
- Wrong totals in reports: compare `row_data` quantities with report filters.
- Missing Others: check `beneficiary_type` in `token_generation_rows`.
- Token range empty: check token quantity in `row_data`.

## Screen fields and columns

- Application number: source application number.
- Beneficiary name: person, district, institution, or others name.
- Names: display name used in token output.
- Requested item: item name.
- Item type: Article, Aid, or Project.
- Beneficiary type: District, Public, Institutions, or Others.
- Sequence number: item order from Sequence List.
- Start Token No and End Token No: generated token range.
- Token quantity: quantity receiving token numbers.
- Waiting Hall quantity: quantity excluded from token numbering.

## Buttons and actions

- Sync Data creates token-stage rows from Sequence List and Seat Allocation.
- Upload replaces token-stage rows from an external file.
- Filter Rows applies optional transformation filters.
- Exclude Selected removes selected rows from final token-stage output.
- Generate Token creates start/end token ranges.
- Export downloads final token data.

## Common errors and fixes

- Excluded rows still in reports: sync reports again or inspect report source query.
- Optional transformation cannot restore excluded rows: use the original sync/upload source again if needed.
- Token quantity zero but token number present: inspect whether the row has mixed waiting and token quantities.
- Export columns missing: check `headers` and `row_data`.
