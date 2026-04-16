from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlparse
import os

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', 'django-insecure-change-this-key')
DEBUG = os.getenv('DJANGO_DEBUG', 'True').lower() in {'1', 'true', 'yes', 'on'}

ALLOWED_HOSTS = [
    host.strip() for host in os.getenv('DJANGO_ALLOWED_HOSTS', '127.0.0.1,localhost').split(',') if host.strip()
]

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'django_filters',
    'rest_framework_simplejwt',
    'corsheaders',
    'core',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'mnp_backend.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'mnp_backend.wsgi.application'
ASGI_APPLICATION = 'mnp_backend.asgi.application'


def _db_config():
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        raise ImproperlyConfigured(
            "DATABASE_URL is required (Postgres-only). "
            "Set it in backend/.env, e.g. postgresql://user:pass@localhost:5432/dbname"
        )

    parsed = urlparse(database_url)
    query = parse_qs(parsed.query)
    config = {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': parsed.path.lstrip('/'),
        'USER': parsed.username,
        'PASSWORD': parsed.password,
        'HOST': parsed.hostname,
        'PORT': parsed.port or '5432',
    }
    options = {}
    for key, values in (query or {}).items():
        if not key or not values:
            continue
        # Allow Postgres connection options like sslmode/options/etc in DATABASE_URL.
        options[str(key)] = str(values[-1])

    # Docker Desktop on macOS often has unreliable/no IPv6 routing. If your DB hostname resolves to
    # an IPv6 address first, connections can fail with "Network is unreachable".
    # Set DJANGO_DB_HOSTADDR to an IPv4 address to force IPv4 while keeping the hostname for TLS/SNI.
    hostaddr = (os.getenv("DJANGO_DB_HOSTADDR") or "").strip()
    if hostaddr:
        options.setdefault("hostaddr", hostaddr)

    connect_timeout = (os.getenv("DJANGO_DB_CONNECT_TIMEOUT") or "").strip()
    if connect_timeout:
        options.setdefault("connect_timeout", connect_timeout)
    if options:
        config['OPTIONS'] = options
    return {'default': config}

DATABASES = _db_config()

# Remote Postgres (e.g., Neon) can feel sluggish if we reconnect on every request.
# Reuse connections for a bit and health-check before reusing to avoid stale sockets.
CONN_HEALTH_CHECKS = os.getenv("DJANGO_DB_CONN_HEALTH_CHECKS", "True").lower() in {"1", "true", "yes", "on"}
if DATABASES.get("default", {}).get("ENGINE") == "django.db.backends.postgresql":
    try:
        DATABASES["default"]["CONN_MAX_AGE"] = int(os.getenv("DJANGO_DB_CONN_MAX_AGE", "60"))
    except (TypeError, ValueError):
        DATABASES["default"]["CONN_MAX_AGE"] = 60

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = os.getenv('DJANGO_TIME_ZONE', 'Asia/Kolkata')
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

STORAGES = {
    # Uploaded files (only used when we explicitly store files locally).
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    # Collected static files.
    "staticfiles": {
        "BACKEND": (
            "django.contrib.staticfiles.storage.StaticFilesStorage"
            if DEBUG
            else "whitenoise.storage.CompressedManifestStaticFilesStorage"
        ),
    },
}

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

CORS_ALLOW_ALL_ORIGINS = os.getenv('CORS_ALLOW_ALL_ORIGINS', 'False').lower() in {'1', 'true', 'yes', 'on'}
CORS_ALLOWED_ORIGINS = [
    origin.strip() for origin in os.getenv('CORS_ALLOWED_ORIGINS', '').split(',') if origin.strip()
]
CSRF_TRUSTED_ORIGINS = [
    origin.strip() for origin in os.getenv('CSRF_TRUSTED_ORIGINS', '').split(',') if origin.strip()
]
CORS_ALLOW_CREDENTIALS = os.getenv('CORS_ALLOW_CREDENTIALS', 'True').lower() in {'1', 'true', 'yes', 'on'}

AUTH_USER_MODEL = 'core.AppUser'

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'user': '120/min',
    },
}

LOGIN_URL = '/ui/login/'
LOGIN_REDIRECT_URL = '/ui/master-entry/'
LOGOUT_REDIRECT_URL = '/ui/login/'

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=120),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
}

# Fund request formsets can legitimately post a large number of recipient fields
# in one submission, especially for aid requests populated in batches.
DATA_UPLOAD_MAX_NUMBER_FIELDS = int(os.getenv('DJANGO_DATA_UPLOAD_MAX_NUMBER_FIELDS', '10000'))
