# Purchase Order

## What this module is

Purchase Order creates vendor-facing purchase order documents. It is separate from Order & Fund Request.

## Main code files

- Views: `core/purchase_order/views.py`
- URLs: `core/purchase_order/urls.py`
- Templates: `core/templates/purchase_order/`
- Models: `PurchaseOrder`, `PurchaseOrderItem`, `Article`, `Vendor`

## Main tables

- `purchase_order`
- `purchase_order_items`
- `articles`
- `vendors`

## Important fields

- `PurchaseOrder.purchase_order_number`: unique PO number.
- `PurchaseOrder.status`: draft or submitted.
- `PurchaseOrder.vendor_name`, `gst_number`, `vendor_address`, `vendor_city`, `vendor_state`, `vendor_pincode`.
- `PurchaseOrder.total_amount`: sum of item totals.
- `PurchaseOrderItem.article_id`, `article_name`, `supplier_article_name`, `quantity`, `unit_price`, `total_value`.

## Data flow

- User creates PO and selects vendor/item details.
- Item totals are recomputed from quantity and unit price.
- Submitted PO becomes a finalized document.
- PDF output should reflect submitted PO data.

## Debug checklist

- Total wrong: inspect `PurchaseOrderItem.recompute_totals()`.
- Vendor data missing: check `vendors` record and form binding.
- PDF mismatch: compare template context with saved `purchase_order_items`.

## Form fields

- Purchase order number: generated or entered PO identifier.
- Vendor name, GST number, address, city, state, pincode: vendor details copied into the PO.
- Comments: default delivery/payment/transport terms.
- Article: selected master article.
- Supplier article name: vendor-side item name.
- Description: extra line detail.
- Quantity, unit price, total value: item financial fields.

## Buttons and actions

- Create opens a draft PO.
- Save as Draft stores incomplete PO.
- Submit finalizes PO.
- Reopen moves submitted PO back to editable state where allowed.
- Delete removes draft or allowed PO.
- Download PDF generates the printable PO.

## Common errors and fixes

- Submit allowed with empty item: validate item formset before saving.
- PO number duplicated: inspect numbering generator and unique constraint.
- PDF old after edit: confirm saved data is used, not stale context.
