# Nightly Export Automation (GitHub Actions)

This project now includes a scheduled workflow that runs daily at **12:00 AM IST** and exports:
- Master Entry
- Fund Request
- Order Management
- Article Management

Files are generated as timestamped CSVs and uploaded to Google Drive.

## Workflow
- File: `.github/workflows/nightly-exports.yml`
- Schedule: `30 18 * * *` (UTC) = `00:00 IST`
- Cutoff date (inclusive): `2026-03-02` via `EXPORT_CUTOFF_DATE`

After the cutoff date, the job exits without generating files.

## Required GitHub Secrets
Configure these in your GitHub repository settings:

1. `SUPABASE_URL`
2. `SUPABASE_SERVICE_ROLE_KEY`
3. `GOOGLE_OAUTH_CLIENT_ID`
4. `GOOGLE_OAUTH_CLIENT_SECRET`
5. `GOOGLE_OAUTH_REFRESH_TOKEN`

`GOOGLE_SERVICE_ACCOUNT_JSON` is optional fallback for service account mode.

## Google Drive Access Setup
For personal `My Drive`, use OAuth user credentials:

1. In Google Cloud, enable **Google Drive API**.
2. Create OAuth client credentials (Desktop/Web).
3. Generate a refresh token for that client with Drive scope.
4. Add `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`, and `GOOGLE_OAUTH_REFRESH_TOKEN` as GitHub secrets.

## Destination Folder
Configured in workflow env:

`GOOGLE_DRIVE_TARGET_PATH=/Users/aswathshakthi/Library/CloudStorage/GoogleDrive-maruvoorhelp@gmail.com/My Drive/Makkal Nala Pani 2026/Database_Code_Aswath`

The script resolves this to Drive path under `My Drive` and creates missing folders if needed.

## Manual Run
You can trigger it from GitHub Actions using **Run workflow** on `Nightly Exports`.

## Local Demo Without Drive Upload
To generate CSVs locally only:

`SKIP_DRIVE_UPLOAD=true node scripts/nightly-exports.mjs`
