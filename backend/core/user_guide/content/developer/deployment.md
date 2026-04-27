# Deployment

## What this section is

Deployment explains how this Django application is moved from a developer machine to a live production URL.

The production setup uses:

- GitHub repository: `https://github.com/dev-mnp/MNP27`
- Supabase PostgreSQL for the database
- Google Cloud Run for hosting the Django container
- Google Drive OAuth for application attachments
- Cloudflare Worker reverse proxy for `mnp.omsakthi.co.in`

## Main production flow

1. Code is committed and pushed to GitHub.
2. Docker builds a container image from the repository.
3. Cloud Run runs that container.
4. Supabase stores the production database.
5. Google Drive stores uploaded attachments.
6. Cloudflare routes `mnp.omsakthi.co.in` to the Cloud Run URL through a Worker.

## MNP27 minimal production setup

This is the shortest production path for MNP27.

Final architecture:

- User opens `https://mnp.omsakthi.co.in`.
- Cloudflare DNS receives the request.
- Cloudflare Worker reverse proxies the request.
- Google Cloud Run runs the Django container in `asia-south1`.
- Supabase stores PostgreSQL data in the Mumbai region.
- Google Drive stores application attachments.

Flow:

- User
- Cloudflare DNS
- Cloudflare Worker reverse proxy
- Cloud Run `asia-south1`
- Supabase Mumbai
- Google Drive attachments

### Step 1: Supabase database

1. Create a Supabase project at `https://supabase.com`.
2. Choose a region near users. For this app, use Mumbai if available.
3. Go to Settings, then Database, then Connection string.
4. Copy the Transaction Pooler URL.
5. Add it to `backend/.env` locally.
6. Add the same value to Cloud Run environment variables for production.

Example local `.env` values:

- `DATABASE_URL=postgresql://user:password@host:6543/postgres`
- `DJANGO_SECRET_KEY=your_secret_key`
- `DJANGO_DEBUG=False`

Use the transaction pooler URL when deploying to Cloud Run because Cloud Run can create short-lived database connections.

### Step 2: Google Drive setup for attachments

This app uses Google Drive OAuth for uploading attachments to a personal Gmail or My Drive folder.

Enable Google Drive API:

1. Open Google Cloud Console.
2. Select the correct Google Cloud project.
3. Go to APIs and Services, then Library.
4. Search for Google Drive API.
5. Click Enable.

Configure OAuth consent screen:

1. Go to APIs and Services, then OAuth consent screen.
2. Select External.
3. Fill required fields such as app name and support email.
4. Add this scope: `https://www.googleapis.com/auth/drive`.
5. Save and continue.
6. Publish the app.
7. Confirm the app status is In production.

Important:

- If the OAuth app stays in Testing mode, refresh tokens can expire after 7 days.
- Keep it in Production mode for a long-running deployment.

Create OAuth 2.0 Client ID:

1. Go to APIs and Services, then Credentials.
2. Click Create Credentials.
3. Select OAuth client ID.
4. Select Web application.
5. Add this Authorized Redirect URI: `https://developers.google.com/oauthplayground`.
6. Click Create.
7. Copy the Client ID and Client Secret.

Generate refresh token:

1. Open `https://developers.google.com/oauthplayground`.
2. Click the gear icon.
3. Enable Use your own OAuth credentials.
4. Enter the Client ID and Client Secret.
5. Close settings.
6. In Step 1, select Drive API v3.
7. Select the scope `https://www.googleapis.com/auth/drive`.
8. Click Authorize APIs.
9. Login with the Gmail account used for Drive attachments.
10. Click Allow.
11. Click Exchange authorization code for tokens.
12. Copy the `refresh_token`.

The refresh token remains valid unless:

- The user revokes app access.
- The OAuth client is deleted.
- Too many refresh tokens are generated for the same user and client.

Use these actual app environment variable names:

- `GOOGLE_DRIVE_CLIENT_ID=your_client_id`
- `GOOGLE_DRIVE_CLIENT_SECRET=your_client_secret`
- `GOOGLE_DRIVE_REFRESH_TOKEN=your_refresh_token`
- `GOOGLE_DRIVE_APPLICATIONS_FOLDER_ID=your_drive_folder_id`

Do not use the shorter names `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, or `GOOGLE_REFRESH_TOKEN` unless the code is changed to read them. This app currently reads the `GOOGLE_DRIVE_...` names.

Cloud Run location:

1. Open Cloud Run.
2. Open the service.
3. Click Edit and deploy new revision.
4. Open Variables and Secrets.
5. Add the same Google Drive variables.
6. Do not include quotes.
7. Do not add extra spaces.
8. Deploy a new revision.

Backend Drive credential logic:

- The app builds Google Drive credentials from the refresh token, token URI, client id, client secret, and Drive scope.
- Google automatically generates short-lived access tokens.
- Google refreshes access tokens when needed.
- No manual refresh job is required.

Folder configuration:

- Files upload inside the configured Google Drive folder.
- Make sure `GOOGLE_DRIVE_APPLICATIONS_FOLDER_ID` is correct.
- Make sure the Google account used by OAuth has access to that folder.

Folder id example:

- Folder URL: `https://drive.google.com/drive/folders/1AbCdEfGhIjKlMnOp`
- Folder id: `1AbCdEfGhIjKlMnOp`

Common Drive errors:

- `403 storageQuotaExceeded`: often happens when using a service account with My Drive. Use OAuth for personal Drive.
- `DefaultCredentialsError`: happens when code expects Application Default Credentials. OAuth refresh-token flow does not need ADC.
- `invalid_grant`: refresh token is revoked, expired, or invalid. Regenerate it using OAuth Playground.

Security notes:

- Never commit the client secret.
- Store credentials in environment variables or Secret Manager.
- Do not regenerate refresh tokens repeatedly.
- Keep the OAuth app in Production mode.

### Step 3: Docker

Build from the repository root:

`docker build -t mnp27 .`

Run locally:

`docker run -p 8080:8080 --env-file backend/.env mnp27`

Visit:

`http://localhost:8080`

If this works locally, proceed to Cloud Run.

### Step 4: Cloud Run deployment

Deploy to:

- Region: `asia-south1`
- Access: allow unauthenticated access if Cloudflare Worker is the public entry point
- Runtime server: Gunicorn

Production must use:

`gunicorn mnp_backend.wsgi:application --bind 0.0.0.0:$PORT`

Do not use:

`python manage.py runserver`

Required Cloud Run environment variables:

- `DATABASE_URL=...`
- `DJANGO_SECRET_KEY=...`
- `DJANGO_DEBUG=False`
- `DJANGO_ALLOWED_HOSTS=mnp.omsakthi.co.in,<cloud-run-host>`
- `CSRF_TRUSTED_ORIGINS=https://mnp.omsakthi.co.in`
- `DJANGO_USE_X_FORWARDED_HOST=True`
- `GOOGLE_DRIVE_CLIENT_ID=...`
- `GOOGLE_DRIVE_CLIENT_SECRET=...`
- `GOOGLE_DRIVE_REFRESH_TOKEN=...`
- `GOOGLE_DRIVE_APPLICATIONS_FOLDER_ID=...`

Replace `<cloud-run-host>` with the Cloud Run host only, without `https://`.

### Step 5: Cloudflare Worker custom domain reverse proxy

Use Cloudflare Worker because this setup avoids Google Load Balancer and keeps custom domain routing simple.

Create Worker:

1. Open Cloudflare.
2. Go to Workers and Pages.
3. Create Worker.
4. Replace the code with the reverse proxy code.
5. Replace the origin URL with your Cloud Run URL.
6. Deploy Worker.

Worker code:

```js
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
```

Attach Worker to domain:

1. Go to Cloudflare Workers.
2. Open Settings.
3. Open Domains and Routes.
4. Add route: `mnp.omsakthi.co.in/*`.
5. Use fail open only if you intentionally want traffic to proceed when the Worker fails.

Configure DNS:

1. Go to Cloudflare DNS.
2. Delete any existing `mnp` record that conflicts.
3. Add an A record.
4. Name: `mnp`.
5. IPv4 address: `192.0.2.1`.
6. Proxy status: ON, orange cloud.

The IP `192.0.2.1` is only a placeholder target so Cloudflare can attach the Worker route. Traffic is handled by the Worker because proxy is ON.

SSL:

1. Go to Cloudflare SSL/TLS.
2. Set mode to Full.
3. Do not use Flexible.

### Step 6: Test production

Open:

`https://mnp.omsakthi.co.in/ui/login/`

Successful signs:

- Page loads through custom domain.
- No Google 404.
- No `DisallowedHost`.
- No CSRF error on login.
- Attachments upload to Drive.
- Reports and labels download correctly.

### Minimal production checklist

- Supabase region is near users.
- Cloud Run region is `asia-south1`.
- Gunicorn is used.
- `runserver` is not used.
- All domains are in `DJANGO_ALLOWED_HOSTS`.
- CSRF trusted origins are configured.
- Drive API refresh token is valid.
- Worker route is configured.
- Cloudflare DNS proxy is ON.
- Cloudflare SSL mode is Full.

### Redeploy flow

When updating the app:

1. Update code.
2. Commit and push to GitHub.
3. Rebuild Docker image or deploy source to Cloud Run.
4. Deploy new Cloud Run revision.
5. No Cloudflare Worker redeploy is needed unless the Cloud Run URL changes.
6. No DNS change is needed.

### Cost model

- Supabase charges for database usage.
- Cloud Run charges for container usage.
- Cloudflare Worker can run on the free plan depending on usage.
- No Google Load Balancer is required in this setup.
- No Firebase Hosting is required.

## Environment file

The local environment file is:

`backend/.env`

This file stores secrets and environment-specific settings. It must never be committed to GitHub.

The project protects it in `.dockerignore` using:

`**/.env`

That means the local `.env` file is not copied into the Docker image. In Cloud Run, the same values must be added through Cloud Run environment variables or Secret Manager.

## Environment variables

### Django core

- `DJANGO_SECRET_KEY`: Secret key used by Django for signing sessions and security tokens. Generate a strong random value and keep it private.
- `DJANGO_DEBUG`: Use `False` in production. Use `True` only for local development.
- `DJANGO_ALLOWED_HOSTS`: Comma-separated list of allowed hostnames. Production should include `mnp.omsakthi.co.in` and the Cloud Run host.
- `CSRF_TRUSTED_ORIGINS`: Comma-separated HTTPS origins allowed for forms. Add `https://mnp.omsakthi.co.in` and the Cloud Run URL.
- `DJANGO_TIME_ZONE`: App timezone. For this project use `Asia/Kolkata`.
- `DJANGO_USE_X_FORWARDED_HOST`: Use `True` when the app is behind Cloudflare or another proxy.

How to get them:

- `DJANGO_SECRET_KEY`: generate locally with Django or any secure password generator.
- `DJANGO_ALLOWED_HOSTS`: use the final domain and Cloud Run hostname.
- `CSRF_TRUSTED_ORIGINS`: use the same public HTTPS URLs that users open in the browser.

### Database and Supabase

- `DATABASE_URL`: PostgreSQL connection URL for Supabase.
- `DJANGO_DB_HOSTADDR`: Optional direct IP address for the database host.
- `DJANGO_DB_CONNECT_TIMEOUT`: Optional database connection timeout.
- `DJANGO_DB_CONN_MAX_AGE`: Keeps database connections open for reuse.
- `DJANGO_DB_CONN_HEALTH_CHECKS`: Enables connection health checks.

How to get them:

1. Open Supabase.
2. Open the project.
3. Go to Project Settings.
4. Open Database.
5. Copy the PostgreSQL connection string.
6. Replace the password placeholder with the real database password.
7. Use the pooled connection string if Cloud Run may open many short-lived connections.

Important production note:

Cloud Run can create many container instances. Supabase has connection limits. Use pooling and keep `GUNICORN_WORKERS` low unless the database plan supports more connections.

### Google Drive attachments

- `GOOGLE_DRIVE_CLIENT_ID`: OAuth client id from Google Cloud.
- `GOOGLE_DRIVE_CLIENT_SECRET`: OAuth client secret from Google Cloud.
- `GOOGLE_DRIVE_REFRESH_TOKEN`: Refresh token used by the app to access Drive.
- `GOOGLE_DRIVE_APPLICATIONS_FOLDER_ID`: Google Drive folder id where attachments are stored.

How to get them:

1. Open Google Cloud Console.
2. Select the project used for this app.
3. Enable Google Drive API.
4. Configure OAuth consent screen.
5. Create an OAuth Client ID.
6. Generate a refresh token for the Google account that owns or can access the Drive folder.
7. Open the target Drive folder in the browser.
8. Copy the folder id from the URL.

Drive folder id example:

If the folder URL is `https://drive.google.com/drive/folders/abc123XYZ`, then the folder id is `abc123XYZ`.

Common Drive errors:

- Upload returns 401: refresh token or OAuth credentials are wrong.
- Upload returns 403: Drive API is disabled or the account does not have folder access.
- File uploads to wrong folder: check `GOOGLE_DRIVE_APPLICATIONS_FOLDER_ID`.
- File saves in Drive but not in UI: check the application attachment save logic and database row after draft submit.

### Admin bootstrap

- `DJANGO_SUPERUSER_EMAIL`: Initial admin email.
- `DJANGO_SUPERUSER_PASSWORD`: Initial admin password.
- `DJANGO_SUPERUSER_NAME`: Initial admin display name.

These create or update the guaranteed superuser during migration/startup.

### Regular user bootstrap

- `DJANGO_BOOTSTRAP_USERS`: JSON array used to create or update non-superuser accounts during migration/startup.

Use this when you want Cloud Run app creation to create normal users along with the superuser.

Example:

```json
[
  {
    "email": "editor@example.com",
    "password": "change-this-password",
    "name": "Editor User",
    "role": "editor",
    "status": "active",
    "permissions": {
      "dashboard": ["view", "view_page_2"],
      "application_entry": ["view", "create_edit", "submit", "reopen"],
      "article_management": ["view", "create_edit"],
      "user_guide": ["view"]
    }
  },
  {
    "email": "viewer@example.com",
    "password": "change-this-password",
    "name": "Viewer User",
    "role": "viewer",
    "status": "active",
    "permissions": {
      "dashboard": ["view"],
      "user_guide": ["view"]
    }
  }
]
```

Cloud Run environment variables are single-line values, so paste the JSON as one line:

```env
DJANGO_BOOTSTRAP_USERS=[{"email":"editor@example.com","password":"change-this-password","name":"Editor User","role":"editor","status":"active","permissions":{"dashboard":["view","view_page_2"],"application_entry":["view","create_edit","submit","reopen"],"user_guide":["view"]}}]
```

Permission rules:

- `permissions` controls exactly what the user can see and do.
- If a module is not listed, that module is disabled for the user.
- `role` is kept for display/filtering, but module access comes from permissions.
- Use `"*": true` inside `permissions` only if you intentionally want every supported action for every module.

After production setup, you can still manage users from User Management.

### Runtime controls

- `PORT`: Cloud Run injects this automatically. The Docker image defaults to `8080`.
- `RUN_MIGRATIONS`: Use `1` to run migrations at container start. Use `0` if migrations are handled separately.
- `RUN_COLLECTSTATIC`: Use `0` in production because static files are collected during Docker build.
- `GUNICORN_WORKERS`: Number of Gunicorn worker processes.
- `WEB_CONCURRENCY`: Alternative worker count used if `GUNICORN_WORKERS` is not set.
- `GUNICORN_TIMEOUT`: Request timeout in seconds. Keep this high enough for PDF and Excel generation.

Recommended Cloud Run values:

- `RUN_MIGRATIONS=1` for simple deployments.
- `RUN_COLLECTSTATIC=0`.
- `GUNICORN_WORKERS=1` or `2`.
- `GUNICORN_TIMEOUT=180`.

## Dockerfile explanation

The Dockerfile is at:

`Dockerfile`

Line-by-line purpose:

- `FROM python:3.11-slim`: starts from a small official Python image.
- `ENV PYTHONDONTWRITEBYTECODE=1`: prevents Python from writing `.pyc` files.
- `ENV PYTHONUNBUFFERED=1`: sends logs immediately to Cloud Run.
- `ENV PORT=8080`: default port used by the container.
- `WORKDIR /app/backend`: sets the working folder inside the container.
- `apt-get update`: refreshes package metadata.
- `apt-get install libpq5`: installs PostgreSQL client runtime library.
- `apt-get install libjpeg62-turbo libfreetype6 zlib1g`: installs image/font libraries needed by PDF and image tooling.
- `rm -rf /var/lib/apt/lists/*`: removes package cache to keep the image smaller.
- `COPY backend/requirements.txt`: copies Python requirements first so Docker can cache dependency installs.
- `pip install --upgrade pip`: updates pip.
- `pip install -r requirements.txt`: installs Django and app dependencies.
- `COPY backend/ /app/backend/`: copies the application code.
- `RUN chmod +x entrypoint.sh`: makes the startup script executable.
- `RUN ... collectstatic`: collects static files during image build.
- `EXPOSE 8080`: documents that the container listens on port 8080.
- `CMD ["/app/backend/entrypoint.sh"]`: starts the app using the entrypoint script.

## .dockerignore explanation

The `.dockerignore` file prevents unnecessary or sensitive files from entering the Docker build.

Important entries:

- `.git`: Git history is not needed inside the image.
- `.github`: CI files are not needed at runtime.
- `.idea`: local PyCharm files are not needed.
- `**/.env`: secrets must not be copied into the image.
- `**/.venv`: local virtual environments should not be copied.
- `backend/db.sqlite3`: local SQLite database must not go to production.
- `backend/media/`: local uploaded media should not go into the container.
- `backend/staticfiles/`: static files are regenerated during build.
- `backend/core/tests/`: tests are not needed in the production container.

## entrypoint.sh explanation

The startup script is:

`backend/entrypoint.sh`

What it does:

- `set -eu`: stops the container if a command fails or a required variable is missing.
- `: "${PORT:=8080}"`: uses port 8080 if Cloud Run does not provide one.
- `RUN_COLLECTSTATIC`: optionally collects static files at startup.
- `RUN_MIGRATIONS`: optionally runs Django migrations at startup.
- `workers="${GUNICORN_WORKERS:-${WEB_CONCURRENCY:-1}}"`: decides how many Gunicorn workers to start.
- `timeout="${GUNICORN_TIMEOUT:-180}"`: sets request timeout.
- `gunicorn mnp_backend.wsgi:application`: starts the Django app.
- `--bind 0.0.0.0:${PORT}`: listens on the Cloud Run port.
- `--access-logfile -` and `--error-logfile -`: sends logs to Cloud Run logging.
- `--worker-tmp-dir /tmp`: avoids temporary file issues in container environments.

## Running Docker locally

Run these commands from the repository root:

`/Users/aswathshakthi/PycharmProjects/MLMR/MNP27`

Build the image:

`docker build -t mnp27 .`

Run the image with local `.env`:

`docker run --env-file backend/.env -p 8080:8080 mnp27`

Open:

`http://127.0.0.1:8080`

Run without migrations:

`docker run --env-file backend/.env -e RUN_MIGRATIONS=0 -p 8080:8080 mnp27`

Use this only when the database is already migrated.

## GitHub workflow

Repository:

`https://github.com/dev-mnp/MNP27`

Normal developer flow:

1. Check changed files.
2. Run Django checks.
3. Commit the change.
4. Push to GitHub.
5. Deploy from the pushed code.

Commands:

`git status`

`git add <files>`

`git commit -m "Describe the deployment/documentation change"`

`git push origin <branch-name>`

Important safety rules:

- Never commit `backend/.env`.
- Never commit service account keys.
- Never commit database passwords.
- Never commit Google OAuth secrets.
- If a secret is accidentally committed, rotate it immediately.

## Supabase setup

Steps:

1. Create a Supabase project.
2. Save the database password securely.
3. Copy the PostgreSQL connection string.
4. Put the connection string in `DATABASE_URL`.
5. Use the pooled connection string if many Cloud Run instances may connect.
6. Run migrations.
7. Verify tables from the app.

Useful checks:

- Application Entry opens without database errors.
- Base files upload and read correctly.
- Token Generation sync works.
- Reports load without missing table or column errors.

Common Supabase errors:

- `relation does not exist`: migrations were not run.
- `password authentication failed`: database password is wrong.
- `too many connections`: use pooling, reduce workers, reduce Cloud Run max instances.
- `permission denied for schema public`: database user does not have enough privileges.

## Cloud Run deployment

Cloud Run can deploy from source or from a built container image.

Simple source deployment:

`gcloud run deploy mnp27 --source . --region asia-south1 --allow-unauthenticated`

Use the project root as the command folder:

`/Users/aswathshakthi/PycharmProjects/MLMR/MNP27`

Cloud Run settings:

- Service name: `mnp27`
- Region: choose a region close to users, for example `asia-south1`
- Container port: `8080`
- Memory: keep enough for PDF and Excel reports
- CPU: request-based CPU is usually enough
- Minimum instances: `0` to save cost
- Maximum instances: keep low at first to avoid unexpected cost
- Timeout: at least `180` seconds for large reports

## Adding environment variables in Cloud Run

In Google Cloud Console:

1. Open Cloud Run.
2. Open the `mnp27` service.
3. Click Edit and deploy new revision.
4. Open Variables and Secrets.
5. Add environment variables.
6. Add sensitive values from Secret Manager where possible.
7. Deploy the new revision.

Use Secret Manager for:

- `DATABASE_URL`
- `DJANGO_SECRET_KEY`
- `GOOGLE_DRIVE_CLIENT_SECRET`
- `GOOGLE_DRIVE_REFRESH_TOKEN`
- `DJANGO_SUPERUSER_PASSWORD`

Use normal environment variables for:

- `DJANGO_DEBUG=False`
- `DJANGO_TIME_ZONE=Asia/Kolkata`
- `RUN_MIGRATIONS=1`
- `RUN_COLLECTSTATIC=0`
- `GUNICORN_TIMEOUT=180`
- `DJANGO_ALLOWED_HOSTS`
- `CSRF_TRUSTED_ORIGINS`

## Protecting Cloud Run from bots and cost spikes

Use several layers together.

Cloud Run cost controls:

- Set minimum instances to `0`.
- Set maximum instances to a safe low number.
- Keep `GUNICORN_WORKERS` low.
- Set request timeout only as high as needed.
- Add Google Cloud billing budget alerts.

Application controls:

- Keep all important modules behind login.
- Use User Management permissions to hide sensitive modules.
- Do not expose admin-only URLs publicly without login.
- Keep `DJANGO_DEBUG=False`.

Cloudflare controls:

- Enable Bot Fight Mode or WAF rules if available.
- Add rate limiting for login and heavy report URLs.
- Block suspicious countries or IP ranges if needed.
- Cache only safe static assets, not authenticated pages.

Stronger protection option:

If the app should only be reached through Cloudflare, add a secret header in the Cloudflare Worker and verify that header in Django middleware. Do not rely on this until the middleware check exists in the codebase.

## Custom domain using Cloudflare Worker

Final domain:

`mnp.omsakthi.co.in`

The Cloud Run service gives a URL like:

`https://mnp27-xxxxxx.a.run.app`

We route the custom domain through Cloudflare Worker because this setup gives better proxy control and lets Cloudflare protect the app.

## Cloudflare DNS setup

In Cloudflare:

1. Open the `omsakthi.co.in` zone.
2. Add or confirm DNS for `mnp`.
3. Keep the record proxied through Cloudflare.
4. Create a Worker.
5. Add a Worker route for `mnp.omsakthi.co.in/*`.
6. The Worker forwards requests to the Cloud Run URL.

After this, update Cloud Run environment variables:

- `DJANGO_ALLOWED_HOSTS=mnp.omsakthi.co.in,<cloud-run-host>`
- `CSRF_TRUSTED_ORIGINS=https://mnp.omsakthi.co.in,https://<cloud-run-host>`
- `DJANGO_USE_X_FORWARDED_HOST=True`

Replace `<cloud-run-host>` with the host part of the Cloud Run URL, without `https://`.

## Cloudflare Worker example

Use this as the starting Worker code:

```js
export default {
  async fetch(request) {
    const targetHost = "<YOUR-CLOUD-RUN-URL.a.run.app>";

    const url = new URL(request.url);
    const targetUrl = `https://${targetHost}${url.pathname}${url.search}`;

    const newHeaders = new Headers(request.headers);
    newHeaders.set("Host", targetHost);

    const newRequest = new Request(targetUrl, {
      method: request.method,
      headers: newHeaders,
      body: request.body,
      redirect: "manual"
    });

    return fetch(newRequest);
  }
};
```

Replace:

`YOUR-CLOUD-RUN-URL.a.run.app`

with the real Cloud Run host.

## Cloudflare Worker safety notes

- Do not cache authenticated pages.
- Do not cache POST requests.
- Keep SSL/TLS mode as Full or Full Strict.
- If login redirects fail, check `CSRF_TRUSTED_ORIGINS`.
- If Django builds links with the Cloud Run URL instead of the custom domain, check `DJANGO_USE_X_FORWARDED_HOST=True`.
- If static files fail, confirm Cloud Run serves `/static/` through WhiteNoise.

## Deployment checklist

Before deployment:

- Run Django checks.
- Confirm `.env` is not staged in Git.
- Confirm Docker build succeeds.
- Confirm Supabase `DATABASE_URL` works.
- Confirm Drive OAuth values work.

After deployment:

- Open the Cloud Run URL.
- Open `https://mnp.omsakthi.co.in`.
- Test login.
- Test logout from the top-right user menu.
- Test Dashboard.
- Test Application Entry save, submit, archive, and attachments.
- Test Base Files upload.
- Test Seat Allocation sync.
- Test Sequence List save.
- Test Token Generation sync and export.
- Test Labels preview and download.
- Test Reports preview and download.
- Test User Management module permissions.

## Common deployment errors and fixes

- `DisallowedHost`: add the current host to `DJANGO_ALLOWED_HOSTS`.
- `CSRF verification failed`: add the full HTTPS origin to `CSRF_TRUSTED_ORIGINS`.
- `relation does not exist`: run migrations.
- `column does not exist`: migrations or schema are out of sync with the code.
- Static CSS missing: check `collectstatic`, WhiteNoise, and Docker build logs.
- Cloud Run health check fails: confirm the app listens on `$PORT`.
- Cloud Run timeout: increase timeout and memory.
- PDF download times out: increase `GUNICORN_TIMEOUT` and Cloud Run timeout.
- Supabase connection limit reached: reduce Cloud Run max instances and workers, use pooling.
- Drive upload 401: refresh token or OAuth credentials are invalid.
- Drive upload 403: Drive folder access or API scope is wrong.
- Cloudflare redirect loop: use Full or Full Strict SSL and confirm forwarded protocol.
- Custom domain opens but forms fail: check `CSRF_TRUSTED_ORIGINS`.
- Bot traffic creates cost: add Cloudflare WAF/rate limits and reduce Cloud Run max instances.

## Beginner debug flow

When production breaks, check in this order:

1. Cloud Run logs.
2. Environment variables in the active Cloud Run revision.
3. Supabase connection and migrations.
4. Cloudflare Worker route and DNS.
5. Django `ALLOWED_HOSTS` and CSRF settings.
6. Google Drive credentials.
7. User Management permissions.

Always fix one layer at a time. If the Cloud Run URL works but the custom domain fails, the problem is probably Cloudflare or host/CSRF settings. If both fail, check Cloud Run logs and environment variables first.
