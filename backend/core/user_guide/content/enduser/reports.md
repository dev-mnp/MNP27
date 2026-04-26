# Reports

## Purpose

Reports generate operational PDFs and Excel files from the final staged data.

## Segregation

- Use Segregation reports for waiting hall and distribution preparation.
- Filters include beneficiary type and item type.
- Apply filters only after selection is complete.
- Preview before downloading.

## Stage Distribution

- Stage Distribution uses token-generated data.
- Filters include beneficiary type, item type, and premise.
- Premise can show Waiting Hall quantity, MASM Hall or Token quantity, or All.
- File 1 is Beneficiary List with optional sequence range.
- Files 2 to 5 show beneficiary-wise and article-wise structured lists.
- File 6 shows article list totals.

## System behavior

- Reports should not modify source data.
- Sync Data refreshes report-stage data from Token Generation.
- Preview and downloaded PDFs should use the same filtered data.
