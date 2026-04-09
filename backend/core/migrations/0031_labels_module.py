from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0030_token_generation_module"),
    ]

    operations = [
        migrations.CreateModel(
            name="LabelGenerationRow",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("source_file_name", models.CharField(blank=True, max_length=255, null=True)),
                ("application_number", models.CharField(blank=True, max_length=120, null=True)),
                ("beneficiary_name", models.CharField(blank=True, max_length=255, null=True)),
                ("requested_item", models.CharField(blank=True, max_length=255, null=True)),
                ("beneficiary_type", models.CharField(blank=True, max_length=30, null=True)),
                ("sequence_no", models.PositiveIntegerField(blank=True, null=True)),
                ("start_token_no", models.PositiveIntegerField(blank=True, null=True)),
                ("end_token_no", models.PositiveIntegerField(blank=True, null=True)),
                ("row_data", models.JSONField(blank=True, default=dict)),
                ("headers", models.JSONField(blank=True, default=list)),
                ("sort_order", models.PositiveIntegerField(default=0)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_label_generation_rows", to="core.appuser")),
                ("session", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="label_generation_rows", to="core.eventsession")),
                ("updated_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="updated_label_generation_rows", to="core.appuser")),
            ],
            options={
                "verbose_name": "Label Generation Row",
                "verbose_name_plural": "Label Generation Rows",
                "db_table": "label_generation_rows",
                "ordering": ["session", "sort_order", "sequence_no", "requested_item", "application_number", "id"],
            },
        ),
        migrations.AddIndex(
            model_name="labelgenerationrow",
            index=models.Index(fields=["session", "sort_order"], name="label_gener_session_sort_idx"),
        ),
        migrations.AddIndex(
            model_name="labelgenerationrow",
            index=models.Index(fields=["session", "sequence_no"], name="label_gener_session_seq_idx"),
        ),
        migrations.AddIndex(
            model_name="labelgenerationrow",
            index=models.Index(fields=["session", "requested_item"], name="label_gener_session_item_idx"),
        ),
        migrations.AlterField(
            model_name="usermodulepermission",
            name="module_key",
            field=models.CharField(
                choices=[
                    ("application_entry", "Application Entry"),
                    ("article_management", "Article Management"),
                    ("base_files", "Base Files"),
                    ("inventory_planning", "Inventory Planning"),
                    ("seat_allocation", "Seat Allocation"),
                    ("sequence_list", "Sequence List"),
                    ("token_generation", "Token Generation"),
                    ("labels", "Labels"),
                    ("order_fund_request", "Order & Fund Request"),
                    ("purchase_order", "Purchase Order"),
                    ("audit_logs", "Audit Logs"),
                    ("user_management", "User Management"),
                ],
                max_length=64,
            ),
        ),
    ]
