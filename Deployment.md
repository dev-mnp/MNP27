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

Google Drive Integration via Cloud Run Service Account


1. Identify the Cloud Run Service Account

1. Open Google Cloud Console.
2. Navigate to Cloud Run.
3. Select the service (e.g., mnp27).
4. Open the Revisions tab.
5. Click the latest revision (serving traffic).
6. Open the Security tab for that revision.
7. Copy the Service Account email.

Example:

690028296899-compute@developer.gserviceaccount.com

This is the identity Cloud Run uses to access Google APIs.

⸻

2. Enable Google Drive API

1. Go to APIs & Services → Library.
2. Search for Google Drive API.
3. Click Enable.

Ensure the API is enabled in the same Google Cloud project where Cloud Run is deployed.

⸻

3. Share Drive Folder with the Service Account

1. Open Google Drive.
2. Locate the root folder used by the application (e.g., /MNP/).
3. Right-click the folder and select Share.
4. Add the Cloud Run service account email.
5. Set permission to Editor.
6. Click Done.

The service account will now have access only to the shared folder and its contents.

⸻

4. Recommended Drive Folder Structure

The Drive structure should follow this format:

/MNP/
    /District/
    /Public/
    /Institution/
    /Others/

If subfolders do not exist, the application may create them automatically when uploading files.

⸻

5. Backend Configuration

Use the following implementation:

from googleapiclient.discovery import build
from google.auth import default
def get_drive_service():
    credentials, _ = default(
        scopes=["https://www.googleapis.com/auth/drive"]
    )
    return build("drive", "v3", credentials=credentials)

This uses Application Default Credentials provided automatically by Cloud Run.

No JSON credential file is required.

⸻

6. Environment Variables in Cloud Run

Only folder IDs are required as environment variables.

Example:

GOOGLE_DRIVE_DISTRICT_FOLDER_ID=xxxxxxxx


⸻

7. Redeployment Steps

After updating the backend:

1. Build a new container image.
2. Deploy the new revision to Cloud Run.
3. Verify the revision is active.
4. Test file upload functionality.

⸻

8. Authentication Model

Cloud Run uses Application Default Credentials (ADC).

Internally:

* Google automatically injects access tokens into the runtime.
* Tokens are rotated automatically.
* No manual refresh mechanism is required.
* No credential expiration handling is needed in application code.

⸻

9. Common Issues

403 Insufficient Permissions

The Drive folder has not been shared correctly with the service account.

404 Folder Not Found

Incorrect folder ID configured in environment variables.

Drive API Not Enabled

Ensure Google Drive API is enabled in the correct project.

⸻

10. Security Considerations

* The service account only has access to folders explicitly shared with it.
* It does not gain access to the entire Drive account.
* No secrets are stored in the repository.
* No OAuth verification is required.


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

