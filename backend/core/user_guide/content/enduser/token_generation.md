# Token Generation

## Purpose

Token Generation creates the final token-stage working data used by labels, reports, and distribution.

## How to use

- Sync Data from Sequence List.
- Review optional transformations.
- Exclude rows only when they should not proceed to token-stage output.
- Adjust long names and token names if they will not fit labels.
- Generate token numbers.
- Export the final token file.

## System behavior

- Rows excluded in optional transformation are not part of the final token-stage output.
- Reports and labels should use the final token-generated data.
- Token numbers are created from Token quantity, not Waiting Hall quantity.
