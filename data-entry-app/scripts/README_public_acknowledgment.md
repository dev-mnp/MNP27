# Public Acknowledgment PDF Generator

This script implements the notebook flow for public acknowledgment autofill and PDF merge.

Script:
- `data-entry-app/scripts/generate_public_acknowledgment.py`

## Prerequisites

```bash
python3 -m pip install pypdf pandas openpyxl
```

## Important

- The template **must** be a fillable PDF (AcroForm), e.g. your editable `acknowledgment stage_2.pdf`.
- Non-fillable/image PDFs cannot be autofilled.

## Run

```bash
python3 data-entry-app/scripts/generate_public_acknowledgment.py \
  --generated "/path/to/Generated_token_V4.xlsx" \
  --public-data "/path/to/Public Data.xlsx" \
  --template "/path/to/acknowledgment stage_2.pdf" \
  --output-dir "/path/to/output" \
  --field-map-json "data-entry-app/scripts/public_ack_field_map.sample.json"
```

## Output

- `all_acknowledgment.pdf` (merged final file)
- `Beneficiary_list.csv` (merged source table for debugging/verification)

