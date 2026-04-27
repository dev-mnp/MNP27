
from __future__ import annotations

"""Views for user management workflows."""

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.views import View
from django.views.generic import CreateView, FormView, ListView, UpdateView

from core import models
from core.user_management.forms import AppUserCreateForm, AppUserPasswordResetForm, AppUserUpdateForm
from core.shared.permissions import AdminRequiredMixin


class UserManagementListView(LoginRequiredMixin, AdminRequiredMixin, ListView):
    module_key = models.ModuleKeyChoices.USER_MANAGEMENT
    permission_action = "view"
    model = models.AppUser
    template_name = "user_management/user_management.html"
    context_object_name = "users"

    def get_queryset(self):
        queryset = models.AppUser.objects.select_related("created_by").order_by("first_name", "email")
        if q := (self.request.GET.get("q") or "").strip():
            queryset = queryset.filter(
                Q(first_name__icontains=q)
                | Q(last_name__icontains=q)
                | Q(email__icontains=q)
                | Q(role__icontains=q)
                | Q(status__icontains=q)
            )
        if role := (self.request.GET.get("role") or "").strip():
            queryset = queryset.filter(role=role)
        if status := (self.request.GET.get("status") or "").strip():
            queryset = queryset.filter(status=status)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["filters"] = {
            "q": (self.request.GET.get("q") or "").strip(),
            "role": (self.request.GET.get("role") or "").strip(),
            "status": (self.request.GET.get("status") or "").strip(),
        }
        context["role_choices"] = models.RoleChoices.choices
        context["status_choices"] = models.StatusChoices.choices
        context["can_create_edit"] = self.request.user.has_module_permission(
            models.ModuleKeyChoices.USER_MANAGEMENT, "create_edit"
        )
        context["can_delete"] = self.request.user.has_module_permission(
            models.ModuleKeyChoices.USER_MANAGEMENT, "delete"
        )
        context["can_reset_password"] = self.request.user.has_module_permission(
            models.ModuleKeyChoices.USER_MANAGEMENT, "reset_password"
        )
        return context


class UserManagementCreateView(LoginRequiredMixin, AdminRequiredMixin, CreateView):
    module_key = models.ModuleKeyChoices.USER_MANAGEMENT
    permission_action = "create_edit"
    model = models.AppUser
    form_class = AppUserCreateForm
    template_name = "user_management/user_form.html"

    def get_success_url(self):
        return reverse("ui:user-list")

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        messages.success(self.request, "User created successfully.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Create User"
        context["submit_label"] = "Create"
        return context


class UserManagementUpdateView(LoginRequiredMixin, AdminRequiredMixin, UpdateView):
    module_key = models.ModuleKeyChoices.USER_MANAGEMENT
    permission_action = "create_edit"
    model = models.AppUser
    form_class = AppUserUpdateForm
    template_name = "user_management/user_form.html"

    def get_success_url(self):
        return reverse("ui:user-list")

    def form_valid(self, form):
        if self.object == self.request.user:
            if form.cleaned_data.get("status") != models.StatusChoices.ACTIVE:
                form.add_error("status", "You cannot deactivate your own account.")
                return self.form_invalid(form)
        messages.success(self.request, "User updated successfully.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Edit User"
        context["submit_label"] = "Save"
        return context


class UserManagementPasswordResetView(LoginRequiredMixin, AdminRequiredMixin, FormView):
    module_key = models.ModuleKeyChoices.USER_MANAGEMENT
    permission_action = "reset_password"
    form_class = AppUserPasswordResetForm
    template_name = "user_management/user_password_reset.html"

    def dispatch(self, request, *args, **kwargs):
        self.target_user = get_object_or_404(models.AppUser, pk=kwargs["pk"])
        return super().dispatch(request, *args, **kwargs)

    def get_success_url(self):
        return reverse("ui:user-list")

    def form_valid(self, form):
        self.target_user.set_password(form.cleaned_data["password1"])
        self.target_user.save(update_fields=["password", "updated_at"])
        messages.success(self.request, f"Password reset for {self.target_user.display_name}.")
        return HttpResponseRedirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Reset Password"
        context["target_user"] = self.target_user
        context["submit_label"] = "Reset Password"
        return context


class UserManagementDeleteView(LoginRequiredMixin, AdminRequiredMixin, View):
    module_key = models.ModuleKeyChoices.USER_MANAGEMENT
    permission_action = "delete"

    def post(self, request, *args, **kwargs):
        user = get_object_or_404(models.AppUser, pk=kwargs["pk"])
        if user == request.user:
            messages.error(request, "You cannot delete your own account.")
            return HttpResponseRedirect(reverse("ui:user-list"))
        user.delete()
        messages.success(request, "User deleted successfully.")
        return HttpResponseRedirect(reverse("ui:user-list"))
