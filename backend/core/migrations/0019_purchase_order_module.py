from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0018_application_name_of_institution"),
    ]

    operations = [
        migrations.CreateModel(
            name="PurchaseOrder",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("purchase_order_number", models.CharField(blank=True, max_length=80, null=True, unique=True)),
                ("status", models.CharField(choices=[("draft", "Draft"), ("submitted", "Submitted"), ("approved", "Approved"), ("rejected", "Rejected"), ("completed", "Completed")], default="draft", max_length=12)),
                ("vendor_name", models.CharField(max_length=255)),
                ("vendor_address", models.TextField()),
                ("vendor_city", models.CharField(max_length=120)),
                ("vendor_state", models.CharField(max_length=120)),
                ("vendor_pincode", models.CharField(max_length=20)),
                ("total_amount", models.DecimalField(decimal_places=2, default=0, max_digits=16)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="purchase_orders", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "Purchase Order",
                "verbose_name_plural": "Purchase Orders",
                "db_table": "purchase_order",
            },
        ),
        migrations.CreateModel(
            name="PurchaseOrderItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("article_name", models.CharField(max_length=255)),
                ("supplier_article_name", models.CharField(max_length=255)),
                ("description", models.TextField(blank=True, null=True)),
                ("quantity", models.PositiveIntegerField(default=1)),
                ("unit_price", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("total_value", models.DecimalField(decimal_places=2, default=0, max_digits=16)),
                ("article", models.ForeignKey(on_delete=django.db.models.deletion.RESTRICT, related_name="purchase_order_items", to="core.article")),
                ("purchase_order", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="items", to="core.purchaseorder")),
            ],
            options={
                "verbose_name": "Purchase Order Item",
                "verbose_name_plural": "Purchase Order Items",
                "db_table": "purchase_order_items",
            },
        ),
        migrations.AddIndex(
            model_name="purchaseorder",
            index=models.Index(fields=["purchase_order_number"], name="purchase_or_purchas_b53c86_idx"),
        ),
        migrations.AddIndex(
            model_name="purchaseorder",
            index=models.Index(fields=["status"], name="purchase_or_status_9d2e52_idx"),
        ),
        migrations.AddIndex(
            model_name="purchaseorder",
            index=models.Index(fields=["created_at"], name="purchase_or_created_5dd8ad_idx"),
        ),
        migrations.AddIndex(
            model_name="purchaseorderitem",
            index=models.Index(fields=["purchase_order"], name="purchase_or_purchase_a0b903_idx"),
        ),
        migrations.AddIndex(
            model_name="purchaseorderitem",
            index=models.Index(fields=["article"], name="purchase_or_article_0a6707_idx"),
        ),
    ]
