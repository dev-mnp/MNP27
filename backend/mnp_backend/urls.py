"""URL configuration for the MNP Django project."""

from __future__ import annotations

from django.contrib import admin
from django.contrib.auth.views import LoginView, LogoutView
from django.urls import include, path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from django.http import HttpResponse
from django.views.generic import RedirectView


urlpatterns = [
    path("", RedirectView.as_view(url="/ui/", permanent=False)),
    path("admin/", admin.site.urls),
    path("api/auth/token/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/auth/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("api/", include("core.urls")),
    path("ui/login/", LoginView.as_view(template_name="account/login.html"), name="ui-login"),
    path("ui/logout/", LogoutView.as_view(), name="ui-logout"),
    path("ui/", include("core.web_urls")),
    path("favicon.ico", lambda _: HttpResponse(status=204)),
]
