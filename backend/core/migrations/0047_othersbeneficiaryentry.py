from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0046_article_allow_manual_price"),
    ]

    operations = [
        migrations.CreateModel(
            name="OthersBeneficiaryEntry",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True, db_index=True)),
                ("institution_name", models.CharField(max_length=255)),
                ("application_number", models.CharField(blank=True, max_length=120, null=True)),
                ("address", models.TextField(blank=True, null=True)),
                ("mobile", models.CharField(blank=True, max_length=50, null=True)),
                ("article_cost_per_unit", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("quantity", models.PositiveIntegerField(default=1)),
                ("total_amount", models.DecimalField(decimal_places=2, default=0, max_digits=16)),
                ("item_comes_here", models.BooleanField(blank=True, null=True)),
                ("name_of_beneficiary", models.CharField(blank=True, max_length=255, null=True)),
                ("name_of_institution", models.CharField(blank=True, max_length=255, null=True)),
                ("aadhar_number", models.CharField(blank=True, max_length=20, null=True)),
                ("cheque_rtgs_in_favour", models.CharField(blank=True, max_length=255, null=True)),
                ("notes", models.TextField(blank=True, null=True)),
                ("internal_notes", models.TextField(blank=True, null=True)),
                (
                    "status",
                    models.CharField(
                        choices=[("pending", "Pending"), ("draft", "Draft"), ("submitted", "Submitted"), ("archived", "Archived")],
                        default="pending",
                        max_length=10,
                    ),
                ),
                (
                    "article",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.RESTRICT,
                        related_name="others_entries",
                        to="core.article",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="created_others_entries",
                        to="core.appuser",
                    ),
                ),
                (
                    "fund_request",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="linked_others_beneficiaries",
                        to="core.fundrequest",
                    ),
                ),
            ],
            options={
                "verbose_name": "Others Beneficiary Entry",
                "verbose_name_plural": "Others Beneficiary Entries",
                "db_table": "others_beneficiary_entries",
            },
        ),
        migrations.AddIndex(
            model_name="othersbeneficiaryentry",
            index=models.Index(fields=["application_number"], name="others_bene_applica_9b1842_idx"),
        ),
        migrations.AddIndex(
            model_name="othersbeneficiaryentry",
            index=models.Index(fields=["status"], name="others_bene_status_4fe8a3_idx"),
        ),
        migrations.AddIndex(
            model_name="othersbeneficiaryentry",
            index=models.Index(fields=["fund_request"], name="others_bene_fund_re_d2b926_idx"),
        ),
        migrations.AddIndex(
            model_name="othersbeneficiaryentry",
            index=models.Index(fields=["article"], name="others_bene_article_1f059d_idx"),
        ),
    ]
