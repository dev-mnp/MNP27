# Inventory Planning

## What this module is

Inventory Planning is the demand and ordering monitor. It aggregates submitted application demand by item and compares it with ordered quantities from fund/order workflows.

## Main code files

- View: `core/inventory_planning/views.py`
- URLs: `core/inventory_planning/urls.py`
- Template: `core/templates/inventory_planning/order_management.html`
- Models used: beneficiary entry tables, `Article`, `OrderEntry`, `FundRequest`, `FundRequestArticle`

## Main tables

- `district_beneficiary_entries`
- `public_beneficiary_entries`
- `institutions_beneficiary_entries`
- `others_beneficiary_entries`
- `articles`
- `order_entries`
- `fund_request_articles`

## Important fields

- Beneficiary rows: `article_id`, `quantity`, `total_amount`, `status`, `fund_request_id`.
- `Article.item_type`: splits Article, Aid, Project.
- `OrderEntry.quantity_ordered`: manual/legacy ordered quantity.
- `FundRequestArticle.quantity`: article request quantity.
- `FundRequest.status`: only submitted requests should affect ordered state.

## Aggregation logic

- Needed quantity comes from submitted beneficiary application rows.
- Ordered quantity comes from submitted order/fund request rows.
- Pending equals needed minus ordered.
- Excess appears when ordered is greater than needed.
- Expanded rows should keep District, Public, Institution, and Others understandable.

## Performance rules

- Use `annotate()` and `aggregate()` wherever possible.
- Avoid looping through every application row in Python for totals.
- Use `select_related()` for `article` and `fund_request` when expanding details.
- Use `prefetch_related()` only when the UI needs child rows.

## Debug checklist

- Needed quantity wrong: inspect submitted application rows by article.
- Ordered wrong: inspect submitted `fund_request_articles` and linked `order_entries`.
- Others mixed with Institutions: check grouping code and beneficiary type labels.
- Export mismatch: compare filtered queryset used by screen and export.

## Screen fields

- Search: filters by article, beneficiary, category, or related text.
- Item type filter: Article, Aid, Project, or all.
- Application status filter: controls which source application statuses are included.
- Combo filter: separates combo and non-combo articles.
- Order status filter: filters pending/ordered/completed states.
- Balance filter: focuses pending, excess, or completed rows.
- Expanded beneficiary rows: show source application, beneficiary type, beneficiary name, quantity, value, and order status.

## Buttons and actions

- Sync or refresh controls recalculate the planning view from current source data if present.
- Expand row reveals beneficiary-level details.
- Export downloads the currently filtered planning view.
- Clear All resets filters.

## Common errors and fixes

- Pending negative: ordered quantity is greater than needed; show as excess instead of hiding it.
- Expanded count differs from summary: check aggregation grouping keys.
- Others absent in expanded view: inspect source union or query combining beneficiary models.
- Page slow with many rows: aggregate in DB and load expanded rows only when requested.
