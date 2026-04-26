# Vendors

## What this module is

Vendors stores supplier data used by purchase and order workflows.

## Main code files

- Views: `core/vendors/views.py`
- URLs: `core/vendors/urls.py`
- Templates: `core/templates/vendors/`
- Model: `Vendor`

## Main table

- `vendors`

## Important fields

- `vendor_name`: supplier display name.
- `gst_number`: GST identifier.
- `phone_number`
- `address`, `city`, `state`, `pincode`
- `cheque_in_favour`
- `is_active`

## Data flow

- Vendor records are selected in Purchase Order and Article request flows.
- Vendor names and cheque details appear in generated documents.

## Debug checklist

- Vendor missing in dropdown: check `is_active`.
- Duplicate-looking vendor: compare GST number and normalized vendor name.
- Purchase document has wrong address: inspect saved purchase order vendor fields, because documents may use copied values.

## Form fields

- Vendor name: primary supplier name.
- GST number: tax identifier.
- Phone number: contact number.
- Address, city, state, pincode: address fields.
- Cheque in favour: payment name.
- Active: controls whether vendor appears in selectable lists.

## Buttons and actions

- Create adds a vendor.
- Edit updates vendor details.
- Delete removes vendor when allowed.
- Export downloads vendor master data.
- Clear All resets filters.

## Common errors and fixes

- Vendor changed but PO still old: purchase orders may store copied vendor details at creation time.
- GST search not working: inspect normalization and search query.
- Delete blocked: check references in fund request articles or purchase orders.
