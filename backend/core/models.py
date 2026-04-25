from __future__ import annotations

"""
Core data model definitions for the MNP27 backend.

Use this file when you need to change persisted business entities, numbering
formats, role/module permissions, or relationships between the major modules
such as master entry, fund requests, inventory planning, and purchase orders.
"""

from decimal import Decimal
from uuid import uuid4

from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.models import AbstractUser
from django.core.cache import cache
from django.core.validators import MinLengthValidator, MinValueValidator
from django.db import models
from django.utils import timezone


def parse_fund_request_sequence(value) -> int | None:
    raw = str(value or "").strip().upper()
    if not raw:
        return None
    if not raw.startswith("FR"):
        return None
    suffix = raw[2:]
    if suffix.startswith("-"):
        suffix = suffix[1:]
    if not suffix.isdigit():
        return None
    return int(suffix)


def format_fund_request_number(value) -> str:
    if value in {None, ""}:
        return ""
    sequence = parse_fund_request_sequence(value)
    if sequence is None:
        return str(value).strip()
    return f"FR-{sequence:03d}"


# =========================
# Shared Choices / Constants
# =========================
class RoleChoices(models.TextChoices):
    ADMIN = "admin", "Admin"
    EDITOR = "editor", "Editor"
    VIEWER = "viewer", "Viewer"


class StatusChoices(models.TextChoices):
    ACTIVE = "active", "Active"
    INACTIVE = "inactive", "Inactive"


class ModuleKeyChoices(models.TextChoices):
    APPLICATION_ENTRY = "application_entry", "Application Entry"
    ARTICLE_MANAGEMENT = "article_management", "Article Management"
    BASE_FILES = "base_files", "Base Files"
    INVENTORY_PLANNING = "inventory_planning", "Inventory Planning"
    SEAT_ALLOCATION = "seat_allocation", "Seat Allocation"
    SEQUENCE_LIST = "sequence_list", "Sequence List"
    TOKEN_GENERATION = "token_generation", "Token Generation"
    LABELS = "labels", "Labels"
    REPORTS = "reports", "Reports"
    ORDER_FUND_REQUEST = "order_fund_request", "Order & Fund Request"
    PURCHASE_ORDER = "purchase_order", "Purchase Order"
    AUDIT_LOGS = "audit_logs", "Audit Logs"
    USER_MANAGEMENT = "user_management", "User Management"


MODULE_PERMISSION_ACTION_LABELS = {
    "view": "View",
    "create_edit": "Create / Edit",
    "delete": "Delete",
    "submit": "Submit",
    "reopen": "Reopen",
    "export": "Export",
    "upload_replace": "Upload / Replace",
    "reset_password": "Reset Password",
}

ALL_MODULE_PERMISSION_ACTIONS = tuple(MODULE_PERMISSION_ACTION_LABELS.keys())

MODULE_PERMISSION_DEFINITIONS = [
    {
        "key": ModuleKeyChoices.APPLICATION_ENTRY,
        "label": "Application Entry",
        "actions": ("view", "create_edit", "delete", "submit", "reopen"),
    },
    {
        "key": ModuleKeyChoices.ARTICLE_MANAGEMENT,
        "label": "Article Management",
        "actions": ("view", "create_edit", "delete"),
    },
    {
        "key": ModuleKeyChoices.BASE_FILES,
        "label": "Base Files",
        "actions": ("view", "upload_replace"),
    },
    {
        "key": ModuleKeyChoices.INVENTORY_PLANNING,
        "label": "Inventory Planning",
        "actions": ("view", "export"),
    },
    {
        "key": ModuleKeyChoices.SEAT_ALLOCATION,
        "label": "Seat Allocation",
        "actions": ("view", "create_edit", "export", "upload_replace"),
    },
    {
        "key": ModuleKeyChoices.SEQUENCE_LIST,
        "label": "Sequence List",
        "actions": ("view", "create_edit", "export"),
    },
    {
        "key": ModuleKeyChoices.TOKEN_GENERATION,
        "label": "Token Generation",
        "actions": ("view", "create_edit", "export", "upload_replace"),
    },
    {
        "key": ModuleKeyChoices.LABELS,
        "label": "Labels",
        "actions": ("view", "create_edit", "export", "upload_replace"),
    },
    {
        "key": ModuleKeyChoices.REPORTS,
        "label": "Reports",
        "actions": ("view", "create_edit", "export", "upload_replace"),
    },
    {
        "key": ModuleKeyChoices.ORDER_FUND_REQUEST,
        "label": "Order & Fund Request",
        "actions": ("view", "create_edit", "delete", "submit", "reopen"),
    },
    {
        "key": ModuleKeyChoices.PURCHASE_ORDER,
        "label": "Purchase Order",
        "actions": ("view", "create_edit", "delete", "submit", "reopen"),
    },
    {
        "key": ModuleKeyChoices.AUDIT_LOGS,
        "label": "Audit Logs",
        "actions": ("view",),
    },
    {
        "key": ModuleKeyChoices.USER_MANAGEMENT,
        "label": "User Management",
        "actions": ("view", "create_edit", "delete", "reset_password"),
    },
]

ROLE_MODULE_PERMISSION_DEFAULTS = {
    RoleChoices.ADMIN: {
        definition["key"]: set(definition["actions"])
        for definition in MODULE_PERMISSION_DEFINITIONS
    },
    RoleChoices.EDITOR: {
        ModuleKeyChoices.APPLICATION_ENTRY: {"view", "create_edit", "submit", "reopen"},
        ModuleKeyChoices.ARTICLE_MANAGEMENT: {"view", "create_edit"},
        ModuleKeyChoices.BASE_FILES: {"view", "upload_replace"},
        ModuleKeyChoices.INVENTORY_PLANNING: {"view", "export"},
        ModuleKeyChoices.SEAT_ALLOCATION: {"view", "create_edit", "export", "upload_replace"},
        ModuleKeyChoices.SEQUENCE_LIST: {"view", "create_edit", "export"},
        ModuleKeyChoices.TOKEN_GENERATION: {"view", "create_edit", "export", "upload_replace"},
        ModuleKeyChoices.LABELS: {"view", "create_edit", "export", "upload_replace"},
        ModuleKeyChoices.REPORTS: {"view", "create_edit", "export", "upload_replace"},
        ModuleKeyChoices.ORDER_FUND_REQUEST: {"view", "create_edit", "submit", "reopen"},
        ModuleKeyChoices.PURCHASE_ORDER: {"view", "create_edit", "submit", "reopen"},
        ModuleKeyChoices.AUDIT_LOGS: set(),
        ModuleKeyChoices.USER_MANAGEMENT: set(),
    },
    RoleChoices.VIEWER: {
        ModuleKeyChoices.APPLICATION_ENTRY: {"view"},
        ModuleKeyChoices.ARTICLE_MANAGEMENT: {"view"},
        ModuleKeyChoices.BASE_FILES: {"view"},
        ModuleKeyChoices.INVENTORY_PLANNING: {"view"},
        ModuleKeyChoices.SEAT_ALLOCATION: {"view"},
        ModuleKeyChoices.SEQUENCE_LIST: {"view"},
        ModuleKeyChoices.TOKEN_GENERATION: {"view"},
        ModuleKeyChoices.LABELS: {"view"},
        ModuleKeyChoices.REPORTS: {"view"},
        ModuleKeyChoices.ORDER_FUND_REQUEST: {"view"},
        ModuleKeyChoices.PURCHASE_ORDER: {"view"},
        ModuleKeyChoices.AUDIT_LOGS: set(),
        ModuleKeyChoices.USER_MANAGEMENT: set(),
    },
}


def build_role_module_permission_map(role: str):
    permission_map = {}
    defaults = ROLE_MODULE_PERMISSION_DEFAULTS.get(role, {})
    for definition in MODULE_PERMISSION_DEFINITIONS:
        module_key = str(definition["key"])
        allowed_actions = defaults.get(definition["key"], set())
        permission_map[module_key] = {
            f"can_{action}": action in allowed_actions for action in ALL_MODULE_PERMISSION_ACTIONS
        }
    return permission_map


class ItemTypeChoices(models.TextChoices):
    ARTICLE = "Article", "Article"
    AID = "Aid", "Aid"
    PROJECT = "Project", "Project"


class FundRequestTypeChoices(models.TextChoices):
    AID = "Aid", "Aid"
    ARTICLE = "Article", "Article"


class RecipientTypeChoices(models.TextChoices):
    DISTRICT = "District", "District"
    PUBLIC = "Public", "Public"
    INSTITUTIONS = "Institutions", "Institutions"
    OTHERS = "Others", "Others"


class BeneficiaryStatusChoices(models.TextChoices):
    DRAFT = "draft", "Draft"
    SUBMITTED = "submitted", "Submitted"
    ARCHIVED = "archived", "Archived"
    PENDING = "pending", "Pending"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"
    COMPLETED = "completed", "Completed"


class FundRequestStatusChoices(models.TextChoices):
    DRAFT = "draft", "Draft"
    SUBMITTED = "submitted", "Submitted"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"
    COMPLETED = "completed", "Completed"


class AadhaarVerificationStatusChoices(models.TextChoices):
    VERIFIED = "VERIFIED", "Verified"
    NOT_AVAILABLE = "NOT_AVAILABLE", "Not Available"
    PENDING_VERIFICATION = "PENDING_VERIFICATION", "Pending Verification"


class FundRequestDocumentType(models.TextChoices):
    FUND_REQUEST = "fund_request", "Fund Request"
    PURCHASE_ORDER = "purchase_order", "Purchase Order"


class OrderStatusChoices(models.TextChoices):
    PENDING = "pending", "Pending"
    ORDERED = "ordered", "Ordered"
    RECEIVED = "received", "Received"
    CANCELLED = "cancelled", "Cancelled"


class ActionTypeChoices(models.TextChoices):
    CREATE = "CREATE", "Create"
    UPDATE = "UPDATE", "Update"
    DELETE = "DELETE", "Delete"
    LOGIN = "LOGIN", "Login"
    LOGOUT = "LOGOUT", "Logout"
    EXPORT = "EXPORT", "Export"
    STATUS_CHANGE = "STATUS_CHANGE", "Status Change"


class GenderChoices(models.TextChoices):
    MALE = "Male", "Male"
    FEMALE = "Female", "Female"
    TRANSGENDER = "Transgender", "Transgender"


class FemaleStatusChoices(models.TextChoices):
    SINGLE = "Single", "Single"
    MARRIED = "Married", "Married"
    WIDOWED = "Widowed", "Widowed"
    DIVORCED = "Divorced", "Divorced"
    SEPARATED = "Separated", "Separated"
    DESERTED = "Deserted", "Deserted"
    SINGLE_MOTHER = "Single Mother", "Single Mother"
    DESTITUTE_WOMAN = "Destitute Woman (no income/support)", "Destitute Woman (no income/support)"
    FEMALE_HEAD = "Female Head of Household", "Female Head of Household"
    DOMESTIC_VIOLENCE = "Victim of Domestic Violence", "Victim of Domestic Violence"
    ABUSE_SURVIVOR = "Survivor of Abuse", "Survivor of Abuse"
    ELDERLY_WOMAN = "Elderly Woman (60+)", "Elderly Woman (60+)"
    HOMELESS = "Homeless", "Homeless"
    ORPHAN = "Orphan / No Family Support", "Orphan / No Family Support"
    MIGRANT_WOMAN = "Migrant Woman", "Migrant Woman"
    CAREGIVER = "Caregiver (children / elderly / disabled)", "Caregiver (children / elderly / disabled)"
    EMPLOYED = "Employed", "Employed"
    SELF_EMPLOYED = "Self-employed", "Self-employed"
    UNEMPLOYED = "Unemployed", "Unemployed"
    STUDENT = "Student", "Student"


class DisabilityCategoryChoices(models.TextChoices):
    BLINDNESS_LOW_VISION = "Blindness / Low Vision", "Blindness / Low Vision"
    DEAF_HARD_HEARING = "Deaf / Hard of Hearing", "Deaf / Hard of Hearing"
    LOCOMOTOR_DISABILITY = "Locomotor Disability", "Locomotor Disability"
    CEREBRAL_PALSY = "Cerebral Palsy", "Cerebral Palsy"
    LEPROSY_CURED = "Leprosy Cured", "Leprosy Cured"
    DWARFISM = "Dwarfism", "Dwarfism"
    ACID_ATTACK_VICTIM = "Acid Attack Victim", "Acid Attack Victim"
    MUSCULAR_DYSTROPHY = "Muscular Dystrophy", "Muscular Dystrophy"
    AUTISM_SPECTRUM_DISORDER = "Autism Spectrum Disorder", "Autism Spectrum Disorder"
    INTELLECTUAL_DISABILITY = "Intellectual Disability", "Intellectual Disability"
    SPECIFIC_LEARNING_DISABILITY = "Specific Learning Disability", "Specific Learning Disability"
    MENTAL_ILLNESS = "Mental Illness", "Mental Illness"
    MULTIPLE_DISABILITY = "Multiple Disability", "Multiple Disability"
    DEAF_BLINDNESS = "Deaf-Blindness", "Deaf-Blindness"
    MIXED = "Mixed", "Mixed"
    OTHER = "Other", "Other"


class HandicappedStatusChoices(models.TextChoices):
    NO = "No", "No"
    BLINDNESS_LOW_VISION = "Blindness / Low Vision", "Blindness / Low Vision"
    DEAF_HARD_HEARING = "Deaf / Hard of Hearing", "Deaf / Hard of Hearing"
    LOCOMOTOR_DISABILITY = "Locomotor Disability", "Locomotor Disability"
    CEREBRAL_PALSY = "Cerebral Palsy", "Cerebral Palsy"
    LEPROSY_CURED = "Leprosy Cured", "Leprosy Cured"
    DWARFISM = "Dwarfism", "Dwarfism"
    ACID_ATTACK_VICTIM = "Acid Attack Victim", "Acid Attack Victim"
    MUSCULAR_DYSTROPHY = "Muscular Dystrophy", "Muscular Dystrophy"
    AUTISM_SPECTRUM_DISORDER = "Autism Spectrum Disorder", "Autism Spectrum Disorder"
    INTELLECTUAL_DISABILITY = "Intellectual Disability", "Intellectual Disability"
    SPECIFIC_LEARNING_DISABILITY = "Specific Learning Disability", "Specific Learning Disability"
    MENTAL_ILLNESS = "Mental Illness", "Mental Illness"
    MULTIPLE_DISABILITY = "Multiple Disability", "Multiple Disability"
    DEAF_BLINDNESS = "Deaf-Blindness", "Deaf-Blindness"
    MIXED = "Mixed", "Mixed"
    OTHER = "Other", "Other"


class InstitutionTypeChoices(models.TextChoices):
    INSTITUTIONS = "institutions", "Institutions"
    OTHERS = "others", "Others"


# =========================
# Shared Base Utilities
# =========================
class BaseTimestampedModel(models.Model):
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


def non_negative_decimal(value: Decimal | int | float) -> Decimal:
    value = Decimal(str(value or 0))
    if value < 0:
        raise ValueError("Amount cannot be negative.")
    return value


# =========================
# Users / Permissions Models
# =========================
class AppUserManager(BaseUserManager):
    """Manager tuned for email-based custom user model."""

    use_in_migrations = True

    def _create_user(self, email: str, password: str | None, **extra_fields):
        if not email:
            raise ValueError("The Email field must be set.")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email: str, password: str | None = None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email: str, password: str | None = None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")
        return self._create_user(email, password, **extra_fields)


class AppUser(AbstractUser):
    """
    Role-aware user model used by all app modules.
    """

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    username = None
    email = models.EmailField(unique=True)
    role = models.CharField(max_length=12, choices=RoleChoices.choices, default=RoleChoices.VIEWER)
    status = models.CharField(max_length=9, choices=StatusChoices.choices, default=StatusChoices.ACTIVE)
    created_by = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_app_users",
    )
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    objects = AppUserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    class Meta:
        db_table = "app_users"
        verbose_name = "App User"
        verbose_name_plural = "App Users"

    def __str__(self) -> str:
        return self.email

    @property
    def display_name(self) -> str:
        full = self.get_full_name().strip()
        return full or self.email

    def get_module_permission_map(self):
        cache_name = "_resolved_module_permission_map"
        if hasattr(self, cache_name):
            return getattr(self, cache_name)

        # This is used by the sidebar on every page. Cache it briefly to avoid a DB hit per request
        # when running against a remote Postgres (Supabase/Neon).
        cache_key = f"mnp27:user_module_perms:{self.pk}:{self.role}"
        cached = cache.get(cache_key)
        if cached is not None:
            setattr(self, cache_name, cached)
            return cached

        permission_map = build_role_module_permission_map(self.role)
        if hasattr(self, "_prefetched_objects_cache") and "module_permissions" in self._prefetched_objects_cache:
            permission_rows = list(self._prefetched_objects_cache["module_permissions"])
        else:
            permission_rows = list(self.module_permissions.all())
        for permission in permission_rows:
            module_key = permission.module_key
            permission_map[module_key] = {
                f"can_{action}": bool(getattr(permission, f"can_{action}", False))
                for action in ALL_MODULE_PERMISSION_ACTIONS
            }
        cache.set(cache_key, permission_map, timeout=300)
        setattr(self, cache_name, permission_map)
        return permission_map

    def has_module_permission(self, module_key, action="view"):
        if not getattr(self, "is_authenticated", False):
            return False
        if self.is_superuser:
            return True
        if self.status != StatusChoices.ACTIVE:
            return False
        resolved_key = getattr(module_key, "value", module_key)
        permission_field = action if str(action).startswith("can_") else f"can_{action}"
        return bool(self.get_module_permission_map().get(str(resolved_key), {}).get(permission_field, False))


class UserModulePermission(BaseTimestampedModel):
    user = models.ForeignKey(AppUser, on_delete=models.CASCADE, related_name="module_permissions")
    module_key = models.CharField(max_length=64, choices=ModuleKeyChoices.choices)
    can_view = models.BooleanField(default=False)
    can_create_edit = models.BooleanField(default=False)
    can_delete = models.BooleanField(default=False)
    can_submit = models.BooleanField(default=False)
    can_reopen = models.BooleanField(default=False)
    can_export = models.BooleanField(default=False)
    can_upload_replace = models.BooleanField(default=False)
    can_reset_password = models.BooleanField(default=False)

    class Meta:
        db_table = "user_module_permissions"
        verbose_name = "User Module Permission"
        verbose_name_plural = "User Module Permissions"
        constraints = [
            models.UniqueConstraint(fields=["user", "module_key"], name="unique_user_module_permission"),
        ]
        ordering = ["module_key"]

    def __str__(self) -> str:
        return f"{self.user.email} - {self.get_module_key_display()}"


# =========================
# Article Management Models
# =========================
class Article(BaseTimestampedModel):
    article_name = models.CharField(max_length=255, unique=True)
    article_name_tk = models.CharField(max_length=255, blank=True, null=True)
    cost_per_unit = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    allow_manual_price = models.BooleanField(default=False)
    item_type = models.CharField(max_length=20, choices=ItemTypeChoices.choices, default=ItemTypeChoices.ARTICLE)
    category = models.CharField(max_length=200, blank=True, null=True)
    master_category = models.CharField(max_length=200, blank=True, null=True)
    comments = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    combo = models.BooleanField(default=False)

    class Meta:
        db_table = "articles"
        verbose_name = "Article"
        verbose_name_plural = "Articles"
        indexes = [
            models.Index(fields=["article_name"]),
            models.Index(fields=["item_type", "is_active"]),
            models.Index(fields=["category"]),
        ]

    def __str__(self) -> str:
        return self.article_name


class Vendor(BaseTimestampedModel):
    vendor_name = models.CharField(max_length=255)
    gst_number = models.CharField(max_length=64, blank=True, null=True)
    phone_number = models.CharField(max_length=32, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    city = models.CharField(max_length=120, blank=True, null=True)
    state = models.CharField(max_length=120, blank=True, null=True)
    pincode = models.CharField(max_length=20, blank=True, null=True)
    cheque_in_favour = models.CharField(max_length=255, blank=True, null=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "vendors"
        verbose_name = "Vendor"
        verbose_name_plural = "Vendors"
        indexes = [
            models.Index(fields=["vendor_name"]),
            models.Index(fields=["gst_number"]),
            models.Index(fields=["is_active"]),
        ]

    def __str__(self) -> str:
        return self.vendor_name


# =========================
# Application Entry Models
# =========================
class DistrictMaster(BaseTimestampedModel):
    district_name = models.CharField(max_length=255, unique=True)
    allotted_budget = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    president_name = models.CharField(max_length=255)
    # Phone numbers sometimes include multiple contacts or separators (e.g. "987.. & 988..").
    mobile_number = models.CharField(max_length=50)
    application_number = models.CharField(max_length=120)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "district_master"
        verbose_name = "District"
        verbose_name_plural = "Districts"
        indexes = [
            models.Index(fields=["district_name"]),
            models.Index(fields=["is_active"]),
        ]

    def __str__(self) -> str:
        return self.district_name


# =========================
# Order / Fund Request Models
# =========================
class FundRequest(BaseTimestampedModel):
    fund_request_type = models.CharField(max_length=20, choices=FundRequestTypeChoices.choices)
    fund_request_number = models.CharField(max_length=80, unique=True, blank=True, null=True)
    status = models.CharField(max_length=12, choices=FundRequestStatusChoices.choices, default=FundRequestStatusChoices.DRAFT)
    total_amount = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    aid_type = models.CharField(max_length=255, blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    gst_number = models.CharField(max_length=64, blank=True, null=True)
    supplier_name = models.CharField(max_length=255, blank=True, null=True)
    supplier_address = models.TextField(blank=True, null=True)
    supplier_city = models.CharField(max_length=120, blank=True, null=True)
    supplier_state = models.CharField(max_length=120, blank=True, null=True)
    supplier_pincode = models.CharField(max_length=20, blank=True, null=True)
    purchase_order_number = models.CharField(max_length=80, blank=True, null=True)
    created_by = models.ForeignKey(
        "core.AppUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="fund_requests",
    )

    class Meta:
        db_table = "fund_request"
        verbose_name = "Fund Request"
        verbose_name_plural = "Fund Requests"
        indexes = [
            models.Index(fields=["fund_request_type"]),
            models.Index(fields=["status"]),
            models.Index(fields=["fund_request_number"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.fund_request_type} {self.formatted_fund_request_number}"

    @property
    def formatted_fund_request_number(self) -> str:
        return format_fund_request_number(self.fund_request_number)


class FundRequestRecipient(BaseTimestampedModel):
    fund_request = models.ForeignKey(FundRequest, on_delete=models.CASCADE, related_name="recipients")
    beneficiary_type = models.CharField(max_length=20, choices=RecipientTypeChoices.choices, blank=True, null=True)
    source_entry_id = models.PositiveIntegerField(blank=True, null=True)
    beneficiary = models.TextField(blank=True, null=True)
    recipient_name = models.CharField(max_length=255)
    name_of_beneficiary = models.CharField(max_length=255, blank=True, null=True)
    name_of_institution = models.CharField(max_length=255, blank=True, null=True)
    details = models.TextField(blank=True, null=True)
    fund_requested = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    aadhar_number = models.CharField(max_length=20, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    cheque_in_favour = models.CharField(max_length=255, blank=True, null=True)
    cheque_no = models.CharField(max_length=120, blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    district_name = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        db_table = "fund_request_recipients"
        verbose_name = "Fund Request Recipient"
        verbose_name_plural = "Fund Request Recipients"
        indexes = [
            models.Index(fields=["fund_request"]),
            models.Index(fields=["beneficiary_type"]),
            models.Index(fields=["beneficiary_type", "source_entry_id"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["beneficiary_type", "source_entry_id"],
                condition=models.Q(source_entry_id__isnull=False),
                name="uniq_fund_request_recipient_source_global",
            )
        ]

    def __str__(self) -> str:
        return self.recipient_name or "Recipient"


class FundRequestArticle(BaseTimestampedModel):
    fund_request = models.ForeignKey(FundRequest, on_delete=models.CASCADE, related_name="articles")
    article = models.ForeignKey(Article, on_delete=models.RESTRICT, related_name="fund_request_lines")
    vendor = models.ForeignKey(
        Vendor,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="fund_request_articles",
    )
    sl_no = models.PositiveIntegerField(blank=True, null=True)
    beneficiary = models.TextField(blank=True, null=True)
    article_name = models.CharField(max_length=255)
    vendor_name = models.CharField(max_length=255, blank=True, null=True)
    gst_no = models.CharField(max_length=64, blank=True, null=True)
    vendor_address = models.TextField(blank=True, null=True)
    vendor_city = models.CharField(max_length=120, blank=True, null=True)
    vendor_state = models.CharField(max_length=120, blank=True, null=True)
    vendor_pincode = models.CharField(max_length=20, blank=True, null=True)
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    price_including_gst = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    value = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    cumulative = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    cheque_in_favour = models.CharField(max_length=255, blank=True, null=True)
    cheque_no = models.CharField(max_length=120, blank=True, null=True)
    supplier_article_name = models.CharField(max_length=255, blank=True, null=True)
    description = models.TextField(blank=True, null=True)

    class Meta:
        db_table = "fund_request_articles"
        verbose_name = "Fund Request Article"
        verbose_name_plural = "Fund Request Articles"
        indexes = [
            models.Index(fields=["fund_request"]),
            models.Index(fields=["article"]),
            models.Index(fields=["vendor"]),
        ]

    def __str__(self) -> str:
        return f"{self.article_name} ({self.quantity})"

    def recompute_totals(self, *, unit_price: Decimal | int | float | None = None, quantity: int | None = None) -> None:
        if unit_price is not None:
            self.unit_price = non_negative_decimal(unit_price)
        if quantity is not None:
            self.quantity = max(int(quantity), 0)

        base = non_negative_decimal(self.unit_price) * self.quantity
        self.price_including_gst = base
        self.value = base
        self.cumulative = base
        self.save(update_fields=["unit_price", "quantity", "price_including_gst", "value", "cumulative"])


class FundRequestDocument(BaseTimestampedModel):
    fund_request = models.ForeignKey(FundRequest, on_delete=models.CASCADE, related_name="documents")
    document_type = models.CharField(max_length=20, choices=FundRequestDocumentType.choices)
    file_path = models.TextField(blank=True, null=True)
    file_name = models.CharField(max_length=255)
    generated_at = models.DateTimeField(default=timezone.now)
    generated_by = models.ForeignKey(
        AppUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="generated_documents",
    )

    class Meta:
        db_table = "fund_request_documents"
        verbose_name = "Fund Request Document"
        verbose_name_plural = "Fund Request Documents"

    def __str__(self) -> str:
        return self.file_name


PURCHASE_ORDER_DEFAULT_COMMENTS = (
    "Purchase order issued with reference to:\n"
    "Delivery Period - Within a Week.\n"
    "Payment Terms - Immediate after delivery.\n"
    "Transport Cost - Inclusive."
)


# =========================
# Purchase Order Models
# =========================
class PurchaseOrder(BaseTimestampedModel):
    purchase_order_number = models.CharField(max_length=80, unique=True, blank=True, null=True)
    status = models.CharField(max_length=12, choices=FundRequestStatusChoices.choices, default=FundRequestStatusChoices.DRAFT)
    vendor_name = models.CharField(max_length=255)
    gst_number = models.CharField(max_length=64, blank=True, null=True)
    vendor_address = models.TextField()
    vendor_city = models.CharField(max_length=120)
    vendor_state = models.CharField(max_length=120)
    vendor_pincode = models.CharField(max_length=20)
    comments = models.TextField(blank=True, null=True)
    total_amount = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    created_by = models.ForeignKey(
        "core.AppUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="purchase_orders",
    )

    class Meta:
        db_table = "purchase_order"
        verbose_name = "Purchase Order"
        verbose_name_plural = "Purchase Orders"
        indexes = [
            models.Index(fields=["purchase_order_number"]),
            models.Index(fields=["status"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self) -> str:
        return self.purchase_order_number or f"Purchase Order #{self.pk}"


class PurchaseOrderItem(BaseTimestampedModel):
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name="items")
    article = models.ForeignKey(Article, on_delete=models.RESTRICT, related_name="purchase_order_items")
    article_name = models.CharField(max_length=255)
    supplier_article_name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total_value = models.DecimalField(max_digits=16, decimal_places=2, default=0)

    class Meta:
        db_table = "purchase_order_items"
        verbose_name = "Purchase Order Item"
        verbose_name_plural = "Purchase Order Items"
        indexes = [
            models.Index(fields=["purchase_order"]),
            models.Index(fields=["article"]),
        ]

    def __str__(self) -> str:
        return f"{self.article_name} ({self.quantity})"

    def recompute_totals(self) -> None:
        quantity = max(int(self.quantity or 0), 0)
        unit_price = non_negative_decimal(self.unit_price)
        self.quantity = quantity
        self.unit_price = unit_price
        self.total_value = unit_price * quantity
        self.save(update_fields=["quantity", "unit_price", "total_value"])


# =========================
# Pipeline Models (Seat/Sequence/Token/Labels)
# =========================
class EventSession(BaseTimestampedModel):
    session_name = models.CharField(max_length=120, unique=True)
    event_year = models.PositiveIntegerField(default=timezone.localdate().year)
    is_active = models.BooleanField(default=False)
    notes = models.TextField(blank=True, null=True)
    phase2_source_name = models.CharField(max_length=255, blank=True, null=True)
    phase2_source_row_count = models.PositiveIntegerField(default=0)
    phase2_grouped_row_count = models.PositiveIntegerField(default=0)
    phase2_source_quantity_total = models.PositiveIntegerField(default=0)
    phase2_grouped_quantity_total = models.PositiveIntegerField(default=0)
    phase2_reconciliation_snapshot = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "event_sessions"
        verbose_name = "Event Session"
        verbose_name_plural = "Event Sessions"
        ordering = ["-is_active", "-event_year", "session_name"]
        indexes = [
            models.Index(fields=["is_active"]),
            models.Index(fields=["event_year"]),
        ]

    def __str__(self) -> str:
        return self.session_name

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.is_active:
            self.__class__.objects.exclude(pk=self.pk).filter(is_active=True).update(is_active=False)


class SeatAllocationRow(BaseTimestampedModel):
    session = models.ForeignKey(EventSession, on_delete=models.CASCADE, related_name="seat_allocation_rows")
    source_file_name = models.CharField(max_length=255, blank=True, null=True)
    application_number = models.CharField(max_length=120, blank=True, null=True)
    beneficiary_name = models.CharField(max_length=255, blank=True, null=True)
    district = models.CharField(max_length=255, blank=True, null=True)
    requested_item = models.CharField(max_length=255)
    quantity = models.PositiveIntegerField(default=0)
    waiting_hall_quantity = models.PositiveIntegerField(default=0)
    token_quantity = models.PositiveIntegerField(default=0)
    beneficiary_type = models.CharField(max_length=30, blank=True, null=True)
    item_type = models.CharField(max_length=30, blank=True, null=True)
    comments = models.TextField(blank=True, null=True)
    master_row = models.JSONField(default=dict, blank=True)
    master_headers = models.JSONField(default=list, blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    sequence_no = models.PositiveIntegerField(blank=True, null=True)
    created_by = models.ForeignKey(
        AppUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_seat_allocation_rows",
    )
    updated_by = models.ForeignKey(
        AppUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="updated_seat_allocation_rows",
    )

    class Meta:
        db_table = "seat_allocation_rows"
        verbose_name = "Seat Allocation Row"
        verbose_name_plural = "Seat Allocation Rows"
        ordering = ["session", "sort_order", "district", "requested_item", "application_number", "id"]
        indexes = [
            models.Index(fields=["session", "sort_order"]),
            models.Index(fields=["session", "beneficiary_type"]),
            models.Index(fields=["session", "requested_item"]),
            models.Index(fields=["session", "sequence_no"]),
        ]

    def __str__(self) -> str:
        return f"{self.application_number or '-'} - {self.requested_item}"


class SequenceListItem(BaseTimestampedModel):
    session = models.ForeignKey(EventSession, on_delete=models.CASCADE, related_name="sequence_list_items")
    item_name = models.CharField(max_length=255)
    sequence_no = models.PositiveIntegerField()
    sort_order = models.PositiveIntegerField(default=0)
    created_by = models.ForeignKey(
        AppUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_sequence_list_items",
    )
    updated_by = models.ForeignKey(
        AppUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="updated_sequence_list_items",
    )

    class Meta:
        db_table = "sequence_list_items"
        verbose_name = "Sequence List Item"
        verbose_name_plural = "Sequence List Items"
        ordering = ["session", "sequence_no", "sort_order", "item_name"]
        indexes = [
            models.Index(fields=["session", "sequence_no"]),
            models.Index(fields=["session", "sort_order"]),
        ]
        constraints = [
            models.UniqueConstraint(fields=["session", "item_name"], name="uniq_sequence_item_per_session"),
            models.UniqueConstraint(fields=["session", "sequence_no"], name="uniq_sequence_no_per_session"),
        ]

    def __str__(self) -> str:
        return f"{self.sequence_no} - {self.item_name}"


class TokenGenerationRow(BaseTimestampedModel):
    session = models.ForeignKey(EventSession, on_delete=models.CASCADE, related_name="token_generation_rows")
    source_file_name = models.CharField(max_length=255, blank=True, null=True)
    application_number = models.CharField(max_length=120, blank=True, null=True)
    beneficiary_name = models.CharField(max_length=255, blank=True, null=True)
    requested_item = models.CharField(max_length=255, blank=True, null=True)
    beneficiary_type = models.CharField(max_length=30, blank=True, null=True)
    sequence_no = models.PositiveIntegerField(blank=True, null=True)
    start_token_no = models.PositiveIntegerField(blank=True, null=True)
    end_token_no = models.PositiveIntegerField(blank=True, null=True)
    row_data = models.JSONField(default=dict, blank=True)
    headers = models.JSONField(default=list, blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    created_by = models.ForeignKey(
        AppUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_token_generation_rows",
    )
    updated_by = models.ForeignKey(
        AppUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="updated_token_generation_rows",
    )

    class Meta:
        db_table = "token_generation_rows"
        verbose_name = "Token Generation Row"
        verbose_name_plural = "Token Generation Rows"
        ordering = ["session", "sort_order", "sequence_no", "requested_item", "application_number", "id"]
        indexes = [
            models.Index(fields=["session", "sort_order"]),
            models.Index(fields=["session", "sequence_no"]),
            models.Index(fields=["session", "requested_item"]),
        ]

    def __str__(self) -> str:
        return f"{self.application_number or '-'} - {self.requested_item or '-'}"


class LabelGenerationRow(BaseTimestampedModel):
    session = models.ForeignKey(EventSession, on_delete=models.CASCADE, related_name="label_generation_rows")
    source_file_name = models.CharField(max_length=255, blank=True, null=True)
    application_number = models.CharField(max_length=120, blank=True, null=True)
    beneficiary_name = models.CharField(max_length=255, blank=True, null=True)
    requested_item = models.CharField(max_length=255, blank=True, null=True)
    beneficiary_type = models.CharField(max_length=30, blank=True, null=True)
    sequence_no = models.PositiveIntegerField(blank=True, null=True)
    start_token_no = models.PositiveIntegerField(blank=True, null=True)
    end_token_no = models.PositiveIntegerField(blank=True, null=True)
    row_data = models.JSONField(default=dict, blank=True)
    headers = models.JSONField(default=list, blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    created_by = models.ForeignKey(
        AppUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_label_generation_rows",
    )
    updated_by = models.ForeignKey(
        AppUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="updated_label_generation_rows",
    )

    class Meta:
        db_table = "label_generation_rows"
        verbose_name = "Label Generation Row"
        verbose_name_plural = "Label Generation Rows"
        ordering = ["session", "sort_order", "sequence_no", "requested_item", "application_number", "id"]
        indexes = [
            models.Index(fields=["session", "sort_order"]),
            models.Index(fields=["session", "sequence_no"]),
            models.Index(fields=["session", "requested_item"]),
        ]

    def __str__(self) -> str:
        return f"{self.application_number or '-'} - {self.requested_item or '-'}"


# =========================
# Application Entry Models (Beneficiary Data)
# =========================
class DistrictBeneficiaryEntry(BaseTimestampedModel):
    district = models.ForeignKey(DistrictMaster, on_delete=models.RESTRICT, related_name="beneficiaries")
    application_number = models.CharField(max_length=120, blank=True, null=True, db_index=True)
    article = models.ForeignKey(Article, on_delete=models.RESTRICT, related_name="district_entries")
    article_cost_per_unit = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    quantity = models.PositiveIntegerField(default=1)
    total_amount = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    item_comes_here = models.BooleanField(blank=True, null=True)
    name_of_beneficiary = models.CharField(max_length=255, blank=True, null=True)
    name_of_institution = models.CharField(max_length=255, blank=True, null=True)
    aadhar_number = models.CharField(max_length=20, blank=True, null=True)
    cheque_rtgs_in_favour = models.CharField(max_length=255, blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    internal_notes = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=10, choices=BeneficiaryStatusChoices.choices, default=BeneficiaryStatusChoices.PENDING)
    created_by = models.ForeignKey(
        AppUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_district_entries",
    )
    fund_request = models.ForeignKey(
        FundRequest,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="linked_district_beneficiaries",
    )

    class Meta:
        db_table = "district_beneficiary_entries"
        verbose_name = "District Beneficiary Entry"
        verbose_name_plural = "District Beneficiary Entries"
        indexes = [
            models.Index(fields=["district"]),
            models.Index(fields=["article"]),
            models.Index(fields=["status"]),
            models.Index(fields=["fund_request"]),
        ]

    def __str__(self) -> str:
        return self.application_number or f"District entry {self.pk}"


class PublicBeneficiaryEntry(BaseTimestampedModel):
    class QuerySet(models.QuerySet):
        def active(self):
            return self.exclude(status=BeneficiaryStatusChoices.ARCHIVED)

        def archived(self):
            return self.filter(status=BeneficiaryStatusChoices.ARCHIVED)

    application_number = models.CharField(max_length=120, unique=True, blank=True, null=True)
    name = models.CharField(max_length=255)
    aadhar_number = models.CharField(max_length=20, validators=[MinLengthValidator(12)], blank=True, null=True)
    aadhaar_status = models.CharField(
        max_length=24,
        choices=AadhaarVerificationStatusChoices.choices,
        default=AadhaarVerificationStatusChoices.PENDING_VERIFICATION,
    )
    is_handicapped = models.CharField(max_length=80, choices=HandicappedStatusChoices.choices, default=HandicappedStatusChoices.NO)
    gender = models.CharField(max_length=15, choices=GenderChoices.choices, blank=True, null=True)
    female_status = models.CharField(max_length=80, choices=FemaleStatusChoices.choices, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    mobile = models.CharField(max_length=50, blank=True, null=True)
    article = models.ForeignKey(Article, on_delete=models.RESTRICT, related_name="public_entries")
    article_cost_per_unit = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    quantity = models.PositiveIntegerField(default=1)
    total_amount = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    item_comes_here = models.BooleanField(blank=True, null=True)
    name_of_institution = models.CharField(max_length=255, blank=True, null=True)
    cheque_rtgs_in_favour = models.CharField(max_length=255, blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=10, choices=BeneficiaryStatusChoices.choices, default=BeneficiaryStatusChoices.PENDING)
    archived_previous_status = models.CharField(max_length=10, blank=True, null=True)
    archived_at = models.DateTimeField(blank=True, null=True)
    archived_by = models.ForeignKey(
        AppUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="archived_public_entries",
    )
    created_by = models.ForeignKey(
        AppUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_public_entries",
    )
    fund_request = models.ForeignKey(
        FundRequest,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="linked_public_beneficiaries",
    )
    objects = QuerySet.as_manager()

    class Meta:
        db_table = "public_beneficiary_entries"
        verbose_name = "Public Beneficiary Entry"
        verbose_name_plural = "Public Beneficiary Entries"
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["article"]),
            models.Index(fields=["aadhar_number"]),
            models.Index(fields=["aadhaar_status"]),
            models.Index(fields=["application_number"]),
            models.Index(fields=["fund_request"]),
            models.Index(fields=["gender"]),
            models.Index(fields=["female_status"]),
        ]

    def __str__(self) -> str:
        return f"{self.application_number} - {self.name}"


class InstitutionsBeneficiaryEntry(BaseTimestampedModel):
    institution_name = models.CharField(max_length=255)
    institution_type = models.CharField(max_length=20, choices=InstitutionTypeChoices.choices)
    application_number = models.CharField(max_length=120, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    mobile = models.CharField(max_length=50, blank=True, null=True)
    article = models.ForeignKey(Article, on_delete=models.RESTRICT, related_name="institution_entries")
    article_cost_per_unit = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    quantity = models.PositiveIntegerField(default=1)
    total_amount = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    item_comes_here = models.BooleanField(blank=True, null=True)
    name_of_beneficiary = models.CharField(max_length=255, blank=True, null=True)
    name_of_institution = models.CharField(max_length=255, blank=True, null=True)
    aadhar_number = models.CharField(max_length=20, blank=True, null=True)
    cheque_rtgs_in_favour = models.CharField(max_length=255, blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    internal_notes = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=10, choices=BeneficiaryStatusChoices.choices, default=BeneficiaryStatusChoices.PENDING)
    created_by = models.ForeignKey(
        AppUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_institution_entries",
    )
    fund_request = models.ForeignKey(
        FundRequest,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="linked_institution_beneficiaries",
    )

    class Meta:
        db_table = "institutions_beneficiary_entries"
        verbose_name = "Institutions / Others Beneficiary Entry"
        verbose_name_plural = "Institutions / Others Beneficiary Entries"
        indexes = [
            models.Index(fields=["institution_type"]),
            models.Index(fields=["application_number"]),
            models.Index(fields=["status"]),
            models.Index(fields=["fund_request"]),
            models.Index(fields=["article"]),
        ]

    def __str__(self) -> str:
        return f"{self.institution_name} - {self.application_number or 'pending'}"


class OthersBeneficiaryEntry(BaseTimestampedModel):
    institution_name = models.CharField(max_length=255)
    application_number = models.CharField(max_length=120, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    mobile = models.CharField(max_length=50, blank=True, null=True)
    article = models.ForeignKey(Article, on_delete=models.RESTRICT, related_name="others_entries")
    article_cost_per_unit = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    quantity = models.PositiveIntegerField(default=1)
    total_amount = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    item_comes_here = models.BooleanField(blank=True, null=True)
    name_of_beneficiary = models.CharField(max_length=255, blank=True, null=True)
    name_of_institution = models.CharField(max_length=255, blank=True, null=True)
    aadhar_number = models.CharField(max_length=20, blank=True, null=True)
    cheque_rtgs_in_favour = models.CharField(max_length=255, blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    internal_notes = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=10, choices=BeneficiaryStatusChoices.choices, default=BeneficiaryStatusChoices.PENDING)
    created_by = models.ForeignKey(
        AppUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_others_entries",
    )
    fund_request = models.ForeignKey(
        FundRequest,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="linked_others_beneficiaries",
    )

    class Meta:
        db_table = "others_beneficiary_entries"
        verbose_name = "Others Beneficiary Entry"
        verbose_name_plural = "Others Beneficiary Entries"
        indexes = [
            models.Index(fields=["application_number"]),
            models.Index(fields=["status"]),
            models.Index(fields=["fund_request"]),
            models.Index(fields=["article"]),
        ]

    def __str__(self) -> str:
        return f"{self.institution_name} - {self.application_number or 'pending'}"


class ApplicationAttachmentTypeChoices(models.TextChoices):
    DISTRICT = "district", "District"
    PUBLIC = "public", "Public"
    INSTITUTION = "institution", "Institution"
    OTHERS = "others", "Others"


class ApplicationAttachmentStatusChoices(models.TextChoices):
    TEMP = "temp", "Temp"
    LINKED = "linked", "Linked"
    MISSING = "missing", "Missing"


class ApplicationAttachment(BaseTimestampedModel):
    application_type = models.CharField(max_length=20, choices=ApplicationAttachmentTypeChoices.choices)
    application_id = models.BigIntegerField(null=True, blank=True)
    draft_uid = models.CharField(max_length=36, blank=True, null=True)
    district = models.ForeignKey(
        DistrictMaster,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="application_attachments",
    )
    public_entry = models.ForeignKey(
        "core.PublicBeneficiaryEntry",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="application_attachments",
    )
    institution_application_number = models.CharField(max_length=120, blank=True, null=True)
    original_filename = models.CharField(max_length=255, blank=True)
    display_filename = models.CharField(max_length=255, blank=True)
    prefix = models.CharField(max_length=255, blank=True)
    file = models.FileField(upload_to="application_attachments/%Y/%m/%d", blank=True)
    file_name = models.CharField(max_length=255)
    drive_file_id = models.CharField(max_length=255, blank=True)
    drive_mime_type = models.CharField(max_length=255, blank=True)
    drive_view_url = models.URLField(blank=True)
    form_token = models.CharField(max_length=64, blank=True, null=True)
    status = models.CharField(
        max_length=20,
        choices=ApplicationAttachmentStatusChoices.choices,
        default=ApplicationAttachmentStatusChoices.LINKED,
    )
    temp_expires_at = models.DateTimeField(blank=True, null=True)
    uploaded_by = models.ForeignKey(
        AppUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="application_attachments",
    )

    class Meta:
        db_table = "application_attachments"
        verbose_name = "Application Attachment"
        verbose_name_plural = "Application Attachments"
        indexes = [
            models.Index(fields=["application_type"]),
            models.Index(fields=["application_type", "application_id"]),
            models.Index(fields=["application_type", "draft_uid"]),
            models.Index(fields=["district"]),
            models.Index(fields=["public_entry"]),
            models.Index(fields=["institution_application_number"]),
            models.Index(fields=["status"]),
            models.Index(fields=["form_token"]),
            models.Index(fields=["temp_expires_at"]),
        ]

    def __str__(self) -> str:
        return self.file_name


# =========================
# Inventory / Order Tracking Models
# =========================
class OrderEntry(BaseTimestampedModel):
    article = models.ForeignKey(Article, on_delete=models.RESTRICT, related_name="orders")
    quantity_ordered = models.PositiveIntegerField(default=1)
    order_date = models.DateField(default=timezone.now)
    status = models.CharField(max_length=10, choices=OrderStatusChoices.choices, default=OrderStatusChoices.PENDING)
    supplier_name = models.CharField(max_length=255, blank=True, null=True)
    supplier_contact = models.CharField(max_length=120, blank=True, null=True)
    unit_price = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    total_amount = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    expected_delivery_date = models.DateField(blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    created_by = models.ForeignKey(
        AppUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_orders",
    )
    fund_request = models.ForeignKey(
        FundRequest,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="order_entries",
    )

    class Meta:
        db_table = "order_entries"
        verbose_name = "Order Entry"
        verbose_name_plural = "Order Entries"
        indexes = [
            models.Index(fields=["article"]),
            models.Index(fields=["status"]),
            models.Index(fields=["order_date"]),
            models.Index(fields=["article", "status"]),
            models.Index(fields=["fund_request"]),
        ]

    def __str__(self) -> str:
        return f"{self.article.article_name} ({self.quantity_ordered})"

    def save(self, *args, **kwargs) -> None:
        if self.unit_price is not None:
            self.total_amount = non_negative_decimal(self.unit_price) * self.quantity_ordered
        super().save(*args, **kwargs)


# =========================
# Dashboard Models
# =========================
class DashboardSetting(BaseTimestampedModel):
    event_budget = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    updated_by = models.ForeignKey(
        AppUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="updated_dashboard_settings",
    )

    class Meta:
        db_table = "dashboard_settings"
        verbose_name = "Dashboard Setting"
        verbose_name_plural = "Dashboard Settings"

    def __str__(self) -> str:
        return f"Dashboard Setting ({self.event_budget})"


# =========================
# Base Files / History Models
# =========================
class PublicBeneficiaryHistory(BaseTimestampedModel):
    aadhar_number = models.CharField(max_length=20)
    name = models.CharField(max_length=255)
    year = models.PositiveIntegerField(validators=[MinValueValidator(2000)])
    article_name = models.CharField(max_length=255, blank=True, null=True)
    application_number = models.CharField(max_length=120, blank=True, null=True)
    comments = models.TextField(blank=True, null=True)
    is_handicapped = models.BooleanField(blank=True, null=True)
    handicapped_status = models.CharField(max_length=80, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    mobile = models.CharField(max_length=50, blank=True, null=True)
    aadhar_number_sp = models.CharField(max_length=20, blank=True, null=True)
    is_selected = models.BooleanField(blank=True, null=True)
    category = models.CharField(max_length=120, blank=True, null=True)
    gender = models.CharField(max_length=15, blank=True, null=True)
    gender_status = models.CharField(max_length=80, blank=True, null=True)

    class Meta:
        db_table = "public_beneficiary_history"
        verbose_name = "Public Beneficiary History"
        verbose_name_plural = "Public Beneficiary History"

    def __str__(self) -> str:
        return f"{self.application_number or ''} {self.aadhar_number}"


# =========================
# Audit Logs Models
# =========================
class AuditLog(BaseTimestampedModel):
    user = models.ForeignKey(AppUser, on_delete=models.SET_NULL, null=True, related_name="audit_logs")
    action_type = models.CharField(max_length=16, choices=ActionTypeChoices.choices)
    entity_type = models.CharField(max_length=100)
    entity_id = models.CharField(max_length=120, blank=True, null=True)
    details = models.JSONField(default=dict, blank=True)
    ip_address = models.CharField(max_length=64, blank=True, null=True)
    user_agent = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        db_table = "audit_logs"
        verbose_name = "Audit Log"
        verbose_name_plural = "Audit Logs"
        indexes = [
            models.Index(fields=["user"]),
            models.Index(fields=["action_type"]),
            models.Index(fields=["entity_type"]),
            models.Index(fields=["created_at"]),
            models.Index(fields=["entity_type", "entity_id"]),
        ]

    def __str__(self) -> str:
        user = self.user.email if self.user else "system"
        return f"{self.action_type} {self.entity_type}:{self.entity_id} by {user}"
