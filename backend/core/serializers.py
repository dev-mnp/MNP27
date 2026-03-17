from __future__ import annotations

from rest_framework import serializers

from . import models


class AppUserSerializer(serializers.ModelSerializer):
    name = serializers.SerializerMethodField()

    class Meta:
        model = models.AppUser
        fields = [
            "id",
            "email",
            "name",
            "first_name",
            "last_name",
            "role",
            "status",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ("created_at", "updated_at")

    def get_name(self, obj: models.AppUser) -> str:
        return obj.display_name


class ArticleSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Article
        fields = "__all__"


class DistrictMasterSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.DistrictMaster
        fields = "__all__"


class DistrictBeneficiaryEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = models.DistrictBeneficiaryEntry
        fields = "__all__"
        read_only_fields = ("id", "created_at", "updated_at")


class PublicBeneficiaryEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = models.PublicBeneficiaryEntry
        fields = "__all__"
        read_only_fields = ("id", "created_at", "updated_at")


class InstitutionsBeneficiaryEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = models.InstitutionsBeneficiaryEntry
        fields = "__all__"
        read_only_fields = ("id", "created_at", "updated_at")


class FundRequestRecipientSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.FundRequestRecipient
        fields = "__all__"
        read_only_fields = ("id", "created_at")


class FundRequestArticleSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.FundRequestArticle
        fields = "__all__"
        read_only_fields = ("id", "created_at")


class FundRequestDocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.FundRequestDocument
        fields = "__all__"
        read_only_fields = ("id", "generated_at")


class FundRequestSerializer(serializers.ModelSerializer):
    recipients = FundRequestRecipientSerializer(source="recipients", many=True, read_only=True)
    articles = FundRequestArticleSerializer(source="articles", many=True, read_only=True)

    class Meta:
        model = models.FundRequest
        fields = "__all__"
        read_only_fields = ("id", "created_at", "updated_at")


class FundRequestWriteSerializer(serializers.ModelSerializer):
    recipients = FundRequestRecipientSerializer(many=True, required=False)
    articles = FundRequestArticleSerializer(many=True, required=False)

    class Meta:
        model = models.FundRequest
        fields = [
            "id",
            "fund_request_type",
            "fund_request_number",
            "status",
            "total_amount",
            "aid_type",
            "notes",
            "gst_number",
            "supplier_name",
            "supplier_address",
            "supplier_city",
            "supplier_state",
            "supplier_pincode",
            "purchase_order_number",
            "recipients",
            "articles",
        ]
        read_only_fields = ("id", "created_at", "updated_at")

    def create(self, validated_data):
        recipients_data = validated_data.pop("recipients", [])
        articles_data = validated_data.pop("articles", [])
        request = self.context["request"]
        user = request.user if request and request.user.is_authenticated else None
        instance = models.FundRequest.objects.create(created_by=user, **validated_data)
        for rec in recipients_data:
            models.FundRequestRecipient.objects.create(fund_request=instance, **rec)
        for item in articles_data:
            models.FundRequestArticle.objects.create(fund_request=instance, **item)
        return instance

    def update(self, instance, validated_data):
        recipients_data = validated_data.pop("recipients", None)
        articles_data = validated_data.pop("articles", None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if recipients_data is not None:
            instance.recipients.all().delete()
            for rec in recipients_data:
                models.FundRequestRecipient.objects.create(fund_request=instance, **rec)

        if articles_data is not None:
            instance.articles.all().delete()
            for item in articles_data:
                models.FundRequestArticle.objects.create(fund_request=instance, **item)
        return instance


class OrderEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = models.OrderEntry
        fields = "__all__"
        read_only_fields = ("id", "created_at", "updated_at")


class AuditLogSerializer(serializers.ModelSerializer):
    user_email = serializers.SerializerMethodField()

    class Meta:
        model = models.AuditLog
        fields = [
            "id",
            "user",
            "user_email",
            "action_type",
            "entity_type",
            "entity_id",
            "details",
            "ip_address",
            "user_agent",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ("id", "created_at", "updated_at")

    def get_user_email(self, obj: models.AuditLog) -> str | None:
        return obj.user.email if obj.user else None


class PublicBeneficiaryHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = models.PublicBeneficiaryHistory
        fields = "__all__"
        read_only_fields = ("id", "created_at", "updated_at")
