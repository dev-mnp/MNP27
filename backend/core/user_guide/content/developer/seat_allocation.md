# Seat Allocation

## What this module is

Seat Allocation creates a stage working copy from master application data and splits each row into Waiting Hall quantity and Token quantity.

## Main code files

- View: `core/seat_allocation/views.py`
- URLs: `core/seat_allocation/urls.py`
- Templates: `core/templates/seat_allocation/`
- Shared phase helpers: `core/shared/phase2.py`
- Models: `EventSession`, `SeatAllocationRow`

## Main tables

- `event_sessions`
- `seat_allocation_rows`

## Important fields

- `EventSession.is_active`: only one active event session.
- `EventSession.phase2_*`: source row counts, grouped counts, and reconciliation snapshot.
- `SeatAllocationRow.application_number`
- `SeatAllocationRow.beneficiary_name`
- `SeatAllocationRow.requested_item`
- `SeatAllocationRow.quantity`
- `SeatAllocationRow.waiting_hall_quantity`
- `SeatAllocationRow.token_quantity`
- `SeatAllocationRow.beneficiary_type`
- `SeatAllocationRow.item_type`
- `SeatAllocationRow.master_row`: original source row JSON.

## Data flow

- Sync Data copies the current master export into `seat_allocation_rows`.
- User edits waiting/token split.
- Sequence List syncs from Seat Allocation.

## Debug checklist

- Sync missing rows: check source master export generation and `phase2_source_row_count`.
- Split mismatch: compare `quantity` with `waiting_hall_quantity + token_quantity`.
- Others filter empty: inspect `beneficiary_type = Others`.
- Export missing columns: inspect `master_headers` and `master_row`.

## Screen fields and columns

- Application number: source application number.
- Beneficiary name: source beneficiary display name.
- District: district or related location value.
- Requested item: item being allocated.
- Quantity: total source quantity.
- Waiting Hall quantity: quantity handled without token.
- Token quantity: quantity going to token/stage.
- Beneficiary type: District, Public, Institutions, or Others.
- Item type: Article, Aid, or Project.
- Comments: optional operational note.

## Buttons and actions

- Sync Data copies current master data into seat allocation rows.
- Upload replaces the seat allocation working copy from a file.
- Save persists waiting/token split.
- Export downloads the stage data.
- Filter controls narrow rows without changing data.

## Common errors and fixes

- `waiting + token` does not equal quantity: fix the split before moving to Sequence List.
- Sync copied only some rows: check source export and any accidental filter during sync.
- Others appears inside Institutions filter: check beneficiary type normalization.
- Uploaded file save fails: check required columns and numeric parsing.
