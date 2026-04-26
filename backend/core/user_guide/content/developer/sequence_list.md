# Sequence List

## What this module is

Sequence List assigns one order number to each unique item. Token Generation uses this order to produce token-stage rows.

## Main code files

- View: `core/sequence_list/views.py`
- URLs: `core/sequence_list/urls.py`
- Templates: `core/templates/sequence_list/`
- Models: `EventSession`, `SequenceListItem`, `SeatAllocationRow`

## Main tables

- `sequence_list_items`
- `seat_allocation_rows`
- `event_sessions`

## Important fields

- `SequenceListItem.item_name`: unique requested item.
- `SequenceListItem.sequence_no`: final sequence number.
- `SequenceListItem.sort_order`: UI/order helper.
- Unique constraints prevent duplicate item names and duplicate sequence numbers per session.

## Data flow

- Sync Data reads unique requested items from Seat Allocation.
- User orders the items.
- Save stores `sequence_list_items`.
- Token Generation joins rows with sequence values.

## Debug checklist

- Save failing after upload: inspect duplicate `sequence_no` or duplicate `item_name`.
- Item missing: check whether item exists in `seat_allocation_rows`.
- Others item missing: check Seat Allocation beneficiary type and item sync query.
- Sequence mismatch: inspect unique constraints and saved sort order.

## Screen fields

- Start From: starting sequence number for auto-numbering.
- Include only Token Quantity > 0: limits sequence candidates to items with token quantity.
- Unassigned Items: items not yet sequenced.
- Sequenced Items: ordered items with sequence numbers.
- Search items: filters visible item names.
- Category dropdown: filters by article category when available.

## Buttons and actions

- Sync Data copies unique items from Seat Allocation.
- Move right assigns selected items to sequence list.
- Move left removes selected items from sequence list.
- Sort by Item sorts sequenced items alphabetically.
- Undo reverts the last ordering action where supported.
- Reset clears unsaved sequence changes.
- Save stores sequence numbers.
- Upload replaces sequence working data from file.
- Export downloads the sequence list.

## Common errors and fixes

- Save button hidden: check toolbar layout and overflow.
- Sequence item list too short visually: adjust list container height, not data logic.
- Duplicate sequence number: check `uniq_sequence_no_per_session`.
- Duplicate item name: check `uniq_sequence_item_per_session`.
