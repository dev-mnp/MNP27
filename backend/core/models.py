from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from django.contrib.auth.models import AbstractUser
from django.core.validators import MinLengthValidator, MinValueValidator
from django.db import models
from django.utils import timezone


class RoleChoices(models.TextChoices):
    ADMIN = "admin", "Admin"
    EDITOR = "editor", "Editor"
    VIEWER = "viewer", "Viewer"


class StatusChoices(models.TextChoices):
    ACTIVE = "active", "Active"
    INACTIVE = "inactive", "Inactive"


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
    SINGLE_MOTHER = "Single Mother", "Single Mother"
    WIDOW = "Widow", "Widow"
    MARRIED = "Married", "Married"
    UNMARRIED = "Unmarried", "Unmarried"


class InstitutionTypeChoices(models.TextChoices):
    INSTITUTIONS = "institutions", "Institutions"
    OTHERS = "others", "Others"


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


class AppUser(AbstractUser):
    """
    Role-aware user model used by all app modules.
    """

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    username = None
    email = models.EmailField(unique=True)
    role = models.CharField(max_length=12, choices=RoleChoices.choices, default=RoleChoices.VIEWER)
    status = models.CharField(max_length=9, choices=StatusChoices.choices, default=StatusChoices.ACTIVE)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

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


class Article(BaseTimestampedModel):
    article_name = models.CharField(max_length=255, unique=True)
    article_name_tk = models.CharField(max_length=255, blank=True, null=True)
    cost_per_unit = models.DecimalField(max_digits=14, decimal_places=2, default=0)
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


class DistrictMaster(BaseTimestampedModel):
    district_name = models.CharField(max_length=255, unique=True)
    allotted_budget = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    president_name = models.CharField(max_length=255)
    mobile_number = models.CharField(max_length=20)
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


class FundRequest(BaseTimestampedModel):
    fund_request_type = models.CharField(max_length=20, choices=FundRequestTypeChoices.choices)
    fund_request_number = models.CharField(max_length=80, unique=True)
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
        return f"{self.fund_request_type} {self.fund_request_number}"


class FundRequestRecipient(BaseTimestampedModel):
    fund_request = models.ForeignKey(FundRequest, on_delete=models.CASCADE, related_name="recipients")
    beneficiary_type = models.CharField(max_length=20, choices=RecipientTypeChoices.choices, blank=True, null=True)
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
        indexes = [models.Index(fields=["fund_request"]), models.Index(fields=["beneficiary_type"])]

    def __str__(self) -> str:
        return self.recipient_name or "Recipient"


class FundRequestArticle(BaseTimestampedModel):
    fund_request = models.ForeignKey(FundRequest, on_delete=models.CASCADE, related_name="articles")
    article = models.ForeignKey(Article, on_delete=models.RESTRICT, related_name="fund_request_lines")
    sl_no = models.PositiveIntegerField(blank=True, null=True)
    beneficiary = models.TextField(blank=True, null=True)
    article_name = models.CharField(max_length=255)
    gst_no = models.CharField(max_length=64, blank=True, null=True)
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


class DistrictBeneficiaryEntry(BaseTimestampedModel):
    district = models.ForeignKey(DistrictMaster, on_delete=models.RESTRICT, related_name="beneficiaries")
    application_number = models.CharField(max_length=120, blank=True, null=True, db_index=True)
    article = models.ForeignKey(Article, on_delete=models.RESTRICT, related_name="district_entries")
    article_cost_per_unit = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    quantity = models.PositiveIntegerField(default=1)
    total_amount = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    notes = models.TextField(blank=True, null=True)
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
    application_number = models.CharField(max_length=120, unique=True)
    name = models.CharField(max_length=255)
    aadhar_number = models.CharField(max_length=20, validators=[MinLengthValidator(12)])
    is_handicapped = models.BooleanField(default=False)
    gender = models.CharField(max_length=15, choices=GenderChoices.choices, blank=True, null=True)
    female_status = models.CharField(max_length=20, choices=FemaleStatusChoices.choices, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    mobile = models.CharField(max_length=20, blank=True, null=True)
    article = models.ForeignKey(Article, on_delete=models.RESTRICT, related_name="public_entries")
    article_cost_per_unit = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    quantity = models.PositiveIntegerField(default=1)
    total_amount = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    notes = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=10, choices=BeneficiaryStatusChoices.choices, default=BeneficiaryStatusChoices.PENDING)
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

    class Meta:
        db_table = "public_beneficiary_entries"
        verbose_name = "Public Beneficiary Entry"
        verbose_name_plural = "Public Beneficiary Entries"
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["article"]),
            models.Index(fields=["aadhar_number"]),
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
    mobile = models.CharField(max_length=20, blank=True, null=True)
    article = models.ForeignKey(Article, on_delete=models.RESTRICT, related_name="institution_entries")
    article_cost_per_unit = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    quantity = models.PositiveIntegerField(default=1)
    total_amount = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    notes = models.TextField(blank=True, null=True)
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


class PublicBeneficiaryHistory(BaseTimestampedModel):
    aadhar_number = models.CharField(max_length=20)
    name = models.CharField(max_length=255)
    year = models.PositiveIntegerField(validators=[MinValueValidator(2000)])
    article_name = models.CharField(max_length=255, blank=True, null=True)
    application_number = models.CharField(max_length=120, blank=True, null=True)
    comments = models.TextField(blank=True, null=True)
    is_handicapped = models.BooleanField(blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    mobile = models.CharField(max_length=20, blank=True, null=True)
    aadhar_number_sp = models.CharField(max_length=20, blank=True, null=True)
    is_selected = models.BooleanField(blank=True, null=True)
    category = models.CharField(max_length=120, blank=True, null=True)

    class Meta:
        db_table = "public_beneficiary_history"
        verbose_name = "Public Beneficiary History"
        verbose_name_plural = "Public Beneficiary History"

    def __str__(self) -> str:
        return f"{self.application_number or ''} {self.aadhar_number}"


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
