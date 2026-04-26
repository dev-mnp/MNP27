# Deployment

## Purpose

Deployment explains how the app is hosted and what external services must be ready before the app can run safely.

## Main parts

- Supabase stores the PostgreSQL database.
- Google Cloud Run hosts the Django application.
- Google service accounts and OAuth support Google Drive attachment upload.
- Custom domain and Cloudflare route users to the live app.

## What users should know

- Deployment changes should be done by an admin or developer.
- Never share production passwords, service account keys, OAuth secrets, or database URLs.
- After deployment, test login, dashboard, application entry, attachments, exports, reports, and labels.
