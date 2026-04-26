# Reports

## What this module is

Reports produces operational PDFs and Excel files from final staged data. Segregation and Stage Distribution are the major report groups.

## Main code files

- View: `core/reports/views.py`
- Services: `core/reports/services.py`
- URLs: `core/reports/urls.py`
- Template: `core/templates/reports/reports.html`
- Models used: `TokenGenerationRow`, `LabelGenerationRow`, `EventSession`

## Main source tables

- `token_generation_rows`: primary source for Segregation and Stage Distribution.
- `event_sessions`: active event and source metadata.
- `label_generation_rows`: label-stage source where label reports need it.

## Important token row fields

- `row_data`: the full exported token row. Most report columns are read from here.
- `headers`: source column order.
- `beneficiary_type`: District, Public, Institutions, Others.
- `sequence_no`: item sequence number.
- `start_token_no` and `end_token_no`: token range.
- `requested_item`: article or aid name.

## Segregation reports

- File 1: Beneficiary-wise Article List using Waiting Hall quantity.
- File 2: Article-wise Beneficiaries.
- File 3: distribution/stage movement style report.
- Filters should apply consistently to preview, PDF download, and Excel download.

## Stage Distribution reports

- File 1: Beneficiary List with optional sequence range.
- Files 2 to 4: District/Public/Institution-wise article lists.
- File 5: Article-wise beneficiaries.
- File 6: Article list.
- Premise filter decides whether totals use Waiting Hall quantity, Token quantity, or both.

## Debug checklist

- Preview total differs from download: compare filter parameters passed to both endpoints.
- File 1 sequence range ignored: check only File 1 preview/download uses sequence range.
- Waiting Hall report shows token numbers: ensure token columns are blank when premise is Waiting Hall only.
- Report includes excluded row: sync reports after Token Generation optional exclusion.
- Grand total mismatch: inspect quantity column selected from `row_data`.

## Report filters and fields

- Beneficiary type: District, Public, Institutions, Others, or All.
- Item type: Article, Aid, Project, or All.
- Premise: Waiting Hall quantity, MASM Hall/Token quantity, or All.
- Sequence From and Sequence To: only for Stage Distribution File 1.
- Rows and Grand Total: calculated summary for the selected report card.

## Buttons and actions

- Sync Data copies latest Token Generation rows into report-stage context.
- Upload replaces report-stage input from CSV or Excel.
- Apply or Filter Rows applies selected filters.
- Reset clears filters.
- Preview opens PDF preview.
- Download PDF downloads the selected report.
- Download Excel exports workbook output where available.

## Common errors and fixes

- All cards expand after filter: preserve open panel state in query parameters.
- Collapsed section still shows counts: hide header meta when collapsed if requested by UI.
- File title wrong: inspect dynamic title builder for beneficiary and premise filters.
- File 2 to 5 token columns look separate: check table column widths and border drawing.
- Excel and PDF totals differ: use the same row builder for both.
