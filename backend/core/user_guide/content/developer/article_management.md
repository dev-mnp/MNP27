# Article Management

## What this module is

Article Management stores the master list of Aid, Article, and Project items. Application Entry and later reports rely on this table for item names, token names, item type, category, master category, cost, and combo state.

## Main code files

- Views: `core/article_management/views.py`
- URLs: `core/article_management/urls.py`
- Templates: `core/templates/article_management/`
- Model: `Article` in `core/models.py`

## Main table

- `articles`

## Important fields

- `article_name`: unique user-facing item name.
- `article_name_tk`: token name used in token and label outputs.
- `cost_per_unit`: default price.
- `item_type`: `Article`, `Aid`, or `Project`.
- `category`: operational category.
- `master_category`: higher-level category.
- `is_active`: controls whether the item should be selectable.
- `combo`: marks combo/separate behavior.

## Price rule

- `cost_per_unit = 0` means price can be edited in Application Entry.
- `cost_per_unit > 0` means the item price is fixed.
- Price updates can affect saved application rows, so the UI asks for confirmation before updating matching rows.

## Data flow

- Base Files can seed article data.
- Application Entry reads active articles.
- Inventory Planning aggregates by article.
- Sequence List, Token Generation, Labels, and Reports use article/token names from downstream staged data.

## Debug checklist

- Duplicate warning missing: check article and token duplicate validation in create/edit views.
- Price not editable in Application Entry: inspect `cost_per_unit`.
- Item not visible in dropdown: check `is_active`, item type, and filters.
- Category autocomplete empty: check distinct `category` and `master_category` values in `articles`.

## Form fields

- Item type: decides whether the row is Aid, Article, or Project.
- Article name: main item name used across the app.
- Token name: shorter name used in tokens, labels, and compact reports.
- Cost per unit: default price.
- Category: operational grouping.
- Master category: higher-level grouping.
- Active: whether the item should be selectable.
- Combo: marks combo/separate handling.

## Buttons and actions

- Create opens the add form.
- Save creates or updates the article record.
- Cancel returns to the list without saving.
- Edit opens the selected record.
- Delete removes the selected article when allowed.
- Export downloads the article master.
- Clear All resets filters.

## Common errors and fixes

- Duplicate warning appears under field instead of notification: check form error display and toast/notification code.
- Create popup not matching edit page: compare popup fields and classes with the full form.
- Action buttons drift: inspect table column widths and action cell flex alignment.
- Price impact modal count wrong: inspect matching rows across district, public, institution, and others entry tables.
