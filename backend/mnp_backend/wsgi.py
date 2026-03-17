"""WSGI config for the MNP Django project."""

import os
from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mnp_backend.settings')

application = get_wsgi_application()
