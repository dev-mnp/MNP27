# Dashboard

## What this module is

Dashboard is a read-only summary module. It helps users quickly understand whether application counts, fund values, planning values, and post-seat-allocation quantity/value trees look correct.

## Main code files

- View: `core/dashboard/views.py`
- Template: `core/templates/dashboard/dashboard.html`
- Shared menu and permissions display: `templates/base.html`
- Models used: `DashboardSetting`, beneficiary entry tables, fund request tables, seat allocation rows

## Main tables

- `dashboard_settings`: stores event-level dashboard settings such as event budget.
- `district_beneficiary_entries`: district application demand.
- `public_beneficiary_entries`: public application demand.
- `institutions_beneficiary_entries`: institution application demand.
- `others_beneficiary_entries`: others application demand.
- `fund_request`, `fund_request_recipients`, `fund_request_articles`: submitted fund/order totals.
- `seat_allocation_rows`: source for quantity and value tree after allocation.

## Important fields

- `DashboardSetting.event_budget`: configured event budget.
- Beneficiary tables use `quantity`, `total_amount`, `status`, `article_id`, and `fund_request_id`.
- `seat_allocation_rows.quantity`: original quantity copied into allocation stage.
- `seat_allocation_rows.waiting_hall_quantity`: quantity handled in waiting hall.
- `seat_allocation_rows.token_quantity`: quantity handled through token/stage.
- `seat_allocation_rows.master_row`: JSON copy of the source export row.

## Data flow

- Application Entry creates source application rows.
- Order & Fund Request updates ordering/fund request state.
- Seat Allocation creates the allocation-stage split.
- Dashboard reads these sources and shows totals. It should not update source rows.

## Permissions

- Module key: `dashboard`
- Actions: `view`, `view_page_2`
- Page 2 tree access is controlled by `can_view_page_2`.

## Debug checklist

- If a dashboard number is wrong, identify which source table feeds that card.
- Check whether archived or draft rows are included or excluded as expected.
- For tree totals, inspect `seat_allocation_rows` for the active event session.
- Use database aggregation, not Python row loops, for heavy totals.
- If a user cannot see dashboard page 2, check `user_module_permissions.can_view_page_2`.

## Buttons and UI fields

- Page arrows move between dashboard summary pages. They do not change data.
- Total cards show calculated values only. They should not contain save logic.
- Quantity tree shows total quantity, beneficiary type split, item type split, Waiting Hall quantity, and Token quantity.
- Value tree follows the same structure as quantity tree but shows calculated values.

## Common errors and fixes

- `column waiting_value does not exist`: do not aggregate a database column that is not stored. Calculate waiting/token values from stored quantity and value fields or JSON data.
- Tree page is empty: check whether Seat Allocation has synced data.
- Dashboard slow: replace Python loops with `values().annotate()` and `aggregate()`.
- Wrong beneficiary split: inspect whether Others is being grouped with Institutions accidentally.
