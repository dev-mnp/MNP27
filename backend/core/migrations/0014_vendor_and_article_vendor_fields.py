import django.db.models.deletion
from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0013_fundrequestrecipient_unique_source_constraint"),
    ]

    operations = [
        migrations.CreateModel(
            name="Vendor",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("vendor_name", models.CharField(max_length=255)),
                ("gst_number", models.CharField(blank=True, max_length=64, null=True)),
                ("address", models.TextField(blank=True, null=True)),
                ("city", models.CharField(blank=True, max_length=120, null=True)),
                ("state", models.CharField(blank=True, max_length=120, null=True)),
                ("pincode", models.CharField(blank=True, max_length=20, null=True)),
                ("cheque_in_favour", models.CharField(blank=True, max_length=255, null=True)),
                ("is_active", models.BooleanField(default=True)),
            ],
            options={
                "verbose_name": "Vendor",
                "verbose_name_plural": "Vendors",
                "db_table": "vendors",
            },
        ),
        migrations.AddField(
            model_name="fundrequestarticle",
            name="vendor",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="fund_request_articles", to="core.vendor"),
        ),
        migrations.AddField(
            model_name="fundrequestarticle",
            name="vendor_address",
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="fundrequestarticle",
            name="vendor_city",
            field=models.CharField(blank=True, max_length=120, null=True),
        ),
        migrations.AddField(
            model_name="fundrequestarticle",
            name="vendor_name",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name="fundrequestarticle",
            name="vendor_pincode",
            field=models.CharField(blank=True, max_length=20, null=True),
        ),
        migrations.AddField(
            model_name="fundrequestarticle",
            name="vendor_state",
            field=models.CharField(blank=True, max_length=120, null=True),
        ),
        migrations.AddIndex(
            model_name="vendor",
            index=models.Index(fields=["vendor_name"], name="vendor_name_idx"),
        ),
        migrations.AddIndex(
            model_name="vendor",
            index=models.Index(fields=["gst_number"], name="vendor_gst_idx"),
        ),
        migrations.AddIndex(
            model_name="vendor",
            index=models.Index(fields=["is_active"], name="vendor_active_idx"),
        ),
        migrations.AddIndex(
            model_name="fundrequestarticle",
            index=models.Index(fields=["vendor"], name="fundreq_article_vendor_idx"),
        ),
    ]
