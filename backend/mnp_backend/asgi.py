"""ASGI config for the MNP Django project."""

import os
from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mnp_backend.settings')

application = get_asgi_application()
