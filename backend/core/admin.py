from __future__ import annotations

from django.contrib import admin

from . import models


@admin.register(models.AppUser)
class AppUserAdmin(admin.ModelAdmin):
    list_display = ("email", "display_name", "role", "status", "is_active", "is_staff", "created_at")
    list_filter = ("role", "status", "is_active", "created_at")
    search_fields = ("email", "first_name", "last_name")
    ordering = ("-created_at",)


@admin.register(models.Article)
class ArticleAdmin(admin.ModelAdmin):
    list_display = ("article_name", "item_type", "category", "master_category", "cost_per_unit", "is_active", "combo")
    list_filter = ("item_type", "is_active", "combo")
    search_fields = ("article_name", "article_name_tk", "category", "master_category")


@admin.register(models.DistrictMaster)
class DistrictMasterAdmin(admin.ModelAdmin):
    list_display = ("district_name", "application_number", "allotted_budget", "president_name", "mobile_number", "is_active")
    list_filter = ("is_active",)
    search_fields = ("district_name", "president_name", "application_number")


@admin.register(models.DistrictBeneficiaryEntry)
class DistrictBeneficiaryEntryAdmin(admin.ModelAdmin):
    list_display = ("application_number", "district", "article", "quantity", "total_amount", "status", "fund_request")
    list_filter = ("status",)
    search_fields = ("application_number", "district__district_name", "notes")


@admin.register(models.PublicBeneficiaryEntry)
class PublicBeneficiaryEntryAdmin(admin.ModelAdmin):
    list_display = ("application_number", "name", "aadhar_number", "article", "quantity", "total_amount", "status", "fund_request")
    list_filter = ("status", "is_handicapped", "gender")
    search_fields = ("application_number", "name", "aadhar_number")


@admin.register(models.InstitutionsBeneficiaryEntry)
class InstitutionsBeneficiaryEntryAdmin(admin.ModelAdmin):
    list_display = ("institution_name", "institution_type", "application_number", "article", "quantity", "total_amount", "status")
    list_filter = ("institution_type", "status")
    search_fields = ("institution_name", "application_number")


@admin.register(models.FundRequest)
class FundRequestAdmin(admin.ModelAdmin):
    list_display = ("fund_request_number", "fund_request_type", "status", "total_amount", "created_by", "created_at", "purchase_order_number")
    list_filter = ("fund_request_type", "status")
    search_fields = ("fund_request_number", "aid_type", "notes")


@admin.register(models.FundRequestRecipient)
class FundRequestRecipientAdmin(admin.ModelAdmin):
    list_display = ("fund_request", "beneficiary_type", "recipient_name", "fund_requested", "aadhar_number")
    list_filter = ("beneficiary_type",)
    search_fields = ("recipient_name", "beneficiary", "aadhar_number")


@admin.register(models.FundRequestArticle)
class FundRequestArticleAdmin(admin.ModelAdmin):
    list_display = ("fund_request", "article_name", "quantity", "unit_price", "value", "cheque_no")
    list_filter = ("cheque_no",)
    search_fields = ("article_name", "beneficiary", "cheque_no")


@admin.register(models.FundRequestDocument)
class FundRequestDocumentAdmin(admin.ModelAdmin):
    list_display = ("fund_request", "document_type", "file_name", "generated_by", "generated_at")
    list_filter = ("document_type",)


@admin.register(models.OrderEntry)
class OrderEntryAdmin(admin.ModelAdmin):
    list_display = ("article", "quantity_ordered", "status", "supplier_name", "total_amount", "order_date", "fund_request")
    list_filter = ("status",)
    search_fields = ("article__article_name", "supplier_name", "notes")


@admin.register(models.AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("action_type", "entity_type", "entity_id", "user", "created_at")
    list_filter = ("action_type", "entity_type")
    search_fields = ("entity_type", "entity_id", "user__email")


@admin.register(models.PublicBeneficiaryHistory)
class PublicBeneficiaryHistoryAdmin(admin.ModelAdmin):
    list_display = ("application_number", "aadhar_number", "name", "year", "is_handicapped", "is_selected")
    list_filter = ("year", "is_handicapped", "is_selected")
    search_fields = ("application_number", "aadhar_number", "name")

