MNP27 – Deployment Guide (Minimal – Production Setup)

⸻

🏗 Final Architecture

User
 ↓
Cloudflare DNS
 ↓
Cloudflare Worker (Reverse Proxy)
 ↓
Cloud Run (asia-south1)
 ↓
Supabase (Mumbai)
 ↓
Google Drive (Attachments)

⸻

1️⃣ Supabase (Database)

1. Create project at:
    https://supabase.com
2. Choose region near users
    Example: Mumbai (ap-south-1)
3. Go to:
    Settings → Database → Connection string
4. Copy Transaction Pooler URL

Add to:

backend/.env

DATABASE_URL=postgresql://user:password@host:6543/postgres
DJANGO_SECRET_KEY=your_secret_key
DJANGO_DEBUG=False

⸻

2️⃣ Google Drive Setup (Attachments)

Google Drive OAuth Setup (Personal Gmail / My Drive)

1. Enable Google Drive API

1. Go to Google Cloud Console.
2. Select the correct project.
3. Navigate to: APIs & Services → Library.
4. Search for “Google Drive API”.
5. Click Enable.

⸻

2. Configure OAuth Consent Screen

1. Go to: APIs & Services → OAuth consent screen.
2. Select User Type: External.
3. Complete required fields:
    * App name
    * Support email
4. Add scope:
    * https://www.googleapis.com/auth/drive
5. Save and Continue.
6. Click Publish App.
7. Confirm status shows: In production.

Important:
If left in Testing mode, refresh tokens expire after 7 days.

⸻

3. Create OAuth 2.0 Client ID

1. Go to: APIs & Services → Credentials.
2. Click Create Credentials → OAuth client ID.
3. Select Application Type: Web application.
4. Add Authorized Redirect URI:
    https://developers.google.com/oauthplayground
5. Click Create.
6. Copy:
    * Client ID
    * Client Secret

Store them securely.

⸻

4. Generate Refresh Token (Permanent)

1. Open:
    https://developers.google.com/oauthplayground
2. Click the gear icon (top right).
3. Enable: Use your own OAuth credentials.
4. Enter:
    * Client ID
    * Client Secret
5. Close settings.
6. In Step 1 panel:
    * Select Drive API v3
    * Select scope:
        https://www.googleapis.com/auth/drive
7. Click Authorize APIs.
8. Login with your Gmail.
9. Click Allow.
10. Click Exchange authorization code for tokens.

Copy the refresh_token value.

This refresh token will remain valid unless:

* You revoke app access
* You regenerate too many tokens
* You delete the OAuth client

⸻

5. Set Environment Variables

Local Development (.env)

GOOGLE_CLIENT_ID=your_client_id
GOOGLE_CLIENT_SECRET=your_client_secret
GOOGLE_REFRESH_TOKEN=your_refresh_token

Cloud Run

Go to:
Cloud Run → Service → Edit & Deploy New Revision → Variables & Secrets

Add the same three variables.

Do not include quotes.
Do not add extra spaces.

Deploy a new revision.

⸻

6. Backend Implementation

Use the following logic to create Drive credentials:

`import os
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
def get_drive_service():
    credentials = Credentials(
        None,
        refresh_token=os.getenv("GOOGLE_REFRESH_TOKEN"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.getenv("GOOGLE_CLIENT_ID"),
        client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
        scopes=["https://www.googleapis.com/auth/drive"],
    )
    return build("drive", "v3", credentials=credentials)`

This allows Google to:

* Automatically generate access tokens
* Refresh tokens when expired

No manual refresh logic is required.

⸻

7. Folder Configuration

Files will be uploaded to folders inside your personal My Drive.

Ensure:

* Folder IDs are correct
* Environment variables contain valid folder IDs
* Drive API is enabled

Example folder ID:

From:
https://drive.google.com/drive/folders/1AbCdEfGhIjKlMnOp

Folder ID:
1AbCdEfGhIjKlMnOp

⸻

8. Common Errors

403 storageQuotaExceeded

Occurs if using Service Account with My Drive.
Use OAuth instead.

DefaultCredentialsError

Occurs when using Application Default Credentials outside GCP.
OAuth method does not require ADC.

invalid_grant

Refresh token revoked or expired.
Regenerate using OAuth Playground.

⸻

9. Security Notes

* Never commit client secret to repository.
* Store credentials in environment variables.
* Do not regenerate refresh tokens repeatedly.
* Keep OAuth app in Production mode.

⸻

10. Maintenance Guidelines

Refresh token remains valid unless:

* User revokes app access from Google Account security
* OAuth client is deleted
* More than 50 tokens are generated for same user/client

If refresh token becomes invalid:
Repeat Step 4 to generate a new one.

⸻


3️⃣ Docker

Build

docker build -t mnp27 .

Run locally

docker run -p 8080:8080 --env-file backend/.env mnp27

Visit:

http://localhost:8080

If working → proceed.

⸻

4️⃣ Cloud Run Deployment

Deploy Container

Region:

asia-south1

Allow:

Unauthenticated access

⸻

Set Environment Variables in Cloud Run

Add:

DATABASE_URL=...
DJANGO_SECRET_KEY=...
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
GOOGLE_REFRESH_TOKEN=...
DJANGO_ALLOWED_HOSTS=mnp.omsakthi.co.in,mnp27-xxxxx.run.app
CSRF_TRUSTED_ORIGINS=https://mnp.omsakthi.co.in
DJANGO_DEBUG=False

⸻

Production Server

Must use:

gunicorn mnp_backend.wsgi:application --bind 0.0.0.0:$PORT

❌ Do NOT use runserver in production.

⸻

5️⃣ Cloudflare Worker (Custom Domain – Reverse Proxy)

Since Cloud Run region does not support direct custom domain mapping without Load Balancer, use Cloudflare Worker.

⸻

A. Create Worker

Cloudflare → Workers & Pages → Create Worker

Replace code with:

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const originUrl = "https://mnp27-xxxxx-asia-south1.run.app";
    const target = originUrl + url.pathname + url.search;
    const newRequest = new Request(target, request);
    return fetch(newRequest, {
      redirect: "follow"
    });
  }
}

Replace originUrl with your Cloud Run URL.

Deploy Worker.

⸻

B. Attach Worker to Domain

Cloudflare → Workers → Settings → Domains & Routes

Add route:

mnp.omsakthi.co.in/*

Failure mode:

Fail open (proceed)

⸻

C. Configure DNS

Cloudflare → DNS → Records

Delete any existing mnp record.

Add:

Type	Name	IPv4	Proxy
A	mnp	192.0.2.1	🟠 ON

Important:
Proxy must be ON (orange cloud).

⸻

D. SSL Setting

Cloudflare → SSL/TLS → Overview

Set:

Full

Do NOT use Flexible.

⸻

6️⃣ Test

Open:

https://mnp.omsakthi.co.in/ui/login/

If working:

* No Google 404
* No DisallowedHost
* Worker forwarding correctly

⸻

✅ Production Checklist

* Supabase region near users
* Cloud Run region matches Supabase
* Gunicorn used (not runserver)
* All domains added to DJANGO_ALLOWED_HOSTS
* CSRF trusted origins configured
* Drive API refresh token valid
* Worker route configured
* Cloudflare DNS proxy ON
* SSL mode = Full

⸻

🔁 Redeploy Flow

When updating app:

1. Update code
2. Rebuild Docker
3. Deploy new revision to Cloud Run
4. Done (Worker auto-forwards)

No Firebase redeploy needed.
No DNS change needed.

⸻

💰 Cost Model

* Supabase: DB usage
* Cloud Run: container usage
* Cloudflare: Free plan
* No Google Load Balancer
* No Firebase Hosting required

