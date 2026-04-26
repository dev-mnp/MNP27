# Seat Allocation

## Purpose

Seat Allocation splits each approved requirement into Waiting Hall quantity and Token quantity.

## How to use

- Use Sync Data to copy the full master data into Seat Allocation.
- Use filters to focus on a beneficiary type, item type, or item.
- Enter Waiting Hall quantity and Token quantity.
- Save when the split is correct.
- Export when allocation is ready for the next stage.

## System behavior

- Sync Data creates a working copy for this stage.
- It does not edit Application Entry directly.
- Waiting Hall quantity plus Token quantity should match the original total quantity.
- Others is handled separately from Institutions where beneficiary-specific detail is shown.
