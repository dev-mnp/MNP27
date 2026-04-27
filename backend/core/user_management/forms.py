from __future__ import annotations

"""Forms for user-management workflows."""

from django import forms
from django.core.cache import cache
from django.core.exceptions import ValidationError

from core import models


class AppUserPermissionFormMixin:
    permission_sections = []

    def _permission_default_role(self):
        if self.is_bound:
            return (self.data.get(self.add_prefix("role")) or self.initial.get("role") or getattr(self.instance, "role", None) or models.RoleChoices.VIEWER)
        return self.initial.get("role") or getattr(self.instance, "role", None) or models.RoleChoices.VIEWER

    def _initial_permission_map(self):
        if getattr(self.instance, "pk", None):
            return self.instance.get_module_permission_map()
        return models.build_role_module_permission_map(self._permission_default_role())

    def _init_permission_fields(self):
        permission_map = self._initial_permission_map()
        sections = []
        for definition in models.MODULE_PERMISSION_DEFINITIONS:
            module_key = str(definition["key"])
            module_permissions = permission_map.get(module_key, {})
            section_fields = []
            for action in definition["actions"]:
                field_name = f"perm__{module_key}__{action}"
                self.fields[field_name] = forms.BooleanField(required=False)
                self.fields[field_name].widget.attrs.update({"style": "width:auto; margin-right:8px;"})
                self.fields[field_name].initial = module_permissions.get(f"can_{action}", False)
                section_fields.append(
                    {
                        "name": field_name,
                        "label": models.MODULE_PERMISSION_ACTION_LABELS[action],
                        "bound_field": self[field_name],
                    }
                )
            sections.append({"label": definition["label"], "fields": section_fields})
        self.permission_sections = sections

    def save_module_permissions(self, user):
        existing = {permission.module_key: permission for permission in user.module_permissions.all()}
        for definition in models.MODULE_PERMISSION_DEFINITIONS:
            module_key = str(definition["key"])
            permission = existing.get(module_key) or models.UserModulePermission(user=user, module_key=module_key)
            for action in models.ALL_MODULE_PERMISSION_ACTIONS:
                field_name = f"perm__{module_key}__{action}"
                setattr(permission, f"can_{action}", bool(self.cleaned_data.get(field_name, False)))
            permission.save()
        if hasattr(user, "_resolved_module_permission_map"):
            delattr(user, "_resolved_module_permission_map")
        cache.delete(f"mnp27:user_module_perms:v2:{user.pk}:{user.role}")


class AppUserCreateForm(AppUserPermissionFormMixin, forms.ModelForm):
    password1 = forms.CharField(widget=forms.PasswordInput(attrs={"class": "input"}), min_length=8)
    password2 = forms.CharField(widget=forms.PasswordInput(attrs={"class": "input"}), min_length=8)

    class Meta:
        model = models.AppUser
        fields = ["first_name", "last_name", "email", "role", "status"]
        widgets = {
            "first_name": forms.TextInput(attrs={"class": "input"}),
            "last_name": forms.TextInput(attrs={"class": "input"}),
            "email": forms.EmailInput(attrs={"class": "input"}),
            "role": forms.Select(attrs={"class": "input"}),
            "status": forms.Select(attrs={"class": "input"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._init_permission_fields()

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").strip().lower()
        if models.AppUser.objects.filter(email__iexact=email).exists():
            raise ValidationError("A user with this email already exists.")
        return email

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("password1") != cleaned.get("password2"):
            raise ValidationError("Passwords do not match.")
        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password1"])
        user.username = None
        if commit:
            user.save()
            self.save_module_permissions(user)
        return user


class AppUserUpdateForm(AppUserPermissionFormMixin, forms.ModelForm):
    password1 = forms.CharField(required=False, widget=forms.PasswordInput(attrs={"class": "input", "placeholder": "Leave blank to keep current password"}), min_length=8)
    password2 = forms.CharField(required=False, widget=forms.PasswordInput(attrs={"class": "input", "placeholder": "Repeat new password"}), min_length=8)

    class Meta:
        model = models.AppUser
        fields = ["first_name", "last_name", "email", "role", "status"]
        widgets = {
            "first_name": forms.TextInput(attrs={"class": "input"}),
            "last_name": forms.TextInput(attrs={"class": "input"}),
            "email": forms.EmailInput(attrs={"class": "input"}),
            "role": forms.Select(attrs={"class": "input"}),
            "status": forms.Select(attrs={"class": "input"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._init_permission_fields()

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").strip().lower()
        qs = models.AppUser.objects.filter(email__iexact=email).exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError("A user with this email already exists.")
        return email

    def clean(self):
        cleaned = super().clean()
        p1 = cleaned.get("password1") or ""
        p2 = cleaned.get("password2") or ""
        if p1 or p2:
            if p1 != p2:
                raise ValidationError("Passwords do not match.")
        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        password = self.cleaned_data.get("password1") or ""
        if password:
            user.set_password(password)
        if commit:
            user.save()
            self.save_module_permissions(user)
        return user


class AppUserPasswordResetForm(forms.Form):
    password1 = forms.CharField(widget=forms.PasswordInput(attrs={"class": "input"}), min_length=8)
    password2 = forms.CharField(widget=forms.PasswordInput(attrs={"class": "input"}), min_length=8)

    def clean(self):
        cleaned = super().clean()
        if (cleaned.get("password1") or "") != (cleaned.get("password2") or ""):
            raise ValidationError("Passwords do not match.")
        return cleaned
