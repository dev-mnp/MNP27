from __future__ import annotations

from django import forms
from django.core.exceptions import ValidationError

from . import models


class ArticleForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].widget.attrs["list"] = "article-category-options"
        self.fields["master_category"].widget.attrs["list"] = "article-master-category-options"

    class Meta:
        model = models.Article
        fields = [
            "article_name",
            "article_name_tk",
            "cost_per_unit",
            "item_type",
            "category",
            "master_category",
            "is_active",
            "combo",
        ]
        widgets = {
            "article_name": forms.TextInput(attrs={"class": "input", "autofocus": True}),
            "article_name_tk": forms.TextInput(attrs={"class": "input"}),
            "cost_per_unit": forms.NumberInput(attrs={"class": "input", "step": "0.01"}),
            "item_type": forms.Select(attrs={"class": "input"}),
            "category": forms.TextInput(attrs={"class": "input"}),
            "master_category": forms.TextInput(attrs={"class": "input"}),
        }


class DistrictBeneficiaryEntryForm(forms.ModelForm):
    class Meta:
        model = models.DistrictBeneficiaryEntry
        fields = [
            "district",
            "application_number",
            "article",
            "article_cost_per_unit",
            "quantity",
            "total_amount",
            "notes",
            "status",
            "fund_request",
        ]
        widgets = {
            "district": forms.Select(attrs={"class": "input"}),
            "application_number": forms.TextInput(attrs={"class": "input"}),
            "article": forms.HiddenInput(),
            "article_cost_per_unit": forms.NumberInput(attrs={"class": "input", "step": "0.01"}),
            "quantity": forms.NumberInput(attrs={"class": "input"}),
            "total_amount": forms.NumberInput(attrs={"class": "input", "step": "0.01"}),
            "notes": forms.Textarea(attrs={"class": "textarea", "rows": 3}),
            "status": forms.Select(attrs={"class": "input"}),
            "fund_request": forms.Select(attrs={"class": "input"}),
        }

    def clean(self):
        cleaned = super().clean()
        article = cleaned.get("article")
        quantity = cleaned.get("quantity") or 0
        unit_cost = cleaned.get("article_cost_per_unit")
        if article and unit_cost in (None, 0):
            unit_cost = article.cost_per_unit
            cleaned["article_cost_per_unit"] = unit_cost
        if unit_cost is not None:
            cleaned["total_amount"] = unit_cost * quantity
        return cleaned


class PublicBeneficiaryEntryForm(forms.ModelForm):
    class Meta:
        model = models.PublicBeneficiaryEntry
        fields = [
            "application_number",
            "name",
            "aadhar_number",
            "is_handicapped",
            "gender",
            "female_status",
            "address",
            "mobile",
            "article",
            "article_cost_per_unit",
            "quantity",
            "total_amount",
            "notes",
            "status",
            "fund_request",
        ]
        widgets = {
            "application_number": forms.TextInput(attrs={"class": "input"}),
            "name": forms.TextInput(attrs={"class": "input"}),
            "aadhar_number": forms.TextInput(attrs={"class": "input"}),
            "gender": forms.Select(attrs={"class": "input"}),
            "female_status": forms.Select(attrs={"class": "input"}),
            "address": forms.Textarea(attrs={"class": "textarea", "rows": 3}),
            "mobile": forms.TextInput(attrs={"class": "input"}),
            "article": forms.HiddenInput(),
            "article_cost_per_unit": forms.NumberInput(attrs={"class": "input", "step": "0.01"}),
            "quantity": forms.NumberInput(attrs={"class": "input"}),
            "total_amount": forms.NumberInput(attrs={"class": "input", "step": "0.01"}),
            "notes": forms.Textarea(attrs={"class": "textarea", "rows": 3}),
            "status": forms.Select(attrs={"class": "input"}),
            "fund_request": forms.Select(attrs={"class": "input"}),
        }

    def clean(self):
        cleaned = super().clean()
        article = cleaned.get("article")
        quantity = cleaned.get("quantity") or 0
        unit_cost = cleaned.get("article_cost_per_unit")
        if article and unit_cost in (None, 0):
            unit_cost = article.cost_per_unit
            cleaned["article_cost_per_unit"] = unit_cost
        if unit_cost is not None:
            cleaned["total_amount"] = unit_cost * quantity
        return cleaned


class InstitutionsBeneficiaryEntryForm(forms.ModelForm):
    class Meta:
        model = models.InstitutionsBeneficiaryEntry
        fields = [
            "institution_name",
            "institution_type",
            "application_number",
            "address",
            "mobile",
            "article",
            "article_cost_per_unit",
            "quantity",
            "total_amount",
            "notes",
            "status",
            "fund_request",
        ]
        widgets = {
            "institution_name": forms.TextInput(attrs={"class": "input"}),
            "institution_type": forms.Select(attrs={"class": "input"}),
            "application_number": forms.TextInput(attrs={"class": "input"}),
            "address": forms.Textarea(attrs={"class": "textarea", "rows": 3}),
            "mobile": forms.TextInput(attrs={"class": "input"}),
            "article": forms.HiddenInput(),
            "article_cost_per_unit": forms.NumberInput(attrs={"class": "input", "step": "0.01"}),
            "quantity": forms.NumberInput(attrs={"class": "input"}),
            "total_amount": forms.NumberInput(attrs={"class": "input", "step": "0.01"}),
            "notes": forms.Textarea(attrs={"class": "textarea", "rows": 3}),
            "status": forms.Select(attrs={"class": "input"}),
            "fund_request": forms.Select(attrs={"class": "input"}),
        }

    def clean(self):
        cleaned = super().clean()
        article = cleaned.get("article")
        quantity = cleaned.get("quantity") or 0
        unit_cost = cleaned.get("article_cost_per_unit")
        if article and unit_cost in (None, 0):
            unit_cost = article.cost_per_unit
            cleaned["article_cost_per_unit"] = unit_cost
        if unit_cost is not None:
            cleaned["total_amount"] = unit_cost * quantity
        return cleaned


class ApplicationAttachmentUploadForm(forms.Form):
    ALLOWED_EXTENSIONS = {"pdf", "jpg", "jpeg", "png", "webp", "doc", "docx", "xls", "xlsx", "csv"}
    MAX_FILE_SIZE = 10 * 1024 * 1024
    MAX_FILES_PER_APPLICATION = 2

    file_name = forms.CharField(
        required=False,
        max_length=255,
        widget=forms.TextInput(
            attrs={
                "class": "input",
                "placeholder": "Optional display name",
            }
        ),
    )
    file = forms.FileField(
        widget=forms.ClearableFileInput(
            attrs={
                "class": "input",
                "accept": ".pdf,.jpg,.jpeg,.png,.webp,.doc,.docx,.xls,.xlsx,.csv",
            }
        )
    )

    def clean_file(self):
        uploaded = self.cleaned_data["file"]
        name = uploaded.name or ""
        extension = name.rsplit(".", 1)[-1].lower() if "." in name else ""
        if extension not in self.ALLOWED_EXTENSIONS:
            allowed = ", ".join(sorted(ext.upper() for ext in self.ALLOWED_EXTENSIONS))
            raise ValidationError(f"Unsupported file type. Allowed types: {allowed}.")
        if uploaded.size > self.MAX_FILE_SIZE:
            raise ValidationError("File size must be 10 MB or less.")
        return uploaded

    def clean_file_name(self):
        value = (self.cleaned_data.get("file_name") or "").strip()
        return value


class FundRequestForm(forms.ModelForm):
    action = forms.ChoiceField(
        required=False,
        choices=[
            ("draft", "Save draft"),
            ("submit", "Submit"),
        ],
        initial="draft",
    )

    class Meta:
        model = models.FundRequest
        fields = [
            "fund_request_type",
            "aid_type",
            "fund_request_number",
            "gst_number",
            "supplier_name",
            "supplier_address",
            "supplier_city",
            "supplier_state",
            "supplier_pincode",
            "purchase_order_number",
        ]
        widgets = {
            "fund_request_type": forms.RadioSelect(),
            "aid_type": forms.TextInput(attrs={"class": "input"}),
            "fund_request_number": forms.TextInput(attrs={"class": "input"}),
            "gst_number": forms.TextInput(attrs={"class": "input"}),
            "supplier_name": forms.TextInput(attrs={"class": "input"}),
            "supplier_address": forms.Textarea(attrs={"class": "textarea", "rows": 3}),
            "supplier_city": forms.TextInput(attrs={"class": "input"}),
            "supplier_state": forms.TextInput(attrs={"class": "input"}),
            "supplier_pincode": forms.TextInput(attrs={"class": "input"}),
            "purchase_order_number": forms.TextInput(attrs={"class": "input"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["fund_request_type"].choices = [
            (value, label) for value, label in self.fields["fund_request_type"].choices if value
        ]
        self.fields["fund_request_number"].required = False


class FundRequestRecipientForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["beneficiary_type"].choices = [("", "Select beneficiary type")] + [
            (value, label) for value, label in models.RecipientTypeChoices.choices
            if value in {
                models.RecipientTypeChoices.DISTRICT,
                models.RecipientTypeChoices.PUBLIC,
                models.RecipientTypeChoices.INSTITUTIONS,
            }
        ]
        beneficiary_choices = [("", "Select beneficiary")]
        if getattr(self.instance, "beneficiary", None):
            current_label = (
                self.instance.recipient_name
                or self.instance.name_of_beneficiary
                or self.instance.name_of_institution
                or self.instance.district_name
                or self.instance.beneficiary
            )
            beneficiary_choices.append((self.instance.beneficiary, current_label))
        self.fields["beneficiary"].widget.choices = beneficiary_choices

    class Meta:
        model = models.FundRequestRecipient
        fields = [
            "beneficiary_type",
            "beneficiary",
            "source_entry_id",
            "recipient_name",
            "name_of_beneficiary",
            "name_of_institution",
            "details",
            "fund_requested",
            "aadhar_number",
            "address",
            "cheque_in_favour",
            "cheque_no",
            "notes",
            "district_name",
        ]
        widgets = {
            "beneficiary_type": forms.Select(attrs={"class": "input js-beneficiary-type-select"}),
            "beneficiary": forms.Select(attrs={"class": "input js-beneficiary-select"}),
            "source_entry_id": forms.HiddenInput(),
            "recipient_name": forms.HiddenInput(),
            "name_of_beneficiary": forms.TextInput(attrs={"class": "input", "placeholder": "Name of beneficiary"}),
            "name_of_institution": forms.TextInput(attrs={"class": "input", "placeholder": "Name of institution"}),
            "details": forms.Textarea(attrs={"class": "textarea", "rows": 3, "placeholder": "Details"}),
            "fund_requested": forms.NumberInput(attrs={"class": "input", "step": "0.01", "min": "0"}),
            "aadhar_number": forms.TextInput(attrs={"class": "input", "placeholder": "Aadhaar number"}),
            "address": forms.HiddenInput(),
            "cheque_in_favour": forms.Textarea(attrs={"class": "textarea", "rows": 3, "placeholder": "Cheque / RTGS in Favour"}),
            "cheque_no": forms.HiddenInput(),
            "notes": forms.HiddenInput(),
            "district_name": forms.HiddenInput(),
        }


class FundRequestArticleForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["article"].required = False
        article_choices = [("", "Select article")]
        if getattr(self.instance, "article_name", None):
            article_choices.append((self.instance.article_name, self.instance.article_name))
        self.fields["article_name"].choices = article_choices

    class Meta:
        model = models.FundRequestArticle
        fields = [
            "article",
            "beneficiary",
            "article_name",
            "gst_no",
            "quantity",
            "unit_price",
            "price_including_gst",
            "value",
            "cumulative",
            "cheque_in_favour",
            "cheque_no",
        ]
        widgets = {
            "article": forms.HiddenInput(),
            "beneficiary": forms.HiddenInput(),
            "article_name": forms.Select(attrs={"class": "input js-article-select"}),
            "gst_no": forms.TextInput(attrs={"class": "input", "placeholder": "GST number"}),
            "quantity": forms.NumberInput(attrs={"class": "input", "min": "0"}),
            "unit_price": forms.NumberInput(attrs={"class": "input", "step": "0.01", "min": "0"}),
            "price_including_gst": forms.HiddenInput(),
            "value": forms.NumberInput(attrs={"class": "input", "step": "0.01", "readonly": "readonly"}),
            "cumulative": forms.HiddenInput(),
            "cheque_in_favour": forms.Textarea(attrs={"class": "textarea", "rows": 3, "placeholder": "Cheque / RTGS in Favour"}),
            "cheque_no": forms.HiddenInput(),
        }

    def clean(self):
        cleaned = super().clean()
        article = cleaned.get("article")
        if article and not cleaned.get("article_name"):
            cleaned["article_name"] = article.article_name
        quantity = cleaned.get("quantity") or 0
        unit_price = cleaned.get("unit_price") or 0
        cleaned["price_including_gst"] = unit_price * quantity
        cleaned["value"] = unit_price * quantity
        cleaned["cumulative"] = unit_price * quantity
        return cleaned


class FundRequestDocumentUploadForm(forms.Form):
    document_type = forms.ChoiceField(
        required=True,
        choices=models.FundRequestDocumentType.choices,
        widget=forms.Select(attrs={"class": "input"}),
    )
    file = forms.FileField(required=True, widget=forms.ClearableFileInput(attrs={"class": "input"}))


class MasterDataUploadForm(forms.Form):
    file = forms.FileField(required=True, widget=forms.ClearableFileInput(attrs={"class": "input"}))
    replace_existing = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={"style": "width: auto; margin-right: 8px;"}),
        help_text="For past history only: clear the old imported rows before loading the new file.",
    )


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
